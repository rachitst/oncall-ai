"""Gradio interface for OnCall AI. It calls the workflow in-process (same object the API uses)."""
from __future__ import annotations

import glob
import json
import os
import tempfile

import gradio as gr

from .config import ROOT

SEV_COLORS = {"P1": "#b91c1c", "P2": "#c2410c", "P3": "#b45309", "P4": "#15803d"}

ABOUT = """
### OnCall AI - Intelligent Production Incident Analyzer
Paste a log excerpt, stack trace or alert. OnCall AI will:

1. **Redact** secrets and personal data before anything leaves the server.
2. **Classify** the incident type and severity with a **QLoRA-fine-tuned Qwen2.5-0.5B** model (12 incident types, P1-P4).
3. **Retrieve** the matching runbook, severity policy and known-error records with **RAG** (all-MiniLM-L6-v2 + FAISS over Markdown, TXT and CSV sources).
4. **Explain** the root cause and fix steps with a cloud LLM, **verified** against the runbooks (grounding check + distance gate).
5. **Draft** a blameless incident report, all orchestrated by a **LangGraph** workflow with confidence-based routing and safe fallbacks.

**Concepts from the lab:** LoRA/QLoRA fine-tuning & 4-bit quantization (Exp 2-3), multi-file RAG with a vector index (Exp 4-5),
LangGraph stateful workflow (Exp 6), FastAPI service with validation, error handling, logging, latency measurement and cloud LLM deployment (Exp 7).

**Links:** source [github.com/rachitst/oncall-ai](https://github.com/rachitst/oncall-ai) ·
fine-tuned model [huggingface.co/rachitst/oncall-ai-incident-classifier](https://huggingface.co/rachitst/oncall-ai-incident-classifier) ·
live demo [rachitst--oncall-ai-web.us-east.modal.run](https://rachitst--oncall-ai-web.us-east.modal.run) (Modal, serverless CPU) ·
API docs at `/docs`.

**Author:** Rachit Manish Chheda (UID 2024301004) - LLM Production & Deployment, ESE mini project.
"""


def _workflow():
    # imported lazily so the UI can be built before the FastAPI lifespan has created the workflow
    from .api import app as fastapi_app
    return fastapi_app.state.workflow


def load_examples():
    items = []
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "samples", "*.log"))):
        items.append((os.path.splitext(os.path.basename(path))[0].replace("_", " "), open(path, encoding="utf-8").read()))
    return items


def analyze(log_text: str, environment: str):
    log_text = (log_text or "").strip()
    if not log_text:
        raise gr.Error("Please paste a log excerpt first.")
    if len(log_text) > 20000:
        raise gr.Error("Log is too long (max 20,000 characters). Paste the relevant part only.")
    try:
        state = _workflow().run(log_text, environment if environment != "auto" else "")
    except Exception as exc:  # BackendError or anything else -> friendly message, details stay in the server log
        raise gr.Error(f"Analysis service temporarily unavailable ({type(exc).__name__}). Please try again.")

    c, a = state["classification"], state["analysis"]
    color = SEV_COLORS.get(c["severity"], "#334155")
    badge = (f"<div style='display:flex;gap:12px;flex-wrap:wrap;align-items:center'>"
             f"<span style='background:{color};color:white;padding:6px 14px;border-radius:999px;font-weight:700'>{c['severity']}</span>"
             f"<span style='font-size:1.15em;font-weight:600'>{c['label']}</span>"
             f"<span style='color:#64748b'>confidence {c['confidence']:.2f} · {c['method']}</span>"
             + ("<span style='background:#fde68a;padding:4px 10px;border-radius:8px'>needs human review</span>" if state.get("needs_human") else "")
             + ("<span style='background:#bbf7d0;padding:4px 10px;border-radius:8px'>grounded in runbook</span>" if state.get("grounded") else
                "<span style='background:#fecaca;padding:4px 10px;border-radius:8px'>not verified against runbook</span>")
             + f"</div><p style='color:#64748b;margin-top:6px'>{c['severity_meaning']}</p>")

    evidence = "\n".join(f"- `{e}`" for e in a.get("evidence", [])) or "_none_"
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(a.get("fix_steps", []), 1)) or "_none_"
    analysis_md = f"### Root cause\n{a.get('root_cause') or '_unavailable_'}\n\n### Evidence from the log\n{evidence}\n\n### Recommended fix steps\n{steps}"

    sources_md = "\n\n".join(
        f"**[{i}] {p['source']} - {p['section']}** (distance {p['distance']:.3f})\n\n> " + p["text"].replace("\n", "\n> ")
        for i, p in enumerate(state.get("passages", []), 1)) or "_no passages retrieved_"

    red = state.get("redaction_counts", {})
    t = state["timings_ms"]
    meta_md = (f"**Workflow path:** `{' → '.join(state['path'])}`  \n"
               f"**Timings (ms):** " + ", ".join(f"{k} {v}" for k, v in t.items()) + "  \n"
               f"**LLM calls:** {state.get('llm_calls', 0)} · **Redactions:** {sum(red.values())} {dict(red) if red else ''}  \n"
               + (f"**Warnings:** {'; '.join(state['errors'])}" if state.get("errors") else ""))

    report = state["incident_report"]
    tmp = tempfile.NamedTemporaryFile("w", suffix="_incident_report.md", delete=False, encoding="utf-8")
    tmp.write(report)
    tmp.close()
    return badge, analysis_md, sources_md, report, tmp.name, meta_md, json.dumps(
        {k: state.get(k) for k in ("classification", "analysis", "grounded", "needs_human", "path", "timings_ms",
                                   "redaction_counts", "llm_calls", "errors")}, indent=2)


