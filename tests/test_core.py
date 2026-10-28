import json
import pandas as pd
import pytest

from app.classifier import RulesClassifier, parse_label
from app.config import ROOT, Settings
from app.redact import redact


def test_redaction_hides_secrets_and_pii():
    text = ("password=Hunter2! token=abcdefghijklmnop user=rachit@shopnest.in card 4111 1111 1111 1111 "
            "phone +91 98765 43210 ip 203.0.113.9 internal 10.0.3.4 postgres://app:s3cret@db.internal/orders "
            "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnopqrstuvwxyz012345")
    out, counts = redact(text)
    for leaked in ["Hunter2", "rachit@", "4111", "98765", "203.0.113.9", "s3cret", "eyJhbGci"]:
        assert leaked not in out
    assert "10.0.3.4" in out           # private IPs are kept for diagnosis
    assert sum(counts.values()) >= 6


def test_parse_label_variants():
    assert parse_label('{"incident_type": "out_of_memory", "severity": "P2"}') == ("out_of_memory", "P2")
    assert parse_label("Looks like disk_space_full, I'd say P1.") == ("disk_space_full", "P1")
    assert parse_label("no idea") == (None, None)


def test_rules_classifier_on_dataset_is_reasonable():
    df = pd.read_csv(f"{ROOT}/data/dataset/test.csv")
    clf = RulesClassifier()
    acc = sum(clf.classify(t).incident_type == y for t, y in zip(df.log_text, df.incident_type)) / len(df)
    assert acc > 0.7, acc


def test_settings_hide_key():
    s = Settings(llm_api_key="gsk_secret_value_123456")
    assert "gsk_secret" not in repr(s) and "llm_api_key" not in s.public_summary()



def test_backend_falls_back_to_secondary_model_on_daily_quota(monkeypatch):
    import httpx
    from app.config import Settings
    from app.llm import OpenAICompatibleBackend
    calls = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        calls.append(body["model"])
        if body["model"] == "primary":
            return httpx.Response(429, json={"error": {"message": "Rate limit reached ... on tokens per day (TPD): Limit 200000"}})
        return httpx.Response(200, json={"model": "secondary", "choices": [{"message": {"content": "{\"ok\": true}"}}],
                                         "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    s = Settings(llm_api_key="k", llm_model="primary", llm_fallback_model="secondary", llm_max_retries=2)
    b = OpenAICompatibleBackend(s)
    b._client = httpx.Client(base_url="https://x", transport=httpx.MockTransport(handler))
    g = b.generate([{"role": "user", "content": "hi"}], json_mode=True)
    assert g.model == "secondary" and g.text == '{"ok": true}'
    assert calls == ["primary", "secondary"]          # no sleeps/retries on a daily-quota 429, one fallback call


def test_backend_per_minute_429_retries_then_falls_back(monkeypatch):
    import httpx
    from app.config import Settings
    from app.llm import OpenAICompatibleBackend
    import app.llm as llm_mod
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    calls = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        calls.append(body["model"])
        if body["model"] == "primary":
            return httpx.Response(429, headers={"retry-after": "1"}, json={"error": {"message": "tokens per minute (TPM)"}})
        return httpx.Response(200, json={"model": "secondary", "choices": [{"message": {"content": "ok"}}]})
    s = Settings(llm_api_key="k", llm_model="primary", llm_fallback_model="secondary", llm_max_retries=2)
    b = OpenAICompatibleBackend(s)
    b._client = httpx.Client(base_url="https://x", transport=httpx.MockTransport(handler))
    assert b.generate([{"role": "user", "content": "hi"}]).model == "secondary"
    assert calls == ["primary", "primary", "primary", "secondary"]
