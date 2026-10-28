# OnCall AI — Intelligent Production Incident Analyzer

> Paste a log excerpt, stack trace or alert. OnCall AI classifies the incident (type + severity) with a
> **QLoRA-fine-tuned Qwen2.5-0.5B**, retrieves the matching **runbook** with RAG, explains the root cause with a
> cloud LLM **verified against the runbook**, and drafts a blameless **incident report**, all orchestrated by a
> **LangGraph** workflow behind a **FastAPI** service with a **Gradio** interface.

**Author:** Rachit Manish Chheda (UID 2024301004) · LLM Production & Deployment, ESE mini project

| | |
|---|---|
| Source code | https://github.com/rachitst/oncall-ai |
| Live demo | _(add Hugging Face Space URL)_ |
| Fine-tuned model | _(add Hugging Face model URL)_ |
| API docs | `<space-url>/docs` |

## Concepts covered (from the lab experiments)

| Concept | Experiment | Where in this project |
|---|---|---|
| LoRA / QLoRA fine-tuning, 4-bit NF4 quantization, hyper-parameter comparison | Exp 2, 3 | `training/OnCall_AI_Training.ipynb` → `app/classifier.py` (`FinetunedClassifier`) |
| RAG over multiple file types with a vector index | Exp 4, 5 | `knowledge_base/` (Markdown runbooks, TXT policies, CSV known errors) → `app/knowledge.py` (FAISS) |
| LangGraph stateful workflow with conditional routing and fallbacks | Exp 6 | `app/workflow.py` |
| Production API: validation, error handling, logging, latency, cloud LLM, secrets, deployment | Exp 7 | `app/api.py`, `app/llm.py`, `Dockerfile`, Hugging Face Spaces |

## Architecture

```
client (browser / curl / any app)
   │ HTTP JSON  POST /api/analyze {"log_text": "...", "environment": "prod"}
   ▼
FastAPI service ──► LangGraph workflow
   │   ingest (redact secrets/PII) → classify (fine-tuned Qwen, CPU) ─┬─ confident ─► retrieve (FAISS RAG) → analyze (cloud LLM) → verify ─┬─ grounded ─► draft_report → END
   │                                                                  └─ low confidence ─► triage_fallback ─────────────────────────────────┘   └─ ungrounded ─► fallback_analysis ─┘
   ▼
Gradio UI mounted at "/"      ·      /health      ·      /docs (OpenAPI)
```

## Repository layout

```
app/            FastAPI service, Gradio UI, LangGraph workflow, RAG, classifiers, LLM backend, redaction
data/           taxonomy, synthetic dataset generator, generated train/val/test CSVs, UI sample logs
knowledge_base/ 12 runbooks (.md), severity policy / report template / postmortem guide (.txt), known errors (.csv)
training/       Colab notebook: 5-way comparison (rules, zero-shot 0.5B, cloud LLM, LoRA, QLoRA) + model export
eval/           chart generation from results/comparison.json
results/        comparison.json, figures/, predictions, smoke-test output (committed after training)
tests/          pytest suite (offline: mock LLM, hash embeddings, rules classifier)
scripts/        run_local.sh, smoke_test.py
deploy/         Hugging Face Space README (Docker SDK)
docs/           report outline
```

## Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-dev.txt
python data/generate_dataset.py                           # regenerates data/dataset (deterministic, seed 42)
cp .env.example .env                                      # add LLM_API_KEY (Groq) and FINETUNED_MODEL
pytest -q                                                 # offline tests
uvicorn app.api:app --host 127.0.0.1 --port 7860          # UI: http://127.0.0.1:7860  API docs: /docs
python scripts/smoke_test.py                              # end-to-end check of the running server
```

Without a fine-tuned model yet, set `CLASSIFIER_BACKEND=llm` (cloud LLM classifies) or `rules` (offline keywords).
Without any key, `LLM_BACKEND=mock EMBEDDING_MODEL=hash` runs everything offline (used by the tests).

## Training and comparison (Colab, T4)

Open `training/OnCall_AI_Training.ipynb` in Colab → GPU runtime → add secrets `HF_TOKEN` (write) and optionally
`GROQ_API_KEY` → set `REPO_URL` / `HF_MODEL_REPO` → Run all. It evaluates all approaches on the same 180-log test set,
writes `results/comparison.json` + charts, merges the QLoRA adapter and pushes the model to the Hub.
Then commit `results/` to this repository and set `FINETUNED_MODEL=<hf-repo>` in the deployment.

## Deployment (Hugging Face Spaces, Docker, free CPU)

1. Create a Space (SDK: **Docker**), copy `deploy/README_SPACE.md` to the Space as `README.md`, push this repository's files.
2. Space settings → Secrets: `LLM_API_KEY`; Variables: `FINETUNED_MODEL`, `CLASSIFIER_BACKEND=finetuned`, `CLASSIFIER_FALLBACK=llm`, `LLM_MODEL=qwen/qwen3.8-27b`, `LLM_BASE_URL=https://api.groq.com/openai/v1`.
3. The container starts `uvicorn app.api:app --port 7860`; `/health` reports the loaded components.

## API

| Request | Response |
|---|---|
| `GET /health` | `200` status, knowledge chunks, classifier, model, uptime |
| `POST /api/analyze` | `200` classification, analysis, passages, incident report, timings; `422` invalid input; `503` LLM provider failure |
| `GET /api/examples`, `GET /api/incident-types` | sample logs, taxonomy |

Every response carries `X-Request-ID` and `X-Response-Time-ms`. Logs (`logs/app.log`, rotating) record outcome, path,
timings and redaction counts, never the log text or the API key.

## Dataset note

The training data is **synthetic**: 1,200 log excerpts generated from hand-written templates that imitate nginx,
Kubernetes, PostgreSQL, systemd, Python and Java logs (12 incident types; severity derived from the blast radius
described in the text), with noise lines and randomised hosts/IPs/timestamps. See `data/generate_dataset.py`.
