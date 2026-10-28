"""Create/update the Hugging Face Space (Docker SDK) from the committed tree and configure its secrets/variables.

Usage: python scripts/deploy_space.py [--space rachitst/oncall-ai] [--restart]
Reads HF_TOKEN and LLM_API_KEY from the environment / .env (never printed). The uploaded tree is the git-tracked
files (so .env, logs/, models/, training/outputs/ are never included) with deploy/README_SPACE.md as README.md.
"""
import argparse, os, shutil, subprocess, sys, tarfile, tempfile, io
from dotenv import load_dotenv
from huggingface_hub import HfApi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))

ap = argparse.ArgumentParser()
ap.add_argument("--space", default="rachitst/oncall-ai")
ap.add_argument("--model", default="rachitst/oncall-ai-incident-classifier")
ap.add_argument("--classifier", default="finetuned", choices=["finetuned", "llm", "rules"])
ap.add_argument("--llm-model", default=os.getenv("LLM_MODEL", "qwen/qwen3.8-27b"))
ap.add_argument("--restart", action="store_true", help="only restart the Space (no upload)")
ap.add_argument("--no-upload", action="store_true")
args = ap.parse_args()

token, llm_key = os.getenv("HF_TOKEN", ""), os.getenv("LLM_API_KEY", "")
if not token:
    sys.exit("HF_TOKEN missing (set it in .env or the environment)")
api = HfApi(token=token)
space = args.space

if args.restart:
    api.restart_space(space, factory_reboot=False)
    print("restarted", space); sys.exit(0)

api.create_repo(space, repo_type="space", space_sdk="docker", exist_ok=True, private=False)
print("space:", f"https://huggingface.co/spaces/{space}")

if not args.no_upload:
    with tempfile.TemporaryDirectory() as tmp:
        archive = subprocess.run(["git", "-C", ROOT, "archive", "--format=tar", "HEAD"], check=True, capture_output=True).stdout
        tarfile.open(fileobj=io.BytesIO(archive)).extractall(tmp)
        shutil.copy(os.path.join(ROOT, "deploy", "README_SPACE.md"), os.path.join(tmp, "README.md"))
        for p in ("training/OnCall_AI_Training.ipynb", "docs/CLAUDE_CODE_PROMPT.md"):
            if os.path.exists(os.path.join(tmp, p)):
                os.remove(os.path.join(tmp, p))
        api.upload_folder(folder_path=tmp, repo_id=space, repo_type="space", commit_message="Deploy OnCall AI",
                          delete_patterns=["*"])
    print("files uploaded")

if llm_key:
    api.add_space_secret(space, "LLM_API_KEY", llm_key)
for k, v in {"CLASSIFIER_BACKEND": args.classifier, "FINETUNED_MODEL": args.model, "CLASSIFIER_FALLBACK": "llm",
             "LLM_MODEL": args.llm_model, "LLM_BASE_URL": os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
             "LLM_MAX_RETRIES": "2", "EMBEDDING_MODEL": "sentence-transformers/all-MiniLM-L6-v2"}.items():
    api.add_space_variable(space, k, v)
print("secrets/variables set:", "LLM_API_KEY" if llm_key else "(no LLM_API_KEY)", "CLASSIFIER_BACKEND=" + args.classifier)
