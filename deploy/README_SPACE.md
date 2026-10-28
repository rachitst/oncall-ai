---
title: OnCall AI - Incident Analyzer
emoji: 🛠️
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: QLoRA + RAG + LangGraph production incident analyzer
---

# OnCall AI — Intelligent Production Incident Analyzer

Paste a log excerpt or stack trace: OnCall AI classifies the incident type and severity with a QLoRA-fine-tuned
Qwen2.5-0.5B, retrieves the matching runbook (RAG over Markdown/TXT/CSV with FAISS), explains the root cause with a
cloud LLM verified against the runbook, and drafts an incident report — orchestrated by a LangGraph workflow behind a
FastAPI service (`/docs`, `/health`).

Required Space settings — **Secrets:** `LLM_API_KEY` · **Variables:** `FINETUNED_MODEL`, `CLASSIFIER_BACKEND=finetuned`,
`LLM_MODEL=llama-3.3-70b-versatile`, `LLM_BASE_URL=https://api.groq.com/openai/v1`.

Author: Rachit Manish Chheda (UID 2024301004) · Source: GitHub `rachitst/oncall-ai`
