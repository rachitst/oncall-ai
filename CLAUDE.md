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
LLM_API_KEY (Groq), LLM_MODEL, LLM_FALLBACK_MODEL, LLM_BASE_URL, CLASSIFIER_BACKEND=finetuned|llm|rules, FINETUNED_MODEL (HF repo id),
CLASSIFIER_FALLBACK, EMBEDDING_MODEL (or "hash" offline), RAG_TOP_K, RAG_MAX_DISTANCE, MAX_LOG_CHARS, DISABLE_UI.

## Status checklist (update as you go)
- [x] venv + deps installed (uv-managed Python 3.11 in .venv; torch 2.15 cpu, transformers 5.21, gradio 6.31), dataset 1200 = 840/180/180, `pytest -q` green (15 passed; added pytest.ini so scripts/smoke_test.py is not collected)
- [x] `.env` created with Groq key; LLM_MODEL=qwen/qwen3.8-27b (llama-3.3-70b-versatile retired from Groq); local server runs with CLASSIFIER_BACKEND=llm; smoke test 11/11 PASS (free tier 8k tokens/min -> Retry-After honoured, 2 retries)
- [x] GitHub repo pushed (public): https://github.com/rachitst/oncall-ai (Space + model links still to fill)
- [x] Colab notebook run (T4, 2026-10-28): results/comparison.json + figures committed; merged model on HF Hub (rachitst/oncall-ai-incident-classifier, config.json + 988 MB safetensors)
- [x] Local server runs with CLASSIFIER_BACKEND=finetuned (model loads from cache in ~5 s; ~15-20 s/classification on this no-AVX Celeron; Hub download was flaky -> resumable retry loop)
- [x] Deployed on Modal (HF Spaces needs PRO for Docker/Gradio on CPU -> 402): https://rachitst--oncall-ai-web.us-east.modal.run ; /health OK, smoke test 11/11 PASS classifier=qlora_finetuned, 4-5 s/classification on Modal CPU, cold start ~37 s; pinned to 1 container (Gradio session state)
- [x] Screenshots captured per docs/REPORT_STRUCTURE.md (UI from the live Modal app, Swagger 200/422/503, notebook crops, charts, GitHub, HF model, terminal renders); Modal dashboard shots need a logged-in browser

## Issues encountered (and the fixes kept in the repo)
- Groq retired `llama-3.3-70b-versatile`; `openai/gpt-oss-120b` spends the 80-token classifier budget on hidden reasoning. Switched to `qwen/qwen3.8-27b` everywhere.
- Groq free tier also caps each model at 200,000 tokens/day (rolling): the 27B model's quota ran out after the Colab baseline + repeated smoke tests -> `LLM_FALLBACK_MODEL=openai/gpt-oss-120b` is used automatically on a per-day 429 (the answering model is recorded in `analysis.model`).
- Groq free tier = 8,000 tokens/min: smoke-test bursts hit 429. Backend now honours `Retry-After` (<=30 s) with `LLM_MAX_RETRIES=2`; `SMOKE_PAUSE_S` spaces out samples.
- Invalid API key returned 200 with an empty template report (every node swallowed BackendError). Permanent kinds (missing/invalid key, unknown model) now raise -> HTTP 503; transient ones still degrade. Tests added.
- pytest collected `scripts/smoke_test.py` (filename pattern) -> `pytest.ini` with `testpaths = tests`.
- Hugging Face Spaces returned 402: Docker/Gradio Spaces on cpu-basic need a PRO plan. Live demo moved to Modal (`deploy/modal_app.py`); `scripts/deploy_space.py` kept for PRO accounts.
- Fine-tuned model misses hand-written sample 03 severity (P2 instead of P1, conf 0.999): the generator never phrases P1 as '100% of requests failing' -> documented as a synthetic-data distribution-shift limitation, smoke test left as FAIL on purpose (10/11).
- Local laptop (Celeron N4500, 2 cores, no AVX): 0.5B classifier ~17-19 s/request on CPU; int8 dynamic quantization crashes (Illegal instruction). CPU latency is measured on Modal instead.
- Colab notebook (fixes made on Colab and kept in `training/OnCall_AI_Training.ipynb`):
  - `pip uninstall torchao` in Step 2 (peft vs Colab's torchao 0.10).
  - `warmup_steps=16` instead of `warmup_ratio` (transformers 5.21 removed it).
  - Groq daily quota exhausted by repeated runs: Step 7 is quota-safe (`llm_max_retries=0`, stops after 3 consecutive 429s, reuses a saved predictions CSV); `N_LLM_EVAL` lowered to 90 for re-runs.
  - `.png` filter in the Step 12 display loop (`.gitkeep` in figures/).