def comparison_tab():
    figs = sorted(glob.glob(os.path.join(ROOT, "results", "figures", "*.png")))
    summary_path = os.path.join(ROOT, "results", "comparison_summary.md")
    summary = open(summary_path, encoding="utf-8").read() if os.path.exists(summary_path) else \
        "_Comparison results will appear here after running `training/OnCall_AI_Training.ipynb` and `eval/make_charts.py`._"
    gr.Markdown(summary)
    if figs:
        gr.Gallery(value=figs, columns=2, height="auto", label="Comparison charts")


def build_ui() -> gr.Blocks:
    examples = load_examples()
    with gr.Blocks(title="OnCall AI") as demo:
        gr.Markdown("# 🛠️ OnCall AI\n**Intelligent Production Incident Analyzer** - classify · retrieve runbook · explain · draft report")
        with gr.Tabs():
            with gr.Tab("Analyze incident"):
                with gr.Row():
                    with gr.Column(scale=5):
                        log_in = gr.Textbox(label="Log excerpt / stack trace / alert", lines=14,
                                            placeholder="Paste the relevant lines from your logs here...")
                        env_in = gr.Dropdown(["auto", "prod", "staging", "dev"], value="auto", label="Environment hint")
                        run_btn = gr.Button("Analyze", variant="primary")
                        gr.Examples(examples=[[text, "auto"] for _, text in examples], inputs=[log_in, env_in],
                                    example_labels=[name for name, _ in examples], label="Example incidents (click to load)")
                    with gr.Column(scale=6):
                        badge_out = gr.HTML(label="Classification")
                        analysis_out = gr.Markdown()
                with gr.Accordion("Runbook passages used (RAG sources)", open=False):
                    sources_out = gr.Markdown()
                with gr.Accordion("Incident report (Markdown)", open=True):
                    report_out = gr.Markdown()
                    report_file = gr.File(label="Download report")
                with gr.Accordion("Workflow trace and raw JSON", open=False):
                    meta_out = gr.Markdown()
                    json_out = gr.Code(language="json", label="Result JSON")

                run_btn.click(analyze, inputs=[log_in, env_in],
                              outputs=[badge_out, analysis_out, sources_out, report_out, report_file, meta_out, json_out])
            with gr.Tab("Model comparison"):
                comparison_tab()
            with gr.Tab("Architecture"):
                gr.Markdown("""
```
                 ┌──────────┐   ┌──────────┐  confident  ┌──────────┐   ┌─────────┐   ┌────────┐ grounded ┌──────────────┐
 log ──────────▶ │  ingest  │──▶│ classify │────────────▶│ retrieve │──▶│ analyze │──▶│ verify │─────────▶│ draft_report │──▶ END
 (redaction)     └──────────┘   └────┬─────┘             └──────────┘   └─────────┘   └───┬────┘          └──────▲───────┘
                                     │ low confidence       (RAG: FAISS)  (cloud LLM)      │ ungrounded          │
                                     ▼                                                     ▼                     │
                              ┌────────────────┐                                  ┌───────────────────┐          │
                              │ triage_fallback│──────────────────────────────────│ fallback_analysis │──────────┘
                              └────────────────┘                                  └───────────────────┘
```
**Classifier:** Qwen2.5-0.5B-Instruct fine-tuned with QLoRA (4-bit NF4 base, LoRA r=16 on attention/MLP projections), adapter merged for CPU inference.
**Knowledge base:** 12 runbooks (Markdown), severity policy / report template / postmortem guidelines (TXT), known-error database (CSV) → 100+ chunks, all-MiniLM-L6-v2 embeddings, FAISS IndexFlatL2.
**LLM:** Groq cloud API (OpenAI-compatible) for root-cause analysis and report drafting, with JSON-mode outputs, timeouts, one retry and error mapping.
**Service:** FastAPI (`/api/analyze`, `/health`, `/docs`) with validation, request IDs, response-time headers, rotating logs and secret redaction; Gradio UI mounted on the same process; deployed as a container on Modal (serverless CPU; Dockerfile also targets Hugging Face Spaces).
""")
            with gr.Tab("About"):
                gr.Markdown(ABOUT)
    return demo
