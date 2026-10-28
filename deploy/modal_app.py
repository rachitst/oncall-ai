"""Deploy OnCall AI on Modal (serverless containers; free monthly credits, no card needed).

Hugging Face Spaces now require a PRO plan for Docker/Gradio Spaces on CPU, so the same FastAPI + Gradio app that the
Dockerfile runs is served here instead. The image mirrors the Dockerfile (python 3.11, CPU torch, requirements.txt).

One-time:   modal setup                                   # browser login
            modal secret create oncall-ai LLM_API_KEY=... # Groq key (or --from-dotenv with a file holding only that key)
Deploy:     modal deploy deploy/modal_app.py              # -> https://<workspace>--oncall-ai-web.modal.run
Dev:        modal serve  deploy/modal_app.py              # temporary URL with live reload

Configuration lives in IMAGE_ENV below (the Space "Variables"); the API key is the Modal secret (the Space "Secret").
Hugging Face downloads (fine-tuned classifier, MiniLM embeddings) are cached in a Modal Volume so cold starts do not
re-download them.
"""
from __future__ import annotations

import os
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "oncall-ai"

IMAGE_ENV = {
    "CLASSIFIER_BACKEND": os.getenv("MODAL_CLASSIFIER_BACKEND", "finetuned"),
    "FINETUNED_MODEL": os.getenv("FINETUNED_MODEL", "rachitst/oncall-ai-incident-classifier"),
    "CLASSIFIER_FALLBACK": "llm",
    "LLM_BACKEND": "openai_compatible",
    "LLM_BASE_URL": "https://api.groq.com/openai/v1",
    "LLM_MODEL": os.getenv("LLM_MODEL", "qwen/qwen3.8-27b"),
    "LLM_MAX_RETRIES": "2",
    "EMBEDDING_MODEL": "sentence-transformers/all-MiniLM-L6-v2",
    "HF_HOME": "/cache/huggingface",
    "LOG_FILE": "/tmp/oncall/app.log",
    "PYTHONUNBUFFERED": "1",
    "TOKENIZERS_PARALLELISM": "false",
}

SKIP_DIRS = {".venv", "venv", ".git", "logs", "models", "outputs", "__pycache__", ".pytest_cache", "screenshots", ".cache"}
SKIP_FILES = {".env"}


def _ignore(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts) or path.name in SKIP_FILES or path.suffix in {".pyc", ".ipynb"}


image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch", index_url="https://download.pytorch.org/whl/cpu")
    .pip_install_from_requirements(str(ROOT / "requirements.txt"))
    .env(IMAGE_ENV)
    .add_local_dir(str(ROOT), remote_path="/app", ignore=_ignore)
)

app = modal.App(APP_NAME)
hf_cache = modal.Volume.from_name(f"{APP_NAME}-hf-cache", create_if_missing=True)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name(APP_NAME)],      # LLM_API_KEY
    volumes={"/cache": hf_cache},
    cpu=2.0,
    memory=4096,
    timeout=600,
    scaledown_window=600,                            # keep a warm container for 10 min after the last request
    max_containers=1,                                # Gradio's queue/session state lives in one process: never split
)                                                    # a browser session across containers (otherwise 404s in the UI)
@modal.concurrent(max_inputs=100)                    # SSE connections (heartbeat, queue) are long-lived inputs
@modal.asgi_app()
def web():
    import sys
    os.chdir("/app")
    sys.path.insert(0, "/app")
    os.makedirs("/tmp/oncall", exist_ok=True)
    from app.api import app as fastapi_app   # FastAPI lifespan loads the knowledge base, classifier and LLM backend
    return fastapi_app
