"""Prompt shared by training (Colab notebook) and inference (app). No third-party imports on purpose."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.taxonomy import INCIDENT_TYPE_IDS  # noqa: E402

CLASSIFY_SYSTEM = (
    "You are an SRE assistant. Classify the production log excerpt into exactly one incident_type from this list: "
    + ", ".join(INCIDENT_TYPE_IDS)
    + ". Then assign a severity: P1 (production outage, all/most users, core flow down, data at risk), "
      "P2 (production degraded for many users, partial impact), P3 (limited impact, single host, non-production, "
      "self-recovered), P4 (informational, single occurrence in dev, within baseline). "
      "Answer with JSON only: {\"incident_type\": \"...\", \"severity\": \"P1|P2|P3|P4\"}"
)


def classify_user_prompt(log_text: str) -> str:
    return f"TASK: classify\nLOG:\n{log_text}"


def label_json(incident_type: str, severity: str) -> str:
    return f'{{"incident_type": "{incident_type}", "severity": "{severity}"}}'
