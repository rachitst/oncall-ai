# OnCall AI - Hugging Face Spaces (Docker SDK) / any container host
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface LOG_FILE=/app/logs/app.log

RUN useradd -m -u 1000 user
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .
RUN mkdir -p /app/logs /app/.cache && chown -R user /app
USER user

EXPOSE 7860
HEALTHCHECK --interval=60s --timeout=10s --start-period=240s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:7860/health')"
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "7860"]
