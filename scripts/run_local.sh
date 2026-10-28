#!/usr/bin/env bash
# Start OnCall AI locally: http://127.0.0.1:7860  (UI)  http://127.0.0.1:7860/docs (API docs)
set -e
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "No .env found - copy .env.example to .env and add your key"; exit 1; }
exec uvicorn app.api:app --host 127.0.0.1 --port "${PORT:-7860}"
