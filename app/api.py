"""OnCall AI - FastAPI service (JSON API) with the Gradio interface mounted on the same process.

  GET  /health            liveness + loaded components
  GET  /api/incident-types
  GET  /api/examples
  POST /api/analyze       {"log_text": "...", "environment": "prod|staging|dev|"}
  GET  /docs              OpenAPI / Swagger UI
  GET  /                  Gradio web interface

Run:  uvicorn app.api:app --host 0.0.0.0 --port 7860
"""
from __future__ import annotations

import glob
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from typing import Literal, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.taxonomy import INCIDENT_TYPES, SEVERITIES  # noqa: E402

from .classifier import create_classifier  # noqa: E402
from .config import ROOT, Settings  # noqa: E402
from .knowledge import KnowledgeBase  # noqa: E402
from .llm import BackendError, create_backend  # noqa: E402
from .workflow import IncidentWorkflow  # noqa: E402

LOG_FILE = os.getenv("LOG_FILE", os.path.join(ROOT, "logs", "app.log"))


# ----------------------------------------------------------------------------- logging
class RedactSecretsFilter(logging.Filter):
    def __init__(self, secrets):
        super().__init__()
        self.secrets = [s for s in secrets if s and len(s) >= 8]

    def filter(self, record):
        if self.secrets:
            msg = record.getMessage()
            for s in self.secrets:
                msg = msg.replace(s, "[REDACTED]")
            record.msg, record.args = msg, None
        return True


def setup_logging():
    logger = logging.getLogger("oncall")
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    redact_filter = RedactSecretsFilter([os.getenv("LLM_API_KEY", ""), os.getenv("GROQ_API_KEY", "")])
    handlers = [logging.StreamHandler()]
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        handlers.append(RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3))
    except OSError:
        pass
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(redact_filter)
        logger.addHandler(h)
    logger.propagate = False


setup_logging()
log = logging.getLogger("oncall.api")


# ----------------------------------------------------------------------------- schemas
class AnalyzeRequest(BaseModel):
    log_text: str = Field(..., description="Log excerpt, stack trace or alert text (1 to 20,000 characters).",
                          examples=["FATAL: too many connections for role \"app\" ..."])
    environment: Optional[Literal["prod", "staging", "dev", ""]] = Field("", description="Optional environment hint.")

    @field_validator("log_text")
    @classmethod
    def check_log(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("log_text must not be empty.")
        limit = Settings.from_env().max_log_chars
        if len(v) > limit:
            raise ValueError(f"log_text must be at most {limit} characters (received {len(v)}).")
        return v


class ClassificationOut(BaseModel):
    incident_type: str
    label: str
    severity: str
    severity_meaning: str
    confidence: float
    method: str
    latency_ms: float


class PassageOut(BaseModel):
    source: str
    section: str
    incident_type: str
    distance: float
    text: str


class AnalyzeResponse(BaseModel):
    request_id: str
    classification: ClassificationOut
    analysis: dict
    grounded: bool
    needs_human: bool
    passages: list[PassageOut]
    incident_report: str
    redaction_counts: dict
    path: list[str]
    timings_ms: dict
    llm_calls: int
    errors: list[str]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    knowledge_chunks: int
    knowledge_file_types: list[str]
    classifier: str
    llm_backend: str
    llm_model: str
    uptime_s: float


class ErrorResponse(BaseModel):
    error: str
    message: str
    request_id: str
    detail: Optional[list[dict]] = None


# ----------------------------------------------------------------------------- app
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    log.info("startup config=%s", settings.public_summary())
    t0 = time.perf_counter()
    knowledge = KnowledgeBase(settings)
    backend = create_backend(settings)
    classifier = create_classifier(settings, backend)
    app.state.settings = settings
    app.state.workflow = IncidentWorkflow(settings, knowledge, classifier, backend)
    app.state.classifier_name = classifier.method
    app.state.started_at = time.time()
    log.info("ready classifier=%s knowledge_chunks=%d startup_s=%.1f", classifier.method, knowledge.size,
             time.perf_counter() - t0)
    yield
    backend.close()
    log.info("shutdown")


app = FastAPI(title="OnCall AI - Intelligent Production Incident Analyzer", version="1.0.0",
              description="Classifies production logs (QLoRA-fine-tuned model), retrieves the matching runbook (RAG), "
                          "explains the root cause and drafts an incident report via a LangGraph workflow.",
              lifespan=lifespan)


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex[:12]
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled_error request_id=%s path=%s", request.state.request_id, request.url.path)
        response = JSONResponse(status_code=500, content=ErrorResponse(
            error="internal_error", message="An unexpected error occurred. Please try again later.",
            request_id=request.state.request_id).model_dump(exclude_none=True))
    elapsed = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Response-Time-ms"] = f"{elapsed:.1f}"
    if not request.url.path.startswith(("/gradio", "/assets", "/theme", "/queue", "/static")) and request.url.path != "/":
        log.info("request request_id=%s method=%s path=%s status=%d latency_ms=%.1f",
                 request.state.request_id, request.method, request.url.path, response.status_code, elapsed)
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    detail = []
    for err in exc.errors():
        field = ".".join(p for p in err.get("loc", []) if isinstance(p, str) and p != "body") or "body"
        detail.append({"field": field, "message": str(err.get("msg", "Invalid value")).removeprefix("Value error, ")})
    log.warning("validation_failed request_id=%s fields=%s", _rid(request), [d["field"] for d in detail])
    return JSONResponse(status_code=422, content=ErrorResponse(error="invalid_request", message="The request is invalid.",
                                                               request_id=_rid(request), detail=detail).model_dump(exclude_none=True))


@app.get("/health", response_model=HealthResponse)
def health(request: Request):
    wf: IncidentWorkflow = request.app.state.workflow
    return HealthResponse(status="ok", knowledge_chunks=wf.knowledge.size, knowledge_file_types=wf.knowledge.file_types,
                          classifier=request.app.state.classifier_name, llm_backend=wf.settings.llm_backend,
                          llm_model=wf.settings.llm_model, uptime_s=round(time.time() - request.app.state.started_at, 1))


@app.get("/api/incident-types")
def incident_types():
    return {"incident_types": {k: v["label"] for k, v in INCIDENT_TYPES.items()}, "severities": SEVERITIES}


def load_examples() -> list[dict]:
    examples = []
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "samples", "*.log"))):
        name = os.path.splitext(os.path.basename(path))[0].replace("_", " ")
        examples.append({"name": name, "log_text": open(path, encoding="utf-8").read()})
    return examples


