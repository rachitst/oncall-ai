"""Cloud LLM backend (OpenAI-compatible chat completions, e.g. Groq) plus an offline mock for tests.

Same design as Experiment 7: every provider failure becomes a BackendError with a safe category and no secrets.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from .config import Settings

logger = logging.getLogger("oncall.llm")


# Permanent failures: the service cannot produce a useful analysis until configuration is fixed -> HTTP 503.
# Everything else (timeouts, rate limits, 5xx, bad JSON) is transient and the workflow degrades gracefully.
FATAL_KINDS = {"configuration_missing_api_key", "authentication_failed", "model_or_endpoint_not_found"}


class BackendError(Exception):
    def __init__(self, kind: str, upstream_status: Optional[int] = None):
        super().__init__(kind)
        self.kind = kind
        self.upstream_status = upstream_status

    @property
    def fatal(self) -> bool:
        return self.kind in FATAL_KINDS


@dataclass
class Generation:
    text: str
    model: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    latency_ms: float = 0.0


def extract_json(text: str) -> Optional[dict]:
    """Find the first JSON object in a model reply (tolerates ```json fences and leading prose)."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = [fenced.group(1)] if fenced else []
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:i + 1])
                    break
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except ValueError:
            continue
    return None


class OpenAICompatibleBackend:
    def __init__(self, settings: Settings):
        self.settings = settings
        headers = {"Content-Type": "application/json"}
        if settings.llm_api_key:
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"
        self._client = httpx.Client(base_url=settings.llm_base_url, headers=headers,
                                    timeout=httpx.Timeout(settings.llm_timeout_s, connect=10.0))

    def generate(self, messages: list[dict], max_tokens: Optional[int] = None, json_mode: bool = False) -> Generation:
        if not self.settings.llm_api_key:
            raise BackendError("configuration_missing_api_key")
        payload = {"model": self.settings.llm_model, "messages": messages,
                   "temperature": self.settings.llm_temperature,
                   "max_tokens": max_tokens or self.settings.llm_max_tokens}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        attempt = 0
        t0 = time.perf_counter()
        while True:
            try:
                response = self._client.post("/chat/completions", json=payload)
            except httpx.TimeoutException:
                raise BackendError("timeout") from None
            except httpx.TransportError:
                raise BackendError("network_error") from None
            status = response.status_code
            if (status == 429 or status >= 500) and attempt < self.settings.llm_max_retries:
                attempt += 1
                try:
                    wait_s = min(30.0, float(response.headers.get("retry-after", "2")))
                except ValueError:
                    wait_s = 1.0
                logger.warning("llm_retry upstream_status=%s attempt=%d wait_s=%.1f", status, attempt, wait_s)
                time.sleep(wait_s)
                continue
            break
        if status in (401, 403):
            raise BackendError("authentication_failed", status)
        if status == 404:
            raise BackendError("model_or_endpoint_not_found", status)
        if status == 429:
            raise BackendError("rate_limited_or_quota_exceeded", status)
        if status >= 500:
            raise BackendError("provider_server_error", status)
        if status >= 400:
            # some providers reject response_format; retry once without it
            if json_mode:
                logger.warning("llm_json_mode_rejected upstream_status=%s; retrying without response_format", status)
                return self.generate(messages, max_tokens=max_tokens, json_mode=False)
            raise BackendError("request_rejected_by_provider", status)
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError):
            raise BackendError("invalid_provider_response", status) from None
        return Generation(text=text.strip(), model=data.get("model", self.settings.llm_model),
                          prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"),
                          latency_ms=(time.perf_counter() - t0) * 1000)

    def close(self) -> None:
        self._client.close()


class MockBackend:
    """Deterministic stand-in used by the tests and by LLM_BACKEND=mock (no key, no network)."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def generate(self, messages: list[dict], max_tokens: Optional[int] = None, json_mode: bool = False) -> Generation:
        user = messages[-1]["content"]
        if "TASK: classify" in user:
            from data.taxonomy import INCIDENT_TYPES  # local import to avoid a hard dependency at import time
            low = user.lower()
            best = max(INCIDENT_TYPES, key=lambda t: sum(k in low for k in INCIDENT_TYPES[t]["keywords"]))
            sev = "P1" if "[prod]" in low and ("all users" in low or "100%" in low or "revenue" in low) else \
                  "P2" if "[prod]" in low else "P3" if "[staging]" in low else "P4"
            return Generation(text=json.dumps({"incident_type": best, "severity": sev, "confidence": 0.8}), model="mock")
        if "TASK: analyze" in user:
            out = {
                "root_cause": "(mock) The connection pool was exhausted because pool_size x replicas exceeded max_connections after the traffic spike.",
                "evidence": ["FATAL: too many connections", "QueuePool limit reached"],
                "fix_steps": ["Terminate idle-in-transaction sessions", "Roll back the last deploy if it introduced the leak",
                              "Add PgBouncer and size pools below max_connections"],
                "grounded_in_runbook": True,
                "confidence": 0.85,
            }
            return Generation(text=json.dumps(out), model="mock")
        return Generation(text="# Incident report\n\n(mock) Service degraded; see analysis above.", model="mock")

    def close(self) -> None:
        pass


def create_backend(settings: Settings):
    if settings.llm_backend == "mock":
        return MockBackend(settings)
    if settings.llm_backend == "openai_compatible":
        return OpenAICompatibleBackend(settings)
    raise ValueError(f"Unknown LLM_BACKEND '{settings.llm_backend}'")
