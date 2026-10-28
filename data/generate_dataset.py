"""Generate the labelled incident-log dataset used for fine-tuning and evaluation.

Each sample is a short multi-line log excerpt (as an on-call engineer would paste it) with two labels:
  * incident_type  - one of the 12 classes in taxonomy.py
  * severity       - P1..P4, derived from the blast radius described IN the log text
                     (environment, error rate, number of affected hosts/pods, whether users are affected),
                     so the model has to read the context, not just spot a keyword.

The logs are synthetic: they are produced from hand-written templates that imitate real nginx, Kubernetes,
PostgreSQL, systemd/journald, Python and Java log lines, with randomised hosts, IPs, timestamps, services and
numbers, plus interleaved unrelated INFO lines as noise. This is stated in the report.

Usage:  python data/generate_dataset.py --n 1200 --seed 42 --out data/dataset
Writes  train.csv / val.csv / test.csv (stratified 70/15/15) and dataset_stats.json
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taxonomy import ENVIRONMENTS, INCIDENT_TYPE_IDS  # noqa: E402

SERVICES = ["checkout-api", "payments-svc", "user-service", "order-worker", "search-api", "notification-svc",
            "inventory-api", "auth-gateway", "recommendation-svc", "billing-cron", "catalog-api", "report-worker"]
HOSTS = ["ip-10-0-{a}-{b}", "web-{n:02d}", "app-{n:02d}", "node-{n:02d}", "db-primary-{n}", "worker-{n:02d}"]
NAMESPACES = ["prod", "staging", "dev", "payments", "core", "platform"]
DOMAINS = ["api.shopnest.in", "payments.shopnest.in", "auth.shopnest.in", "cdn.shopnest.in", "db.internal",
           "redis.internal", "search.internal", "sso.internal"]
DBS = ["orders_db", "users_db", "payments_db", "catalog_db"]
NOISE_LINES = [
    "{ts} INFO  {service} health check ok (uptime {n}h)",
    "{ts} INFO  {service} GET /api/v1/items 200 {ms}ms",
    "{ts} INFO  {service} scheduled job 'cleanup' finished in {ms}ms",
    "{ts} DEBUG {service} cache hit ratio {pct}%",
    "{ts} INFO  kubelet Successfully pulled image for {service}",
    "{ts} INFO  {service} POST /api/v1/orders 201 {ms}ms",
    "{ts} INFO  {service} connection to {domain} established",
]

# ----------------------------------------------------------------------------- templates
# Each template: a list of lines. Placeholders filled by fill(). {scope} lines describe the blast radius.
T = {
    "database_connection_exhausted": [
        ["{ts} ERROR {service} sqlalchemy.exc.TimeoutError: QueuePool limit of size {pool} overflow {ovf} reached, connection timed out, timeout {to}",
         "{ts} ERROR {service} could not obtain connection from pool after {ms}ms (db={db})",
         "{scope}"],
        ["{ts} FATAL postgres[{pid}]: FATAL:  sorry, too many clients already",
         "{ts} FATAL postgres[{pid}]: FATAL:  remaining connection slots are reserved for non-replication superuser connections",
         "{ts} ERROR {service} psycopg2.OperationalError: FATAL:  too many connections for role \"app\"",
         "{scope}"],
        ["{ts} WARN  {service} HikariPool-1 - Connection is not available, request timed out after {ms}ms.",
         "{ts} ERROR {service} java.sql.SQLTransientConnectionException: HikariPool-1 - Connection is not available",
         "{ts} WARN  {service} HikariPool-1 - Thread starvation or clock leap detected (housekeeper delta={ms}ms).",
         "{scope}"],
        ["{ts} ERROR {service} pymysql.err.OperationalError: (1040, 'Too many connections')",
         "{ts} ERROR {service} db={db} active_connections={conns}/{maxconns} waiting={count}",
         "{scope}"],
    ],
    "out_of_memory": [
        ["{ts} kernel: [{pid}.{n}] Out of memory: Killed process {pid} ({proc}) total-vm:{kb}kB, anon-rss:{kb2}kB, file-rss:0kB",
         "{ts} kernel: oom-kill:constraint=CONSTRAINT_NONE,nodemask=(null),cpuset=/,mems_allowed=0,task={proc},pid={pid}",
         "{ts} systemd[1]: {service}.service: Main process exited, code=killed, status=9/KILL",
         "{scope}"],
        ["{ts} WARN  kubelet Pod {ns}/{service}-{hash} container {service} terminated: reason=OOMKilled exitCode=137",
         "{ts} INFO  kubelet Container {service} restarted (restart count {count}); memory limit {mb}Mi",
         "{scope}"],
        ["{ts} ERROR {service} java.lang.OutOfMemoryError: Java heap space",
         "{ts} ERROR {service} \tat java.base/java.util.Arrays.copyOf(Arrays.java:3512)",
         "{ts} ERROR {service} \tat com.shopnest.report.Exporter.buildRows(Exporter.java:{n})",
         "{scope}"],
        ["{ts} ERROR {service} Traceback (most recent call last):",
         "{ts} ERROR {service}   File \"/app/workers/{proc}.py\", line {n}, in build_batch",
         "{ts} ERROR {service} MemoryError: Unable to allocate {gb} GiB for an array with shape ({big}, 512)",
         "{scope}"],
    ],
    "disk_space_full": [
        ["{ts} ERROR {service} OSError: [Errno 28] No space left on device: '/var/log/{service}/app.log'",
         "{ts} CRIT  {service} disk usage on /var is {pct}% ({gb}G used, 0G free)",
         "{scope}"],
        ["{ts} ERROR postgres[{pid}]: PANIC:  could not write to file \"pg_wal/xlogtemp.{pid}\": No space left on device",
         "{ts} ERROR postgres[{pid}]: LOG:  database system is shut down",
         "{scope}"],
        ["{ts} WARN  kubelet Node {host} condition DiskPressure=True (ephemeral-storage {pct}% used)",
         "{ts} WARN  kubelet Evicting pod {ns}/{service}-{hash}: The node was low on resource: ephemeral-storage.",
         "{scope}"],
        ["{ts} ERROR {service} write /data/uploads/{hash}.tmp: ENOSPC: no space left on device",
         "{ts} WARN  node_exporter filesystem /data inodes_free=0 avail_bytes=0",
         "{scope}"],
    ],
    "upstream_gateway_error": [
        ["{ts} [error] {pid}#0: *{n} connect() failed (111: Connection refused) while connecting to upstream, client: {ip}, server: {domain}, request: \"GET /api/v1/cart HTTP/1.1\", upstream: \"http://10.0.{a}.{b}:8080/api/v1/cart\"",
         "{ts} {ip} - - \"GET /api/v1/cart HTTP/1.1\" 502 157 \"-\" \"Mozilla/5.0\"",
         "{scope}"],
        ["{ts} [error] {pid}#0: *{n} upstream prematurely closed connection while reading response header from upstream, client: {ip}, server: {domain}, request: \"POST /api/v1/checkout HTTP/1.1\"",
         "{ts} {ip} - - \"POST /api/v1/checkout HTTP/1.1\" 502 0",
         "{scope}"],
        ["{ts} [error] {pid}#0: *{n} no live upstreams while connecting to upstream, client: {ip}, server: {domain}, request: \"GET / HTTP/1.1\", upstream: \"http://{service}/\"",
         "{ts} ALERT ingress 5xx_rate={pct}% on {domain} (502 Bad Gateway)",
         "{scope}"],
        ["{ts} [error] {pid}#0: *{n} upstream timed out (110: Connection timed out) while reading response header from upstream, client: {ip}, server: {domain}, request: \"GET /api/v1/search?q=shoes HTTP/1.1\"",
         "{ts} {ip} - - \"GET /api/v1/search?q=shoes HTTP/1.1\" 504 0",
         "{scope}"],
    ],
    "tls_certificate_expired": [
        ["{ts} ERROR {service} requests.exceptions.SSLError: HTTPSConnectionPool(host='{domain}', port=443): Max retries exceeded (Caused by SSLError(SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: certificate has expired (_ssl.c:1006)')))",
         "{scope}"],
        ["{ts} [error] {pid}#0: *{n} SSL_do_handshake() failed (SSL: error:0A000415:SSL routines::sslv3 alert certificate expired) while SSL handshaking to upstream, upstream: \"https://{domain}:443/\"",
         "{scope}"],
        ["{ts} ERROR {service} x509: certificate has expired or is not yet valid: current time {ts} is after {expiry}",
         "{ts} ERROR {service} Get \"https://{domain}/v1/token\": x509: certificate has expired",
         "{scope}"],
        ["{ts} WARN  cert-monitor certificate for {domain} expired on {expiry} (NotAfter); TLS handshake failures rising",
         "{ts} ERROR {service} curl: (60) SSL certificate problem: certificate has expired",
         "{scope}"],
    ],
    "kubernetes_crashloop": [
        ["{ts} WARN  kubelet Back-off restarting failed container {service} in pod {service}-{hash}_{ns}",
         "{ts} INFO  kubectl pod {service}-{hash} status CrashLoopBackOff restarts={count} age={n}m",
         "{scope}"],
        ["{ts} WARN  kubelet Liveness probe failed: Get \"http://10.0.{a}.{b}:8080/health\": dial tcp 10.0.{a}.{b}:8080: connect: connection refused",
         "{ts} INFO  kubelet Container {service} failed liveness probe, will be restarted",
         "{ts} INFO  kubectl {service}-{hash} 0/1 CrashLoopBackOff {count} {n}m",
         "{scope}"],
        ["{ts} ERROR {service} panic: runtime error: invalid memory address or nil pointer dereference",
         "{ts} ERROR {service} goroutine 1 [running]: main.initConfig(...) /app/cmd/main.go:{n}",
         "{ts} WARN  kubelet Back-off restarting failed container {service} (exit code 2)",
         "{scope}"],
        ["{ts} WARN  kubelet Readiness probe failed: HTTP probe failed with statuscode: 503",
         "{ts} WARN  kubelet Back-off restarting failed container {service} in pod {service}-{hash}_{ns}; restart count {count}",
         "{scope}"],
    ],
    "application_exception": [
        ["{ts} ERROR {service} Traceback (most recent call last):",
         "{ts} ERROR {service}   File \"/app/api/orders.py\", line {n}, in get_order",
         "{ts} ERROR {service}     total = order[\"items\"][0][\"price\"]",
         "{ts} ERROR {service} KeyError: 'price'",
         "{scope}"],
        ["{ts} ERROR {service} Traceback (most recent call last):",
         "{ts} ERROR {service}   File \"/app/services/user.py\", line {n}, in display_name",
         "{ts} ERROR {service}     return user.profile.name.strip()",
         "{ts} ERROR {service} AttributeError: 'NoneType' object has no attribute 'strip'",
         "{scope}"],
        ["{ts} ERROR {service} java.lang.NullPointerException: Cannot invoke \"com.shopnest.Cart.getItems()\" because \"cart\" is null",
         "{ts} ERROR {service} \tat com.shopnest.checkout.CheckoutService.total(CheckoutService.java:{n})",
         "{scope}"],
        ["{ts} ERROR {service} Unhandled exception in request POST /api/v1/payments: TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'",
         "{ts} ERROR {service}   File \"/app/api/payments.py\", line {n}, in apply_discount",
         "{scope}"],
    ],
    "dns_resolution_failure": [
        ["{ts} ERROR {service} socket.gaierror: [Errno -3] Temporary failure in name resolution (host={domain})",
         "{ts} ERROR {service} requests.exceptions.ConnectionError: HTTPSConnectionPool(host='{domain}', port=443): Max retries exceeded",
         "{scope}"],
        ["{ts} ERROR {service} Error: getaddrinfo ENOTFOUND {domain}",
         "{ts} ERROR {service}     at GetAddrInfoReqWrap.onlookup [as oncomplete] (node:dns:{n}:26)",
         "{scope}"],
        ["{ts} WARN  coredns [ERROR] plugin/errors: 2 {domain}. A: read udp 10.0.{a}.{b}:{port}->10.0.0.2:53: i/o timeout",
         "{ts} ERROR {service} dial tcp: lookup {domain} on 10.0.0.10:53: server misbehaving",
         "{scope}"],
        ["{ts} ERROR {service} curl: (6) Could not resolve host: {domain}",
         "{ts} WARN  resolver NXDOMAIN for {domain} (ttl 0)",
         "{scope}"],
    ],
    "rate_limit_exceeded": [
        ["{ts} WARN  {service} HTTP 429 Too Many Requests from https://{domain}/v1/charges (retry-after: {n}s)",
         "{ts} WARN  {service} provider rate limit hit: {count} requests in 60s (limit {maxconns})",
         "{scope}"],
        ["{ts} {ip} - - \"POST /api/v1/login HTTP/1.1\" 429 85 \"-\" \"python-requests/2.31\"",
         "{ts} WARN  api-gateway rate limit exceeded for client {ip}: {count} req/min > {maxconns} req/min, throttling",
         "{scope}"],
        ["{ts} ERROR {service} openai.RateLimitError: Error code: 429 - {{'error': {{'message': 'Rate limit reached for model on tokens per minute. Limit {maxconns}, used {count}', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}}}",
         "{scope}"],
        ["{ts} WARN  {service} ThrottlingException: Rate exceeded (Service: AmazonSQS; Status Code: 400; Error Code: Throttling)",
         "{ts} WARN  {service} backing off {n}s before retry ({count} throttled calls in last minute)",
         "{scope}"],
    ],
    "authentication_failure": [
        ["{ts} WARN  {service} 401 Unauthorized: JWT signature verification failed for sub={hash} (kid=prod-2024)",
         "{ts} WARN  {service} jwt.exceptions.InvalidSignatureError: Signature verification failed",
         "{scope}"],
        ["{ts} WARN  {service} 401 Unauthorized: token expired at {expiry} for client_id=mobile-app",
         "{ts} WARN  {service} jwt.exceptions.ExpiredSignatureError: Signature has expired",
         "{scope}"],
        ["{ts} sshd[{pid}]: Failed password for invalid user admin from {ip} port {port} ssh2",
         "{ts} sshd[{pid}]: Failed password for root from {ip} port {port} ssh2",
         "{ts} sshd[{pid}]: message repeated {count} times: [ Failed password for root from {ip} port {port} ssh2]",
         "{scope}"],
        ["{ts} ERROR {service} 403 Forbidden: service account {service}@shopnest.iam does not have permission storage.objects.get on bucket shopnest-{env}-assets",
         "{ts} ERROR {service} google.api_core.exceptions.Forbidden: 403 GET https://storage.googleapis.com/...: Access denied",
         "{scope}"],
    ],
    "high_latency_timeout": [
        ["{ts} ALERT prometheus p99 latency for {service} = {latency}ms (threshold 800ms) for {n}m",
         "{ts} WARN  {service} request GET /api/v1/search took {latency}ms (slow)",
         "{scope}"],
        ["{ts} LOG   postgres[{pid}]: duration: {latency}.{n} ms  statement: SELECT * FROM orders o JOIN order_items i ON i.order_id = o.id WHERE o.user_id = $1",
         "{ts} WARN  {service} slow query detected ({latency}ms) on db={db}; lock_wait={ms}ms",
         "{scope}"],
        ["{ts} ERROR {service} grpc: rpc error: code = DeadlineExceeded desc = context deadline exceeded (timeout {to}s) calling inventory.Reserve",
         "{ts} WARN  {service} {count} requests exceeded deadline in the last minute",
         "{scope}"],
        ["{ts} ERROR {service} httpx.ReadTimeout: timed out after {to}s waiting for https://{domain}/v1/quote",
         "{ts} WARN  {service} upstream response time p95={latency}ms p99={latency2}ms (baseline 120ms)",
         "{scope}"],
    ],
    "deployment_failure": [
        ["{ts} WARN  kubelet Failed to pull image \"registry.shopnest.in/{service}:v{n}.{a}.{b}\": rpc error: code = NotFound desc = manifest unknown",
         "{ts} INFO  kubectl {service}-{hash} 0/1 ImagePullBackOff 0 {n}m",
         "{scope}"],
        ["{ts} ERROR deploy-bot Deployment \"{service}\" exceeded its progress deadline (progressDeadlineSeconds=600)",
         "{ts} INFO  deploy-bot rolling back {service} to revision {n}",
         "{scope}"],
        ["{ts} ERROR migrate alembic.util.exc.CommandError: Can't locate revision identified by '{hash}'",
         "{ts} ERROR deploy-bot pre-deploy migration failed for {service}; deployment aborted",
         "{scope}"],
        ["{ts} ERROR helm Error: UPGRADE FAILED: timed out waiting for the condition (release {service}, chart {service}-{n}.{a}.{b})",
         "{ts} INFO  helm rollback {service} to revision {count} started",
         "{scope}"],
    ],
}

# Blast-radius sentences. Each carries the severity the generator assigns.
SCOPE = {
    "P1": [
        "{ts} ALERT pagerduty [{env}] {service}: error rate {bigpct}% across all {hostsN} hosts; checkout unavailable for all users",
        "{ts} ALERT statuspage [{env}] incident opened: {service} down, 100% of requests failing since {ts}",
        "{ts} ALERT oncall [{env}] {hostsN}/{hostsN} replicas affected, customer-facing API returning errors, revenue impact",
        "{ts} CRIT  monitor [{env}] primary database unavailable; all write traffic failing on {hostsN} nodes",
    ],
    "P2": [
        "{ts} ALERT monitor [{env}] {service}: error rate {midpct}% on {fewN} of {hostsN} hosts; some users affected",
        "{ts} WARN  oncall [{env}] degraded: {service} succeeding after retries, p95 latency elevated for {pct}% of users",
        "{ts} ALERT monitor [{env}] {fewN} pods of {service} unhealthy, traffic shifted to remaining replicas, partial impact",
        "{ts} WARN  monitor [{env}] background jobs for {service} delayed by {n} min; customer-facing API healthy",
    ],
    "P3": [
        "{ts} INFO  monitor [{env}] {service}: {count} errors in the last hour on 1 host; no customer impact reported",
        "{ts} INFO  monitor [{env}] non-production environment {env}; QA test run affected only",
        "{ts} INFO  monitor [{env}] {service} recovered automatically after {n} min; error rate back to {lowpct}%",
        "{ts} INFO  oncall [{env}] intermittent; {count} occurrences today, retries succeed, no SLA impact",
    ],
    "P4": [
        "{ts} INFO  monitor [{env}] single occurrence on dev host {host}; no users on this environment",
        "{ts} DEBUG monitor [{env}] seen once during local test run by developer; informational",
        "{ts} INFO  monitor [{env}] rate {lowpct}% within normal baseline; no action required by policy",
        "{ts} INFO  monitor [{env}] one-off event in {env}, already resolved by auto-restart; logged for record",
    ],
}

SEVERITY_BY_ENV = {"prod": ["P1", "P2", "P2", "P3"], "staging": ["P2", "P3", "P3", "P4"], "dev": ["P3", "P4", "P4"]}


def next_ts(rng: random.Random, ctx: dict) -> str:
    """Monotonic timestamps: each line is 1-9 seconds after the previous one."""
    ctx["_offset"] = ctx.get("_offset", 0) + rng.randint(1, 9)
    return (ctx["base"] + timedelta(seconds=ctx["_offset"])).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def fill(line: str, rng: random.Random, ctx: dict) -> str:
    ts = next_ts(rng, ctx)
    values = {k: v for k, v in ctx.items() if not k.startswith("_")}
    values["ts"] = ts
    return line.format(**values)


def make_context(rng: random.Random, env: str) -> dict:
    a, b = rng.randint(1, 250), rng.randint(1, 250)
    host_t = rng.choice(HOSTS)
    n = rng.randint(1, 48)
    latency = rng.randint(900, 9000)
    return dict(
        base=datetime(2026, rng.randint(1, 10), rng.randint(1, 28), rng.randint(0, 23), rng.randint(0, 59)),
        service=rng.choice(SERVICES), host=host_t.format(a=a, b=b, n=n), ns=rng.choice(NAMESPACES),
        domain=rng.choice(DOMAINS), db=rng.choice(DBS), ip=f"{rng.randint(11, 220)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
        a=a, b=b, n=n, pid=rng.randint(100, 65000), port=rng.randint(1024, 65000), hash=f"{rng.getrandbits(40):010x}"[:10],
        ms=rng.randint(30, 30000), to=rng.choice([5, 10, 15, 30]), pool=rng.choice([5, 10, 20]), ovf=rng.choice([0, 10, 20]),
        conns=rng.randint(95, 100), maxconns=rng.choice([100, 200, 500, 1000, 60]), count=rng.randint(2, 900),
        kb=rng.randint(2_000_000, 9_000_000), kb2=rng.randint(1_500_000, 7_000_000), mb=rng.choice([256, 512, 1024, 2048]),
        gb=rng.randint(2, 64), big=rng.randint(2_000_000, 9_000_000), proc=rng.choice(["gunicorn", "celery", "java", "node", "uvicorn", "report_builder"]),
        pct=rng.randint(85, 100), bigpct=rng.randint(60, 100), midpct=rng.randint(8, 45), lowpct=round(rng.uniform(0.01, 0.9), 2),
        latency=latency, latency2=latency + rng.randint(500, 4000), expiry=f"2026-{rng.randint(1, 9):02d}-{rng.randint(1, 28):02d}T00:00:00Z",
        env=env, hostsN=rng.choice([3, 4, 6, 8, 12]), fewN=rng.choice([1, 2, 3]),
    )


def build_sample(rng: random.Random, incident_type: str, env: str, severity: str) -> str:
    ctx = make_context(rng, env)
    template = rng.choice(T[incident_type])
    lines = []
    for line in template:
        if line == "{scope}":
            lines.append(fill(rng.choice(SCOPE[severity]), rng, ctx))
        else:
            lines.append(fill(line, rng, ctx))
    # interleave 0-2 unrelated noise lines at random positions (never before the first line)
    for _ in range(rng.choice([0, 1, 1, 2])):
        pos = rng.randint(1, len(lines))
        lines.insert(pos, fill(rng.choice(NOISE_LINES), rng, ctx))
    # keep timestamps monotonic after inserting noise lines
    stamped = [l for l in lines if l[:4].isdigit()]
    if len(stamped) == len(lines):
        stamps = sorted(l.split(" ", 1)[0] for l in lines)
        lines = [st + " " + l.split(" ", 1)[1] for st, l in zip(stamps, lines)]
    # occasionally drop the timestamps, as engineers often paste logs without them
    if rng.random() < 0.15:
        lines = [l.split(" ", 1)[1] if l[:4].isdigit() else l for l in lines]
    return "\n".join(lines)


def generate(n: int, seed: int) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    per_type = n // len(INCIDENT_TYPE_IDS)
    # balanced cycle of (environment, severity) pairs so every incident type has every severity well represented
    combos = [(env, sev) for env in ("prod", "prod", "staging", "dev") for sev in SEVERITY_BY_ENV[env]]
    for t in INCIDENT_TYPE_IDS:
        for i in range(per_type):
            env, sev = combos[i % len(combos)]
            rows.append({"log_text": build_sample(rng, t, env, sev), "incident_type": t, "severity": sev, "environment": env})
    df = pd.DataFrame(rows).sample(frac=1.0, random_state=seed).reset_index(drop=True)
    df.insert(0, "id", [f"inc-{i:04d}" for i in range(len(df))])
    return df


def split(df: pd.DataFrame, seed: int):
    from sklearn.model_selection import train_test_split
    strat = df["incident_type"] + "|" + df["severity"]
    train, rest = train_test_split(df, test_size=0.30, random_state=seed, stratify=strat)
    strat_rest = rest["incident_type"] + "|" + rest["severity"]
    val, test = train_test_split(rest, test_size=0.50, random_state=seed, stratify=strat_rest)
    return train.reset_index(drop=True), val.reset_index(drop=True), test.reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset"))
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    df = generate(args.n, args.seed)
    assert df["log_text"].nunique() == len(df), "duplicate samples generated"
    train, val, test = split(df, args.seed)
    for name, part in [("train", train), ("val", val), ("test", test)]:
        part.to_csv(os.path.join(args.out, f"{name}.csv"), index=False)
    stats = {
        "total": len(df), "train": len(train), "val": len(val), "test": len(test),
        "incident_types": df["incident_type"].value_counts().to_dict(),
        "severity": df["severity"].value_counts().to_dict(),
        "environment": df["environment"].value_counts().to_dict(),
        "avg_lines": round(float(df["log_text"].str.count("\n").mean() + 1), 2),
        "avg_chars": round(float(df["log_text"].str.len().mean()), 1),
        "seed": args.seed,
    }
    with open(os.path.join(args.out, "dataset_stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
