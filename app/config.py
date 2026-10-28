"""Configuration for OnCall AI, read from environment variables (and a local .env file in development)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env_float(name: str, default: Optional[float]) -> Optional[float]:
    raw = os.getenv(name, "").strip()
    if raw == "":
        return default
    if raw.lower() in {"none", "off", "disabled"}:
        return None
    return float(raw)


@dataclass(frozen=True)
class Settings:
    # knowledge base / retrieval
    knowledge_dir: str = os.path.join(ROOT, "knowledge_base")
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"   # "hash" = offline test embedder
    chunk_size: int = 600
    chunk_overlap: int = 80
    top_k: int = 4
    max_distance: Optional[float] = 1.6

    # classifier: "finetuned" (QLoRA-merged Qwen on HF Hub / local path), "llm" (cloud LLM), "rules" (keywords)
    classifier_backend: str = "finetuned"
    finetuned_model: str = ""                         # HF repo id or local path of the merged fine-tuned model
    classifier_fallback: str = "llm"                  # used when the fine-tuned model cannot be loaded
    classifier_min_confidence: float = 0.55

    # cloud LLM (OpenAI-compatible chat completions)
    llm_backend: str = "openai_compatible"            # or "mock"
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "qwen/qwen3.8-27b"
    llm_api_key: str = field(default="", repr=False)
    llm_timeout_s: float = 45.0
    llm_max_tokens: int = 900
    llm_temperature: float = 0.1
    llm_max_retries: int = 2

    # API limits
    max_log_chars: int = 20000
    results_dir: str = os.path.join(ROOT, "results")

    @classmethod
    def from_env(cls) -> "Settings":
        d = cls()
        return cls(
            knowledge_dir=os.getenv("KNOWLEDGE_DIR", d.knowledge_dir),
            embedding_model=os.getenv("EMBEDDING_MODEL", d.embedding_model),
            chunk_size=int(os.getenv("RAG_CHUNK_SIZE", d.chunk_size)),
            chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", d.chunk_overlap)),
            top_k=int(os.getenv("RAG_TOP_K", d.top_k)),
            max_distance=_env_float("RAG_MAX_DISTANCE", d.max_distance),
            classifier_backend=os.getenv("CLASSIFIER_BACKEND", d.classifier_backend).strip().lower(),
            finetuned_model=os.getenv("FINETUNED_MODEL", d.finetuned_model).strip(),
            classifier_fallback=os.getenv("CLASSIFIER_FALLBACK", d.classifier_fallback).strip().lower(),
            classifier_min_confidence=float(os.getenv("CLASSIFIER_MIN_CONFIDENCE", d.classifier_min_confidence)),
            llm_backend=os.getenv("LLM_BACKEND", d.llm_backend).strip().lower(),
            llm_base_url=os.getenv("LLM_BASE_URL", d.llm_base_url).rstrip("/"),
            llm_model=os.getenv("LLM_MODEL", d.llm_model),
            llm_api_key=os.getenv("LLM_API_KEY", os.getenv("GROQ_API_KEY", "")).strip(),
            llm_timeout_s=float(os.getenv("LLM_TIMEOUT_SECONDS", d.llm_timeout_s)),
            llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", d.llm_max_tokens)),
            llm_temperature=float(os.getenv("LLM_TEMPERATURE", d.llm_temperature)),
            llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", d.llm_max_retries)),
            max_log_chars=int(os.getenv("MAX_LOG_CHARS", d.max_log_chars)),
            results_dir=os.getenv("RESULTS_DIR", d.results_dir),
        )

    def public_summary(self) -> dict:
        return {
            "classifier_backend": self.classifier_backend,
            "finetuned_model": self.finetuned_model or None,
            "classifier_fallback": self.classifier_fallback,
            "llm_backend": self.llm_backend,
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "api_key_configured": bool(self.llm_api_key),
            "embedding_model": self.embedding_model,
            "top_k": self.top_k,
            "max_distance": self.max_distance,
            "max_log_chars": self.max_log_chars,
        }
