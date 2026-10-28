"""LangGraph incident-analysis workflow.

    START -> ingest -> classify -> (route) -> retrieve -> analyze -> verify -> (route) -> draft_report -> END
                                     |                                            |
                                     +--> triage_fallback ------------------------+--> (ungrounded) -> fallback_analysis -> draft_report

Nodes return only the fields they change; LangGraph merges them into IncidentState.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.taxonomy import INCIDENT_TYPES, SEVERITIES  # noqa: E402

from .classifier import Classification  # noqa: E402
from .config import Settings  # noqa: E402
from .knowledge import KnowledgeBase, Passage  # noqa: E402
from .llm import BackendError, extract_json  # noqa: E402
from .redact import redact  # noqa: E402

logger = logging.getLogger("oncall.workflow")

ANALYZE_SYSTEM = """You are a senior Site Reliability Engineer helping an on-call engineer.
Rules:
1. Use ONLY the RUNBOOK CONTEXT and the LOG to explain the incident. Do not invent commands, hosts or policies that are not in the context.
2. If the runbook context does not cover this incident, set "grounded_in_runbook": false and give only generic, safe triage advice.
3. Never include secrets, tokens or personal data in the output.
4. Reply with JSON only, with keys: root_cause (string, 2-4 sentences), evidence (list of 2-5 short quotes from the LOG),
   fix_steps (list of 3-6 imperative steps, most urgent first), grounded_in_runbook (true/false), confidence (0-1)."""

REPORT_SYSTEM = """You write concise, blameless incident reports for an engineering team, in Markdown, following the
INCIDENT REPORT TEMPLATE in the context. Use only facts present in the inputs. Keep it under 300 words.
Sections: Title, Severity, Status, Summary, Timeline (use the timestamps from the log), Root cause, Mitigation applied,
Action items (bullet list with suggested owners as roles, not names), Lessons learned."""


class IncidentState(TypedDict, total=False):
    raw_log: str
    environment_hint: str
    log_text: str
    redaction_counts: dict
    classification: dict
    passages: List[dict]
    analysis: dict
    grounded: bool
    incident_report: str
    needs_human: bool
    path: List[str]
    timings_ms: dict
    errors: List[str]
    llm_calls: int


def _add_timing(state: IncidentState, node: str, started: float) -> dict:
    timings = dict(state.get("timings_ms", {}))
    timings[node] = round((time.perf_counter() - started) * 1000, 1)
    path = list(state.get("path", [])) + [node]
    return {"timings_ms": timings, "path": path}


class IncidentWorkflow:
    def __init__(self, settings: Settings, knowledge: KnowledgeBase, classifier, backend):
        self.settings = settings
        self.knowledge = knowledge
        self.classifier = classifier
        self.backend = backend
        self.graph = self._build()

    # ------------------------------------------------------------------ nodes
    def ingest(self, state: IncidentState) -> dict:
        t0 = time.perf_counter()
        raw = state["raw_log"].strip()
        text = raw[: self.settings.max_log_chars]
        text, counts = redact(text)
        hint = (state.get("environment_hint") or "").strip().lower()
        if hint in {"prod", "staging", "dev"} and f"[{hint}]" not in text.lower():
            text = f"[environment hint: {hint}]\n" + text
        return {"log_text": text, "redaction_counts": counts, "errors": [], "llm_calls": 0,
                **_add_timing(state, "ingest", t0)}

    def classify(self, state: IncidentState) -> dict:
        t0 = time.perf_counter()
        try:
            c: Classification = self.classifier.classify(state["log_text"])
        except BackendError as exc:
            # classification via the cloud LLM failed -> keyword fallback keeps the service working
            from .classifier import RulesClassifier
            logger.error("classify_backend_error kind=%s; using rules fallback", exc.kind)
            c = RulesClassifier().classify(state["log_text"])
            c.method = "rules_fallback"
        llm_calls = state.get("llm_calls", 0) + (1 if c.method == "llm_prompting" else 0)
        return {"classification": {"incident_type": c.incident_type, "label": c.label, "severity": c.severity,
                                   "severity_meaning": SEVERITIES.get(c.severity, ""), "confidence": c.confidence,
                                   "method": c.method, "latency_ms": round(c.latency_ms, 1)},
                "llm_calls": llm_calls, **_add_timing(state, "classify", t0)}

    def route_after_classify(self, state: IncidentState) -> str:
        c = state["classification"]
        if c["confidence"] < self.settings.classifier_min_confidence:
            return "low_confidence"
        return "confident"

    def retrieve(self, state: IncidentState) -> dict:
        t0 = time.perf_counter()
        itype = state["classification"]["incident_type"]
        query = f"{INCIDENT_TYPES[itype]['label']}\n{state['log_text'][:1500]}"
        passages = self.knowledge.search(query, incident_type=itype)
        return {"passages": [p.__dict__ for p in passages], **_add_timing(state, "retrieve", t0)}

    def analyze(self, state: IncidentState) -> dict:
        t0 = time.perf_counter()
        context = "\n\n".join(f"[{i}] ({p['source']} - {p['section']})\n{p['text']}" for i, p in enumerate(state["passages"], 1))
        user = (f"TASK: analyze\nINCIDENT TYPE: {state['classification']['label']} (severity {state['classification']['severity']})\n\n"
                f"RUNBOOK CONTEXT:\n{context}\n\nLOG:\n{state['log_text'][:6000]}")
        errors = list(state.get("errors", []))
        analysis = None
        llm_calls = state.get("llm_calls", 0)
        for attempt in range(2):                      # one bounded retry if the reply is not valid JSON
            try:
                gen = self.backend.generate([{"role": "system", "content": ANALYZE_SYSTEM}, {"role": "user", "content": user}],
                                            json_mode=True)
                llm_calls += 1
                analysis = extract_json(gen.text)
                if analysis and "root_cause" in analysis:
                    analysis["model"] = gen.model
                    analysis["tokens"] = {"prompt": gen.prompt_tokens, "completion": gen.completion_tokens}
                    break
                errors.append(f"analyze: invalid JSON on attempt {attempt + 1}")
                user += "\n\nIMPORTANT: reply with a single valid JSON object only."
            except BackendError as exc:
                errors.append(f"analyze: backend {exc.kind}")
                break
        if analysis is None:
            analysis = {"root_cause": "", "evidence": [], "fix_steps": [], "grounded_in_runbook": False, "confidence": 0.0}
        analysis.setdefault("fix_steps", [])
        analysis.setdefault("evidence", [])
        return {"analysis": analysis, "errors": errors, "llm_calls": llm_calls, **_add_timing(state, "analyze", t0)}

    def verify(self, state: IncidentState) -> dict:
        """Grounding check: runbook distance within the gate, model says grounded, and the fix steps are non-empty."""
        t0 = time.perf_counter()
        a = state["analysis"]
        best = min((p["distance"] for p in state.get("passages", [])), default=99.0)
        gate_ok = self.settings.max_distance is None or best <= self.settings.max_distance
        grounded = bool(a.get("grounded_in_runbook")) and gate_ok and bool(a.get("root_cause")) and len(a.get("fix_steps", [])) >= 2
        return {"grounded": grounded, **_add_timing(state, "verify", t0)}

    def route_after_verify(self, state: IncidentState) -> str:
        return "grounded" if state.get("grounded") else "ungrounded"

    def triage_fallback(self, state: IncidentState) -> dict:
        """Low classifier confidence: still retrieve general guidance, but mark the incident for a human."""
        t0 = time.perf_counter()
        passages = self.knowledge.search(state["log_text"][:1500])
        return {"passages": [p.__dict__ for p in passages], "needs_human": True,
                "analysis": {"root_cause": "The classifier is not confident about this log. Treat it as unknown and follow "
                                           "the generic triage steps while a human reviews it.",
                             "evidence": [], "fix_steps": ["Confirm the affected service, environment and user impact",
                                                           "Check recent deployments and roll back if one correlates",
                                                           "Collect full logs and metrics for the time window",
                                                           "Escalate to the service owner per the severity policy"],
                             "grounded_in_runbook": False, "confidence": 0.0},
                "grounded": False, **_add_timing(state, "triage_fallback", t0)}

    def fallback_analysis(self, state: IncidentState) -> dict:
        """Analysis was not grounded in the runbooks: keep the classification but replace the advice with safe steps."""
        t0 = time.perf_counter()
        a = dict(state.get("analysis", {}))
        a["root_cause"] = (a.get("root_cause") or "") + "\n\nNOTE: this explanation could not be verified against the " \
                          "runbooks, so treat it as a hypothesis and confirm before acting."
        if len(a.get("fix_steps", [])) < 2:
            a["fix_steps"] = ["Check service health and recent deployments", "Collect logs and metrics for the window",
                              "Escalate to the service owner"]
        return {"analysis": a, "needs_human": True, **_add_timing(state, "fallback_analysis", t0)}

    def draft_report(self, state: IncidentState) -> dict:
        t0 = time.perf_counter()
        c, a = state["classification"], state["analysis"]
        template = [p for p in self.knowledge.search("incident report template sections", k=2) if "template" in p.source]
        template_text = template[0].text if template else ""
        user = (f"INCIDENT REPORT TEMPLATE:\n{template_text}\n\nCLASSIFICATION: {json.dumps(c)}\n\n"
                f"ANALYSIS: {json.dumps({k: a.get(k) for k in ('root_cause', 'evidence', 'fix_steps')})}\n\n"
                f"GROUNDED IN RUNBOOK: {state.get('grounded')}\nNEEDS HUMAN REVIEW: {state.get('needs_human', False)}\n\n"
                f"LOG (redacted):\n{state['log_text'][:4000]}")
        errors = list(state.get("errors", []))
        llm_calls = state.get("llm_calls", 0)
        try:
            gen = self.backend.generate([{"role": "system", "content": REPORT_SYSTEM}, {"role": "user", "content": user}])
            llm_calls += 1
            report = gen.text
        except BackendError as exc:
            errors.append(f"draft_report: backend {exc.kind}")
            report = self._template_report(state)
        if not report.strip().startswith("#"):
            report = f"# Incident report: {c['label']}\n\n" + report
        report += f"\n\n---\n_Generated by OnCall AI on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}; " \
                  f"classifier: {c['method']}; grounded: {state.get('grounded')}; redactions: {sum(state.get('redaction_counts', {}).values())}_"
        return {"incident_report": report, "errors": errors, "llm_calls": llm_calls,
                "needs_human": state.get("needs_human", False), **_add_timing(state, "draft_report", t0)}

    def _template_report(self, state: IncidentState) -> str:
        c, a = state["classification"], state["analysis"]
        steps = "\n".join(f"- {s}" for s in a.get("fix_steps", []))
        return (f"# Incident report: {c['label']}\n\n**Severity:** {c['severity']}  \n**Status:** Investigating\n\n"
                f"## Summary\n{a.get('root_cause') or 'Analysis unavailable (LLM backend error).'}\n\n"
                f"## Action items\n{steps or '- Escalate to the service owner'}\n")

    # ------------------------------------------------------------------ graph
    def _build(self):
        g = StateGraph(IncidentState)
        g.add_node("ingest", self.ingest)
        g.add_node("classify", self.classify)
        g.add_node("retrieve", self.retrieve)
        g.add_node("analyze", self.analyze)
        g.add_node("verify", self.verify)
        g.add_node("triage_fallback", self.triage_fallback)
        g.add_node("fallback_analysis", self.fallback_analysis)
        g.add_node("draft_report", self.draft_report)
        g.add_edge(START, "ingest")
        g.add_edge("ingest", "classify")
        g.add_conditional_edges("classify", self.route_after_classify,
                                {"confident": "retrieve", "low_confidence": "triage_fallback"})
        g.add_edge("retrieve", "analyze")
        g.add_edge("analyze", "verify")
        g.add_conditional_edges("verify", self.route_after_verify,
                                {"grounded": "draft_report", "ungrounded": "fallback_analysis"})
        g.add_edge("fallback_analysis", "draft_report")
        g.add_edge("triage_fallback", "draft_report")
        g.add_edge("draft_report", END)
        return g.compile()

    def run(self, raw_log: str, environment_hint: Optional[str] = None) -> IncidentState:
        t0 = time.perf_counter()
        state = self.graph.invoke({"raw_log": raw_log, "environment_hint": environment_hint or ""})
        state["timings_ms"] = {**state.get("timings_ms", {}), "total": round((time.perf_counter() - t0) * 1000, 1)}
        return state

    def mermaid(self) -> str:
        return self.graph.get_graph().draw_mermaid()