@app.get("/api/examples")
def examples():
    return {"examples": load_examples()}


@app.post("/api/analyze", response_model=AnalyzeResponse,
          responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
def analyze(payload: AnalyzeRequest, request: Request):
    rid = _rid(request)
    wf: IncidentWorkflow = request.app.state.workflow
    t0 = time.perf_counter()
    try:
        state = wf.run(payload.log_text, payload.environment or "")
    except BackendError as exc:
        log.error("analyze_failed request_id=%s error_kind=%s upstream_status=%s", rid, exc.kind, exc.upstream_status)
        return JSONResponse(status_code=503, content=ErrorResponse(
            error="backend_unavailable", message="The analysis service is temporarily unavailable. Please try again later.",
            request_id=rid).model_dump(exclude_none=True))
    c = state["classification"]
    log.info("analyze_ok request_id=%s type=%s severity=%s confidence=%.2f method=%s grounded=%s needs_human=%s "
             "llm_calls=%d log_chars=%d redactions=%d path=%s total_ms=%.1f",
             rid, c["incident_type"], c["severity"], c["confidence"], c["method"], state.get("grounded"),
             state.get("needs_human", False), state.get("llm_calls", 0), len(payload.log_text),
             sum(state.get("redaction_counts", {}).values()), ">".join(state["path"]), (time.perf_counter() - t0) * 1000)
    return AnalyzeResponse(request_id=rid, classification=ClassificationOut(**c), analysis=state["analysis"],
                           grounded=bool(state.get("grounded")), needs_human=bool(state.get("needs_human", False)),
                           passages=[PassageOut(**p) for p in state.get("passages", [])],
                           incident_report=state["incident_report"], redaction_counts=state.get("redaction_counts", {}),
                           path=state["path"], timings_ms=state["timings_ms"], llm_calls=state.get("llm_calls", 0),
                           errors=state.get("errors", []))


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"], include_in_schema=False)
def api_fallback(rest: str, request: Request):
    """Keep proper 405/404 semantics for /api/* even though the Gradio UI is mounted at '/'."""
    path = "/api/" + rest
    allowed = sorted({m for r in app.routes if getattr(r, "path", None) == path for m in (getattr(r, "methods", None) or [])})
    if allowed:
        return JSONResponse(status_code=405, content={"detail": "Method Not Allowed"}, headers={"Allow": ", ".join(allowed)})
    return JSONResponse(status_code=404, content={"detail": "Not Found"})


# ----------------------------------------------------------------------------- Gradio UI (mounted last)
if os.getenv("DISABLE_UI", "").lower() not in {"1", "true"}:
    import gradio as gr

    from .ui import build_ui

    app = gr.mount_gradio_app(app, build_ui(), path="/")
