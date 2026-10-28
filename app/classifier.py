"""Incident classifiers: fine-tuned Qwen (QLoRA, merged), cloud LLM (prompting) and keyword rules.

All three return the same Classification object so the workflow and the evaluation can swap them freely.
The prompt used by the fine-tuned model is defined here and copied verbatim into the training notebook.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.taxonomy import INCIDENT_TYPE_IDS, INCIDENT_TYPES, SEVERITY_IDS  # noqa: E402

from .config import Settings  # noqa: E402
from .llm import BackendError, extract_json  # noqa: E402

logger = logging.getLogger("oncall.classifier")

from .prompts import CLASSIFY_SYSTEM, classify_user_prompt  # noqa: E402


@dataclass
class Classification:
    incident_type: str
    severity: str
    confidence: float
    method: str
    latency_ms: float = 0.0
    raw: str = ""
    scores: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return INCIDENT_TYPES.get(self.incident_type, {}).get("label", self.incident_type)


def parse_label(text: str) -> tuple[Optional[str], Optional[str]]:
    """Robustly read incident_type and severity from a model reply (JSON preferred, substring fallback)."""
    obj = extract_json(text) or {}
    itype = obj.get("incident_type") if isinstance(obj, dict) else None
    sev = obj.get("severity") if isinstance(obj, dict) else None
    low = text.lower()
    if itype not in INCIDENT_TYPE_IDS:
        found = [t for t in INCIDENT_TYPE_IDS if t in low]
        itype = found[0] if found else None
    if sev not in SEVERITY_IDS:
        m = re.search(r"\bP([1-4])\b", text)
        sev = f"P{m.group(1)}" if m else None
    return itype, sev


# ----------------------------------------------------------------------------- rules
class RulesClassifier:
    """Keyword baseline (the kind of classifier used in Experiment 6)."""
    method = "rules"

    def classify(self, log_text: str) -> Classification:
        t0 = time.perf_counter()
        low = log_text.lower()
        scores = {t: sum(low.count(k.lower()) for k in INCIDENT_TYPES[t]["keywords"]) for t in INCIDENT_TYPE_IDS}
        best = max(scores, key=scores.get)
        total = sum(scores.values())
        confidence = scores[best] / total if total else 0.0
        if total == 0:
            best = "application_exception"
        env = "prod" if "[prod]" in low or "production" in low else "staging" if "[staging]" in low else "dev" if "[dev]" in low else "prod"
        if env == "prod" and re.search(r"all users|100%|revenue|outage|unavailable for all|primary database", low):
            sev = "P1"
        elif env == "prod":
            sev = "P2"
        elif env == "staging":
            sev = "P3"
        else:
            sev = "P4" if re.search(r"single occurrence|informational|once|baseline|auto-restart", low) else "P3"
        return Classification(best, sev, round(confidence, 3), self.method, (time.perf_counter() - t0) * 1000,
                              scores=scores)


# ----------------------------------------------------------------------------- cloud LLM
class LLMClassifier:
    method = "llm_prompting"

    def __init__(self, backend):
        self.backend = backend

    def classify(self, log_text: str) -> Classification:
        t0 = time.perf_counter()
        gen = self.backend.generate([{"role": "system", "content": CLASSIFY_SYSTEM},
                                     {"role": "user", "content": classify_user_prompt(log_text)}],
                                    max_tokens=80, json_mode=True)
        itype, sev = parse_label(gen.text)
        obj = extract_json(gen.text) or {}
        conf = obj.get("confidence", 0.9 if itype and sev else 0.3)
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.5
        return Classification(itype or "application_exception", sev or "P3", round(min(max(conf, 0.0), 1.0), 3),
                              self.method, (time.perf_counter() - t0) * 1000, raw=gen.text)


# ----------------------------------------------------------------------------- fine-tuned model
class FinetunedClassifier:
    """QLoRA-fine-tuned Qwen2.5-0.5B-Instruct (adapter merged into the base weights), run with Transformers.
    Works on CPU (about 1-4 s per log on 2 vCPUs) or GPU. Confidence = geometric mean token probability of the
    generated label."""
    method = "qlora_finetuned"

    def __init__(self, model_id: str, device: Optional[str] = None):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        t0 = time.perf_counter()
        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=dtype).to(self.device).eval()
        self.model_id = model_id
        self.load_s = time.perf_counter() - t0
        logger.info("finetuned_classifier_ready model=%s device=%s load_s=%.1f", model_id, self.device, self.load_s)

    def classify(self, log_text: str) -> Classification:
        torch = self.torch
        t0 = time.perf_counter()
        messages = [{"role": "system", "content": CLASSIFY_SYSTEM},
                    {"role": "user", "content": classify_user_prompt(log_text[:6000])}]
        prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048).to(self.device)
        with torch.no_grad():
            out = self.model.generate(**inputs, max_new_tokens=48, do_sample=False, output_scores=True,
                                      return_dict_in_generate=True, pad_token_id=self.tokenizer.pad_token_id
                                      or self.tokenizer.eos_token_id)
        new_tokens = out.sequences[0][inputs["input_ids"].shape[1]:]
        text = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        logps = []
        for step, tok in zip(out.scores, new_tokens):
            lp = torch.log_softmax(step[0].float(), dim=-1)[tok].item()
            logps.append(lp)
            if tok.item() == self.tokenizer.eos_token_id:
                break
        confidence = math.exp(sum(logps) / len(logps)) if logps else 0.0
        itype, sev = parse_label(text)
        if itype is None or sev is None:
            confidence = min(confidence, 0.3)
        return Classification(itype or "application_exception", sev or "P3", round(confidence, 3), self.method,
                              (time.perf_counter() - t0) * 1000, raw=text)


def create_classifier(settings: Settings, backend):
    """Build the configured classifier, falling back as configured when the fine-tuned model is unavailable."""
    choice = settings.classifier_backend
    if choice == "finetuned":
        if settings.finetuned_model:
            try:
                return FinetunedClassifier(settings.finetuned_model)
            except Exception as exc:  # model missing / no internet / no RAM -> fall back, never crash the service
                logger.error("finetuned_classifier_unavailable reason=%s; falling back to %s",
                             type(exc).__name__, settings.classifier_fallback)
        else:
            logger.warning("FINETUNED_MODEL not set; falling back to %s", settings.classifier_fallback)
        choice = settings.classifier_fallback
    if choice == "llm":
        return LLMClassifier(backend)
    if choice == "rules":
        return RulesClassifier()
    raise ValueError(f"Unknown CLASSIFIER_BACKEND '{choice}'")
