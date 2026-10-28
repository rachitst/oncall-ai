"""Redaction of secrets and personal data from log text BEFORE it is sent to a cloud LLM or written to a report.

Patterns are deliberately conservative (false positives only hide a little context; false negatives leak data).
"""
from __future__ import annotations

import re

PATTERNS = [
    ("api_key", re.compile(r"\b(?:sk|gsk|ghp|xox[abp]|AKIA)[A-Za-z0-9_\-]{12,}\b")),
    ("bearer_token", re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-_\.=]{16,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\b")),
    ("password_kv", re.compile(r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|token)\s*[=:]\s*['\"]?([^\s'\",;]{4,})")),
    ("db_url_credentials", re.compile(r"(?i)\b(postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://([^:/\s]+):([^@\s]+)@")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("indian_phone", re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")),
    ("ipv4", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")),
]

KEEP_PRIVATE_IPS = True   # 10.x / 192.168.x / 127.x are kept: they carry no personal data and help diagnosis


def _is_private_ip(ip: str) -> bool:
    return ip.startswith(("10.", "192.168.", "127.", "172.16.", "172.17.", "172.18.", "172.19.", "172.2", "172.30.", "172.31."))


def redact(text: str) -> tuple[str, dict]:
    """Return (redacted_text, counts_by_category)."""
    counts: dict[str, int] = {}

    def bump(name: str) -> None:
        counts[name] = counts.get(name, 0) + 1

    for name, pattern in PATTERNS:
        if name == "ipv4":
            def ip_sub(m: re.Match) -> str:
                ip = m.group(0)
                if KEEP_PRIVATE_IPS and _is_private_ip(ip):
                    return ip
                bump(name)
                return "[REDACTED_IP]"
            text = pattern.sub(ip_sub, text)
        elif name == "bearer_token":
            def bearer_sub(m: re.Match) -> str:
                bump(name)
                return m.group(1) + "[REDACTED_TOKEN]"
            text = pattern.sub(bearer_sub, text)
        elif name == "password_kv":
            def kv_sub(m: re.Match) -> str:
                bump(name)
                return f"{m.group(1)}=[REDACTED]"
            text = pattern.sub(kv_sub, text)
        elif name == "db_url_credentials":
            def db_sub(m: re.Match) -> str:
                bump(name)
                return f"{m.group(1)}://[REDACTED_USER]:[REDACTED]@"
            text = pattern.sub(db_sub, text)
        else:
            placeholder = {"api_key": "[REDACTED_KEY]", "jwt": "[REDACTED_JWT]", "email": "[REDACTED_EMAIL]",
                           "credit_card": "[REDACTED_NUMBER]", "indian_phone": "[REDACTED_PHONE]"}[name]

            def generic_sub(m: re.Match, _p: str = placeholder, _n: str = name) -> str:
                bump(_n)
                return _p
            text = pattern.sub(generic_sub, text)
    return text, counts
