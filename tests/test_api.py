import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app.api import app
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["knowledge_chunks"] > 50 and set(body["knowledge_file_types"]) == {".csv", ".md", ".txt"}
    assert "x-request-id" in r.headers and "x-response-time-ms" in r.headers


def test_examples_and_types(client):
    assert len(client.get("/api/examples").json()["examples"]) >= 5
    assert len(client.get("/api/incident-types").json()["incident_types"]) == 12


def test_analyze_supported(client):
    log = open("data/samples/01_database_pool_exhausted_prod.log").read()
    r = client.post("/api/analyze", json={"log_text": log, "environment": "prod"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["classification"]["incident_type"] == "database_connection_exhausted"
    assert b["classification"]["severity"] == "P1"
    assert b["path"][:3] == ["ingest", "classify", "retrieve"]
    assert b["passages"] and b["passages"][0]["source"] == "database_connection_exhausted.md"
    assert b["incident_report"].startswith("#")
    assert "total" in b["timings_ms"]


def test_analyze_redacts_before_llm(client):
    log = open("data/samples/04_python_keyerror_dev.log").read() + "\napi_key=gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
    b = client.post("/api/analyze", json={"log_text": log}).json()
    assert b["redaction_counts"].get("api_key") == 1 or b["redaction_counts"].get("password_kv") == 1
    assert "gsk_ABCDEFGH" not in json.dumps(b)


@pytest.mark.parametrize("payload", [{"log_text": ""}, {"log_text": "   "}, {}, {"log_text": 5}, {"log_text": "x" * 20001},
                                     {"log_text": "ok", "environment": "production"}])
def test_validation_errors(client, payload):
    r = client.post("/api/analyze", json=payload)
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_request"


def test_wrong_method_and_unknown_path(client):
    assert client.get("/api/analyze").status_code == 405
    assert client.get("/api/nope").status_code == 404
