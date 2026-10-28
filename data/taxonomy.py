"""Incident taxonomy shared by the dataset generator, the classifier, the knowledge base and the UI."""

INCIDENT_TYPES = {
    "database_connection_exhausted": {
        "label": "Database connection pool exhausted",
        "runbook": "database_connection_exhausted.md",
        "keywords": ["too many connections", "connection pool", "pool exhausted", "could not obtain connection",
                     "QueuePool limit", "FATAL: sorry", "remaining connection slots"],
    },
    "out_of_memory": {
        "label": "Out of memory (OOM)",
        "runbook": "out_of_memory.md",
        "keywords": ["out of memory", "oomkilled", "oom-killer", "killed process", "memoryerror",
                     "outofmemoryerror", "cannot allocate memory", "exit code 137"],
    },
    "disk_space_full": {
        "label": "Disk space exhausted",
        "runbook": "disk_space_full.md",
        "keywords": ["no space left on device", "disk usage", "enospc", "filesystem full", "inodes", "100% full"],
    },
    "upstream_gateway_error": {
        "label": "Upstream / gateway failure (502/504)",
        "runbook": "upstream_gateway_error.md",
        "keywords": ["502", "504 gateway", "upstream prematurely closed", "connect() failed", "while connecting to upstream",
                     "bad gateway", "no live upstreams"],
    },
    "tls_certificate_expired": {
        "label": "TLS certificate expired / invalid",
        "runbook": "tls_certificate_expired.md",
        "keywords": ["certificate has expired", "certificate verify failed", "x509", "ssl_error", "certificate_verify_failed",
                     "notafter", "tls handshake"],
    },
    "kubernetes_crashloop": {
        "label": "Kubernetes CrashLoopBackOff",
        "runbook": "kubernetes_crashloop.md",
        "keywords": ["crashloopbackoff", "back-off restarting", "liveness probe failed", "readiness probe failed",
                     "container restarted", "restart count"],
    },
    "application_exception": {
        "label": "Unhandled application exception",
        "runbook": "application_exception.md",
        "keywords": ["traceback (most recent call last)", "keyerror", "attributeerror", "nullpointerexception",
                     "typeerror", "unhandled exception", "indexerror", "nonetype"],
    },
    "dns_resolution_failure": {
        "label": "DNS resolution failure",
        "runbook": "dns_resolution_failure.md",
        "keywords": ["name resolution", "nxdomain", "getaddrinfo", "enotfound", "could not resolve host",
                     "name or service not known", "dns lookup"],
    },
    "rate_limit_exceeded": {
        "label": "Rate limit / quota exceeded",
        "runbook": "rate_limit_exceeded.md",
        "keywords": ["429", "too many requests", "rate limit", "quota exceeded", "throttl", "retry-after"],
    },
    "authentication_failure": {
        "label": "Authentication failure / credential issue",
        "runbook": "authentication_failure.md",
        "keywords": ["401", "invalid token", "jwt expired", "signature verification failed", "authentication failed",
                     "invalid credentials", "failed password", "403 forbidden"],
    },
    "high_latency_timeout": {
        "label": "High latency / request timeouts",
        "runbook": "high_latency_timeout.md",
        "keywords": ["p99", "latency", "timed out", "timeout exceeded", "slow query", "deadline exceeded",
                     "upstream timed out", "duration:"],
    },
    "deployment_failure": {
        "label": "Deployment / rollout failure",
        "runbook": "deployment_failure.md",
        "keywords": ["imagepullbackoff", "errimagepull", "migration failed", "rollout", "rolling back", "helm",
                     "deployment exceeded its progress deadline", "manifest unknown"],
    },
}

SEVERITIES = {
    "P1": "Critical - production outage or data at risk; page on-call immediately",
    "P2": "Major - production degraded for many users; respond within 30 minutes",
    "P3": "Minor - limited impact or non-production; handle in working hours",
    "P4": "Low - informational, single occurrence, no user impact",
}

ENVIRONMENTS = ["prod", "staging", "dev"]

INCIDENT_TYPE_IDS = list(INCIDENT_TYPES.keys())
SEVERITY_IDS = list(SEVERITIES.keys())
