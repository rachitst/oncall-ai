# CLAUDE.md — project instructions for Claude Code

## What this is
OnCall AI: ESE mini project (LLM Production & Deployment) by Rachit Manish Chheda (UID 2024301004).
Deadline is immediate; the goal is a working, deployed, documented demo — not perfection.

## Ground rules
- Never print, log or commit secrets. `.env` is git-ignored; keys live in `.env` locally and in Hugging Face Space secrets.
- Before pushing: `git status` must not list `.env`, `models/`, `logs/` or `training/outputs/`.
- Do not change the dataset generator seed or the taxonomy (training/evaluation depend on them).
- Keep `app/prompts.py` identical to what the notebook trained with.
- All numbers in docs/report must come from real runs (results/comparison.json, results/smoke_test.json). Never invent metrics.
- Prefer small, verified steps: run `pytest -q` and `python scripts/smoke_test.py` after any change.

## Commands
- Tests (offline, no key):        `pytest -q`
- Run locally:                    `uvicorn app.api:app --host 127.0.0.1 --port 7860`
- Offline demo (no key):          `LLM_BACKEND=mock EMBEDDING_MODEL=hash CLASSIFIER_BACKEND=rules uvicorn app.api:app --port 7860`
- Smoke test a running server:    `python scripts/smoke_test.py http://127.0.0.1:7860`
- Regenerate dataset:             `python data/generate_dataset.py`
- Charts from training results:   `python eval/make_charts.py`

## Configuration (env vars)
LLM_API_KEY (Groq), LLM_MODEL, LLM_BASE_URL, CLASSIFIER_BACKEND=finetuned|llm|rules, FINETUNED_MODEL (HF repo id),
CLASSIFIER_FALLBACK, EMBEDDING_MODEL (or "hash" offline), RAG_TOP_K, RAG_MAX_DISTANCE, MAX_LOG_CHARS, DISABLE_UI.

## Status checklist (update as you go)
- [x] venv + deps installed (uv-managed Python 3.11 in .venv; torch 2.15 cpu, transformers 5.21, gradio 6.31), dataset 1200 = 840/180/180, `pytest -q` green (15 passed; added pytest.ini so scripts/smoke_test.py is not collected)
- [x] `.env` created with Groq key; LLM_MODEL=qwen/qwen3.8-27b (llama-3.3-70b-versatile retired from Groq); local server runs with CLASSIFIER_BACKEND=llm; smoke test 11/11 PASS (free tier 8k tokens/min -> Retry-After honoured, 2 retries)
- [ ] GitHub repo pushed (public), README links filled
- [ ] Colab notebook run: results/comparison.json + figures committed; model on HF Hub
- [ ] Local server runs with CLASSIFIER_BACKEND=finetuned (model loads on CPU)
- [ ] Hugging Face Space deployed, /health OK, smoke test passes against the Space URL
- [ ] Screenshots captured per docs/REPORT_STRUCTURE.md
