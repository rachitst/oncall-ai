"""End-to-end check of a running OnCall AI server (local or deployed).

Usage: python scripts/smoke_test.py [http://127.0.0.1:7860]
Runs the sample incidents, a validation error and a wrong-method request, and prints a results table that can go
into the report. Saves results/smoke_test.json.
"""
import json, os, sys, time
import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7860").rstrip("/")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED = {"01": ("database_connection_exhausted", {"P1"}), "02": ("out_of_memory", {"P2", "P3"}), "03": ("tls_certificate_expired", {"P1"}),
            "04": ("application_exception", {"P4", "P3"}), "05": ("kubernetes_crashloop", {"P2"}), "06": ("rate_limit_exceeded", {"P2"})}
rows, records = [], []
r = httpx.get(f"{BASE}/health", timeout=60)
print("health:", r.status_code, r.json())
rows.append(("GET /health", "200 ok", f"{r.status_code} {r.json().get('status')}", r.status_code == 200))
for name in sorted(os.listdir(os.path.join(ROOT, "data", "samples"))):
    log = open(os.path.join(ROOT, "data", "samples", name)).read()
    t0 = time.perf_counter()
    r = httpx.post(f"{BASE}/api/analyze", json={"log_text": log}, timeout=180)
    ms = (time.perf_counter() - t0) * 1000
    b = r.json(); c = b.get("classification", {})
    exp = EXPECTED.get(name[:2])
    ok = r.status_code == 200 and (exp is None or (c.get("incident_type") == exp[0] and c.get("severity") in exp[1]))
    actual = f"{c.get('incident_type')} {c.get('severity')} conf {c.get('confidence')} grounded={b.get('grounded')} human={b.get('needs_human')} {ms:.0f}ms"
    rows.append((name, f"{exp[0]} {'/'.join(sorted(exp[1]))}" if exp else "any / needs_human", actual, ok))
    records.append({"sample": name, "status": r.status_code, "client_ms": round(ms, 1), "result": {k: b.get(k) for k in ("classification", "grounded", "needs_human", "path", "timings_ms", "llm_calls", "redaction_counts")}})
r = httpx.post(f"{BASE}/api/analyze", json={"log_text": ""}, timeout=30)
rows.append(("empty log", "422 invalid_request", f"{r.status_code} {r.json().get('error')}", r.status_code == 422))
r = httpx.post(f"{BASE}/api/analyze", json={"log_text": "x" * 20001}, timeout=30)
rows.append(("20,001-char log", "422 invalid_request", f"{r.status_code} {r.json().get('error')}", r.status_code == 422))
r = httpx.get(f"{BASE}/api/analyze", timeout=30)
rows.append(("GET /api/analyze", "405", str(r.status_code), r.status_code == 405))
print(f"\n{'Test':36s} {'Expected':40s} {'Pass':5s} Actual")
for name, exp, act, ok in rows:
    print(f"{name:36s} {exp:40s} {'PASS' if ok else 'FAIL':5s} {act}")
os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
json.dump({"base_url": BASE, "rows": [dict(test=n, expected=e, actual=a, passed=o) for n, e, a, o in rows], "records": records},
          open(os.path.join(ROOT, "results", "smoke_test.json"), "w"), indent=2)
sys.exit(0 if all(o for *_, o in rows) else 1)
