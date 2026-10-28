# Prompt for Claude Code (paste as the first message, from inside the `oncall-ai` folder)

You are completing my ESE mini project **OnCall AI – Intelligent Production Incident Analyzer** end to end today. The foundation is already built and tested offline (read `CLAUDE.md` and `README.md` first, then skim `app/`, `data/`, `knowledge_base/`, `training/`, `tests/`). Do not redesign anything; make it run, train, deploy and document. Work phase by phase, verify each phase before moving on, and keep a running checklist in `CLAUDE.md`. Ask me only when you genuinely need something from me (keys, logins, running the Colab notebook). Never print or commit secrets.

My details: GitHub username `rachitst`; Hugging Face username `rachitst`; repo name `oncall-ai`; Space name `oncall-ai`; model repo `rachitst/oncall-ai-incident-classifier`. I have a Groq API key and a Hugging Face write token ready (ask me for them when needed; put them only in `.env` / Space secrets).

## Phase 0 — Environment and tests
1. Create a venv, install CPU torch first (`pip install torch --index-url https://download.pytorch.org/whl/cpu`), then `pip install -r requirements-dev.txt`.
2. Run `python data/generate_dataset.py` (must print 1200 total, 840/180/180) and `pytest -q` (must be all green). Fix any environment issue before continuing.

## Phase 1 — Run locally with the cloud LLM (no fine-tuned model yet)
1. Ask me for the Groq key. Create `.env` from `.env.example` with `LLM_API_KEY=<key>`, `CLASSIFIER_BACKEND=llm`, `LLM_MODEL=llama-3.3-70b-versatile` (if Groq returns 404 for that model, list models via `GET https://api.groq.com/openai/v1/models` and pick an available large chat model; update `.env.example`, `deploy/README_SPACE.md` and README accordingly).
2. Start `uvicorn app.api:app --host 127.0.0.1 --port 7860`, wait for `/health`, run `python scripts/smoke_test.py` — all rows must PASS (the cloud classifier should get all sample severities right; if one is off, that is acceptable, note it). Keep the server running and tell me the URL so I can check the UI myself. Wait for my OK.

## Phase 2 — GitHub
1. `git init`, confirm `git status` does NOT list `.env`, `models/`, `logs/`, `training/outputs/`. Commit everything (including `data/dataset/*.csv` and `results/` placeholders).
2. Create the public repo `rachitst/oncall-ai` with `gh repo create` if `gh` is available (else tell me the exact steps) and push `main`. Put the repo URL in README.

## Phase 3 — Training on Colab (I run it, you integrate)
1. Tell me exactly: open `training/OnCall_AI_Training.ipynb` in Colab, T4 GPU runtime, add secrets `HF_TOKEN` (write) and `GROQ_API_KEY`, confirm `REPO_URL`/`HF_MODEL_REPO` in Step 1 match my repo names, Runtime → Run all (~30–45 min), then download `oncall_results.zip` and give you the path. Also tell me to screenshot the Colab comparison table and charts for the report.
2. When I give you the zip: unzip into `results/` (overwrite), run `python eval/make_charts.py`, open `results/comparison_summary.md` and report the numbers to me. Verify the model exists at `https://huggingface.co/rachitst/oncall-ai-incident-classifier`. Commit and push `results/`.
3. If the notebook fails, debug the exact cell with me (common causes: bitsandbytes/CUDA version, `eval_strategy` vs `evaluation_strategy` in older transformers, Groq rate limits → reduce `N_LLM_EVAL`). Keep the fix in the notebook file and re-commit.

## Phase 4 — Fine-tuned classifier locally
1. Set `CLASSIFIER_BACKEND=finetuned` and `FINETUNED_MODEL=rachitst/oncall-ai-incident-classifier` in `.env`, restart the server, confirm `/health` shows `"classifier": "qlora_finetuned"`, run the smoke test, and record the per-request latency on CPU. If the model fails to load, fix the cause (usually the HF repo name or a missing `config.json`), never silently fall back.

## Phase 5 — Deploy to Hugging Face Spaces (free CPU, Docker SDK)
1. Ask me for the HF write token (use it only via `huggingface-cli login`/`HF_TOKEN` env, never commit it).
2. Create Space `rachitst/oncall-ai` with SDK `docker`, push the repository files to the Space (the Space README must be `deploy/README_SPACE.md` with its front matter; keep the GitHub README for GitHub). Exclude `training/outputs`, `logs`, `models`, `.env`.
3. Set Space **secrets** `LLM_API_KEY` and **variables** `FINETUNED_MODEL`, `CLASSIFIER_BACKEND=finetuned`, `CLASSIFIER_FALLBACK=llm`, `LLM_MODEL`, `LLM_BASE_URL` (use `huggingface_hub.HfApi().add_space_secret / add_space_variable`).
4. Wait for the build (check logs with `HfApi().get_space_runtime` or the Space page), then `curl <space-url>/health` and `python scripts/smoke_test.py <space-url>`. All rows must PASS. Put the Space URL and model URL into README and `app/ui.py` About text. Commit and push to GitHub.
5. If the build fails or the free CPU is too slow for the fine-tuned model (> 20 s per request), tell me, then set `CLASSIFIER_BACKEND=llm` on the Space as a temporary fallback so the demo works, and note it clearly for the report.

## Phase 6 — Screenshots for the report
Install Playwright (`pip install playwright && playwright install chromium`) and capture, at 1400×900, into `docs/screenshots/` with the file names listed in `docs/REPORT_STRUCTURE.md`: UI after analyzing samples 01, 05 and 07 (badge, root cause, sources accordion open, report accordion open), the Model comparison tab, the Architecture tab, Swagger `/docs`, a 200 response in Swagger, a 422 (empty log), and a 503 (start a second local server with an invalid key on port 7861 and call it). Also capture the GitHub repo page, the HF Space page (running) and the HF model page via the browser (ask me to log in if needed; mask any secret values). Commit the screenshots.

## Phase 7 — Hand-off for the report
Write `docs/RESULTS_SUMMARY.md` containing ONLY real measured values: dataset stats, the 5-way comparison table (from `results/comparison.json`), training config, training time / peak memory / trainable params per run, inference latency (Colab GPU and Space CPU), smoke-test table (local and Space), per-node timing example from one `/api/analyze` response, redaction example, and a list of every screenshot with a one-line caption. Then give me a final summary with the GitHub URL, Space URL, model URL, the test results, and anything that is incomplete or approximated.
