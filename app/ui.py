"""Gradio interface for OnCall AI. It calls the workflow in-process (same object the API uses).

Design notes
- Colours come from Gradio's own theme variables (``--body-text-color``, ``--block-background-fill`` ...) plus a small set of
  ``--oc-*`` variables that are redefined under ``.dark``; nothing is hard-coded to a light background, so the page stays
  readable when the user (or the OS) switches theme.
- Charts are embedded as base64 data URIs, so the comparison tab never depends on Gradio's per-container file cache
  (which broke the images on the serverless deployment).
"""
from __future__ import annotations

import base64
import glob
import html
import json
import os
import tempfile

import gradio as gr

from .config import ROOT

GITHUB_URL = "https://github.com/rachitst/oncall-ai"
MODEL_URL = "https://huggingface.co/rachitst/oncall-ai-incident-classifier"
DEMO_URL = "https://rachitst--oncall-ai-web.us-east.modal.run"
AUTHOR = "Rachit Manish Chheda (UID 2024301004)"

SEV_COLORS = {"P1": "#dc2626", "P2": "#ea580c", "P3": "#d97706", "P4": "#16a34a"}

THEME = gr.themes.Soft(
    primary_hue="indigo", secondary_hue="violet", neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "SFMono-Regular", "monospace"],
)

HEAD = """
<meta name="description" content="OnCall AI - classify a production log excerpt, retrieve the runbook, explain the root cause and draft an incident report.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' rx='22' fill='%234f46e5'/%3E%3Ctext x='50' y='68' font-size='54' text-anchor='middle' fill='white' font-family='sans-serif' font-weight='700'%3EOC%3C/text%3E%3C/svg%3E">
"""

CSS = """
.gradio-container { max-width: 1240px !important; margin: 0 auto !important; }
.gradio-container {
  --oc-accent: #4f46e5; --oc-accent-2: #7c3aed; --oc-accent-soft: rgba(79,70,229,.10);
  --oc-amber-bg: #fef3c7; --oc-amber-fg: #92400e;
  --oc-green-bg: #dcfce7; --oc-green-fg: #166534;
  --oc-red-bg:   #fee2e2; --oc-red-fg:   #991b1b;
  --oc-blue-bg:  #e0e7ff; --oc-blue-fg:  #3730a3;
  --oc-grey-bg:  var(--background-fill-secondary); --oc-grey-fg: var(--body-text-color);
  --oc-card-bg: var(--block-background-fill); --oc-border: var(--border-color-primary);
  --oc-muted: var(--body-text-color-subdued); --oc-text: var(--body-text-color);
  --oc-shadow: 0 1px 2px rgba(15,23,42,.06), 0 8px 24px -12px rgba(15,23,42,.18);
}
.dark .gradio-container {
  --oc-accent-soft: rgba(129,140,248,.16);
  --oc-amber-bg: rgba(245,158,11,.20); --oc-amber-fg: #fcd34d;
  --oc-green-bg: rgba(34,197,94,.20);  --oc-green-fg: #86efac;
  --oc-red-bg:   rgba(239,68,68,.22);  --oc-red-fg:   #fca5a5;
  --oc-blue-bg:  rgba(99,102,241,.25); --oc-blue-fg:  #c7d2fe;
  --oc-shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
}
.oc-hero { display:flex; justify-content:space-between; align-items:flex-end; gap:24px; flex-wrap:wrap;
  padding:28px 32px; border-radius:18px; color:#fff !important; margin:4px 0 14px;
  background: linear-gradient(120deg, #312e81 0%, #4f46e5 55%, #7c3aed 100%); box-shadow: var(--oc-shadow); }
.oc-hero * { color:#fff !important; }
.oc-kicker { font-size:.78rem; letter-spacing:.14em; text-transform:uppercase; opacity:.85; margin-bottom:6px; }
.oc-hero h1 { font-size:2.1rem; font-weight:800; margin:0 0 6px; line-height:1.1; }
.oc-hero p { margin:0; max-width:720px; opacity:.95; font-size:1.02rem; }
.oc-pills { display:flex; gap:8px; flex-wrap:wrap; margin-top:14px; }
.oc-pills span { background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.28); padding:4px 11px; border-radius:999px; font-size:.8rem; }
.oc-hero-links { display:flex; gap:8px; flex-wrap:wrap; }
.oc-hero-links a { text-decoration:none !important; background:#fff; color:#312e81 !important; padding:8px 14px; border-radius:10px; font-weight:600; font-size:.88rem; }
.oc-hero-links a.ghost { background:rgba(255,255,255,.14); color:#fff !important; border:1px solid rgba(255,255,255,.35); }

.oc-card { background:var(--oc-card-bg); border:1px solid var(--oc-border); border-radius:14px; padding:18px 20px; color:var(--oc-text); box-shadow: var(--oc-shadow); }
.oc-card h3 { margin:0 0 8px; font-size:1.05rem; font-weight:700; color:var(--oc-text); }
.oc-card p { color:var(--oc-text); }
.oc-muted { color:var(--oc-muted) !important; font-size:.9rem; }
.oc-section-title { font-weight:700; font-size:1.15rem; margin:18px 0 10px; color:var(--oc-text); }
.oc-section-sub { color:var(--oc-muted); margin:-6px 0 12px; font-size:.92rem; }

.oc-result-head { display:flex; gap:14px; align-items:center; }
.oc-sev { display:inline-flex; align-items:center; justify-content:center; min-width:58px; height:58px; border-radius:14px;
  color:#fff !important; font-weight:800; font-size:1.35rem; letter-spacing:.02em; flex:none; }
.oc-result-title { font-size:1.25rem; font-weight:700; color:var(--oc-text); line-height:1.2; }
.oc-chips { display:flex; gap:8px; flex-wrap:wrap; margin:14px 0 6px; }
.oc-chip { display:inline-flex; align-items:center; gap:6px; padding:4px 11px; border-radius:999px; font-size:.8rem; font-weight:600;
  background:var(--oc-grey-bg); color:var(--oc-grey-fg); border:1px solid var(--oc-border); }
.oc-chip-amber { background:var(--oc-amber-bg); color:var(--oc-amber-fg); border-color:transparent; }
.oc-chip-green { background:var(--oc-green-bg); color:var(--oc-green-fg); border-color:transparent; }
.oc-chip-red   { background:var(--oc-red-bg);   color:var(--oc-red-fg);   border-color:transparent; }
.oc-chip-blue  { background:var(--oc-blue-bg);  color:var(--oc-blue-fg);  border-color:transparent; }
.oc-conf { margin-top:12px; }
.oc-conf-label { display:flex; justify-content:space-between; font-size:.85rem; color:var(--oc-muted); margin-bottom:5px; }
.oc-conf-label b { color:var(--oc-text); }
.oc-bar { height:8px; border-radius:999px; background:var(--oc-grey-bg); overflow:hidden; border:1px solid var(--oc-border); }
.oc-bar > div { height:100%; border-radius:999px; }
.oc-stats { display:grid; grid-template-columns:repeat(auto-fit, minmax(96px,1fr)); gap:8px; margin-top:14px; }
.oc-stats div { background:var(--oc-grey-bg); border:1px solid var(--oc-border); border-radius:10px; padding:8px 10px; }
.oc-stats span { display:block; font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--oc-muted); }
.oc-stats b { font-size:1rem; color:var(--oc-text); }

.oc-empty { text-align:center; padding:34px 20px; border-style:dashed; box-shadow:none; }
.oc-empty-icon { width:56px; height:56px; margin:0 auto 10px; border-radius:16px; display:flex; align-items:center; justify-content:center;
  background:var(--oc-accent-soft); font-size:1.6rem; }
.oc-steps-mini { display:flex; justify-content:center; gap:8px; flex-wrap:wrap; list-style:none; padding:0; margin:14px 0 0; }
.oc-steps-mini li { background:var(--oc-grey-bg); border:1px solid var(--oc-border); border-radius:999px; padding:4px 12px; font-size:.8rem; color:var(--oc-text); }
.oc-steps-mini li::before { content: counter(step) " "; counter-increment: step; color:var(--oc-accent); font-weight:700; }
.oc-steps-mini { counter-reset: step; }

.oc-kpis { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px,1fr)); gap:12px; margin:6px 0 16px; }
.oc-kpi { background:var(--oc-card-bg); border:1px solid var(--oc-border); border-radius:14px; padding:14px 16px; box-shadow:var(--oc-shadow); }
.oc-kpi span { display:block; font-size:.74rem; text-transform:uppercase; letter-spacing:.06em; color:var(--oc-muted); }
.oc-kpi b { display:block; font-size:1.45rem; font-weight:800; color:var(--oc-text); margin-top:2px; }
.oc-kpi small { color:var(--oc-muted); font-size:.78rem; }
.oc-figs { display:grid; grid-template-columns:repeat(auto-fit, minmax(420px,1fr)); gap:16px; margin-top:8px; }
.oc-fig { background:#fff; border:1px solid var(--oc-border); border-radius:14px; overflow:hidden; box-shadow:var(--oc-shadow); }
.oc-fig img { display:block; width:100%; height:auto; }
.oc-fig figcaption { padding:10px 14px; font-size:.86rem; color:var(--oc-muted); background:var(--oc-card-bg); border-top:1px solid var(--oc-border); }

.oc-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(260px,1fr)); gap:14px; margin-top:8px; }
.oc-grid-5 { grid-template-columns:repeat(auto-fit, minmax(200px,1fr)); }
.oc-icon { width:38px; height:38px; border-radius:11px; display:flex; align-items:center; justify-content:center; background:var(--oc-accent-soft); font-size:1.15rem; margin-bottom:10px; }
.oc-step-no { display:inline-flex; width:28px; height:28px; border-radius:999px; align-items:center; justify-content:center; background:var(--oc-accent); color:#fff !important; font-weight:700; font-size:.85rem; margin-bottom:10px; }
.oc-card ul, .oc-card ol { margin:6px 0 0 18px; padding:0; color:var(--oc-text); }
.oc-card li { margin:3px 0; font-size:.92rem; }
.oc-card code { font-family:var(--font-mono); font-size:.84em; background:var(--oc-grey-bg); border:1px solid var(--oc-border); padding:1px 5px; border-radius:6px; color:var(--oc-text); }
.oc-diagram { background:var(--oc-card-bg); border:1px solid var(--oc-border); border-radius:14px; padding:14px 10px 6px; box-shadow:var(--oc-shadow); }
.oc-diagram svg { width:100%; height:auto; display:block; font-family:var(--font); }
.oc-legend { display:flex; gap:16px; flex-wrap:wrap; padding:6px 10px 8px; font-size:.82rem; color:var(--oc-muted); }
.oc-legend i { display:inline-block; width:22px; height:3px; border-radius:2px; vertical-align:middle; margin-right:6px; }
table.oc-table { width:100%; border-collapse:collapse; font-size:.9rem; margin-top:6px; color:var(--oc-text); }
table.oc-table th, table.oc-table td { text-align:left; padding:9px 12px; border-bottom:1px solid var(--oc-border); vertical-align:top; }
table.oc-table th { font-size:.76rem; text-transform:uppercase; letter-spacing:.06em; color:var(--oc-muted); }
.oc-links { display:grid; grid-template-columns:repeat(auto-fit, minmax(220px,1fr)); gap:12px; margin-top:8px; }
.oc-links a { display:block; text-decoration:none !important; background:var(--oc-card-bg); border:1px solid var(--oc-border); border-radius:14px; padding:14px 16px; color:var(--oc-text) !important; box-shadow:var(--oc-shadow); }
.oc-links a:hover { border-color:var(--oc-accent); }
.oc-links a b { display:block; color:var(--oc-accent) !important; margin-bottom:3px; }
.oc-links a span { font-size:.85rem; color:var(--oc-muted); word-break:break-all; }
.oc-footer { margin-top:18px; padding-top:12px; border-top:1px solid var(--oc-border); color:var(--oc-muted); font-size:.86rem; }
"""


# ----------------------------------------------------------------------------- helpers
def _workflow():
    # imported lazily so the UI can be built before the FastAPI lifespan has created the workflow
    from .api import app as fastapi_app
    return fastapi_app.state.workflow


def load_examples():
    items = []
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "samples", "*.log"))):
        items.append((os.path.splitext(os.path.basename(path))[0].replace("_", " "), open(path, encoding="utf-8").read()))
    return items


def _fmt_ms(ms: float) -> str:
    return f"{ms / 1000:.1f} s" if ms >= 1000 else f"{ms:.0f} ms"


def _esc(s) -> str:
    return html.escape(str(s))


# ----------------------------------------------------------------------------- analyze tab
EMPTY_RESULT = """
<div class="oc-card oc-empty">
  <div class="oc-empty-icon">🛰️</div>
  <h3>No incident analysed yet</h3>
  <p class="oc-muted">Paste a log excerpt, stack trace or alert on the left (or load an example), then press <b>Analyze</b>.</p>
  <ol class="oc-steps-mini"><li>redact secrets</li><li>classify type + severity</li><li>retrieve runbook</li><li>explain · verify · draft report</li></ol>
</div>"""


def result_card(state: dict) -> str:
    c, a = state["classification"], state.get("analysis") or {}
    color = SEV_COLORS.get(c["severity"], "#475569")
    conf = max(0.0, min(1.0, float(c.get("confidence", 0.0))))
    chips = [f"<span class='oc-chip oc-chip-blue'>⚙ {_esc(c['method'])}</span>"]
    if state.get("grounded"):
        chips.append("<span class='oc-chip oc-chip-green'>✔ grounded in runbook</span>")
    else:
        chips.append("<span class='oc-chip oc-chip-red'>✖ not verified against runbook</span>")
    if state.get("needs_human"):
        chips.append("<span class='oc-chip oc-chip-amber'>⚠ needs human review</span>")
    if a.get("model"):
        chips.append(f"<span class='oc-chip'>🧠 {_esc(a['model'])}</span>")
    red = sum((state.get("redaction_counts") or {}).values())
    if red:
        chips.append(f"<span class='oc-chip'>🔒 {red} redaction{'s' if red != 1 else ''}</span>")

    t = state.get("timings_ms") or {}
    stats = "".join(f"<div><span>{_esc(k.replace('_', ' '))}</span><b>{_fmt_ms(float(t[k]))}</b></div>"
                    for k in ("classify", "retrieve", "analyze", "draft_report", "total") if k in t)
    return f"""
<div class="oc-card">
  <div class="oc-result-head">
    <span class="oc-sev" style="background:{color}">{_esc(c['severity'])}</span>
    <div><div class="oc-result-title">{_esc(c['label'])}</div><div class="oc-muted">{_esc(c.get('severity_meaning', ''))}</div></div>
  </div>
  <div class="oc-chips">{''.join(chips)}</div>
  <div class="oc-conf"><div class="oc-conf-label"><span>classifier confidence</span><b>{conf:.2f}</b></div>
    <div class="oc-bar"><div style="width:{conf * 100:.0f}%;background:{color}"></div></div></div>
  <div class="oc-stats">{stats}</div>
</div>"""


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

    a = state["analysis"]
    evidence = "\n".join(f"- `{e}`" for e in a.get("evidence", [])) or "_none_"
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(a.get("fix_steps", []), 1)) or "_none_"
    analysis_md = (f"### 🔍 Root cause\n{a.get('root_cause') or '_unavailable_'}\n\n"
                   f"### 🧾 Evidence from the log\n{evidence}\n\n### 🛠️ Recommended fix steps\n{steps}")

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
    return result_card(state), analysis_md, sources_md, report, tmp.name, meta_md, json.dumps(
        {k: state.get(k) for k in ("classification", "analysis", "grounded", "needs_human", "path", "timings_ms",
                                   "redaction_counts", "llm_calls", "errors")}, indent=2)


# ----------------------------------------------------------------------------- model comparison tab
FIG_CAPTIONS = {
    "01_type_accuracy_f1": "Incident-type accuracy and macro-F1 on the 180-log test set",
    "02_severity_accuracy_f1": "Severity accuracy and macro-F1 on the 180-log test set",
    "03_training_resources": "Training time, peak GPU memory and trainable parameters (LoRA fp16 vs QLoRA 4-bit)",
    "04_inference_latency_memory": "Average inference time per log and GPU memory of the loaded model",
    "05_confusion_matrix": "Incident-type confusion matrix of the best model",
    "06_loss_curves": "Fine-tuning loss curves (training and evaluation)",
}


def _load_results():
    path = os.path.join(ROOT, "results", "comparison.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _modal_latency():
    path = os.path.join(ROOT, "results", "smoke_test_modal.json")
    try:
        with open(path, encoding="utf-8") as fh:
            recs = json.load(fh).get("records", [])
        ms = [r["result"]["classification"]["latency_ms"] for r in recs if r.get("status") == 200]
        return (min(ms), max(ms)) if ms else None
    except (OSError, KeyError, ValueError):
        return None


def kpi_tiles(results: dict) -> str:
    runs = {r["name"]: r for r in results.get("runs", [])}
    q = runs.get("QLoRA 4-bit") or runs.get("LoRA fp16")
    if not q:
        return ""
    tiles = [
        ("Type accuracy", f"{q['type_accuracy']:.3f}", f"macro-F1 {q['type_macro_f1']:.3f}"),
        ("Severity accuracy", f"{q['severity_accuracy']:.3f}", f"macro-F1 {q['severity_macro_f1']:.3f}"),
        ("Trainable params", f"{q['trainable_params'] / 1e6:.1f} M", "LoRA r=16 on attention + MLP"),
        ("Training time", f"{q['train_time_s']:.0f} s", f"{results.get('gpu', 'GPU')}, {results.get('config', {}).get('epochs', '?')} epochs"),
        ("Peak training memory", f"{q['peak_train_memory_gb']:.2f} GB", "4-bit NF4 base + adapters"),
    ]
    lat = _modal_latency()
    if lat:
        tiles.append(("CPU latency (deployed)", f"{lat[0] / 1000:.1f}–{lat[1] / 1000:.1f} s", "per log, 2 vCPU container"))
    return "<div class='oc-kpis'>" + "".join(
        f"<div class='oc-kpi'><span>{_esc(k)}</span><b>{_esc(v)}</b><small>{_esc(s)}</small></div>" for k, v, s in tiles) + "</div>"


def figure_grid() -> str:
    cards = []
    for path in sorted(glob.glob(os.path.join(ROOT, "results", "figures", "*.png"))):
        stem = os.path.splitext(os.path.basename(path))[0]
        with open(path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        cap = FIG_CAPTIONS.get(stem, stem.replace("_", " "))
        cards.append(f"<figure class='oc-fig' style='margin:0'><img src='data:image/png;base64,{b64}' alt='{_esc(cap)}'>"
                     f"<figcaption>{_esc(cap)}</figcaption></figure>")
    return "<div class='oc-figs'>" + "".join(cards) + "</div>" if cards else ""


def comparison_tab():
    results = _load_results()
    summary_path = os.path.join(ROOT, "results", "comparison_summary.md")
    if not results or not os.path.exists(summary_path):
        gr.Markdown("_Comparison results will appear here after running `training/OnCall_AI_Training.ipynb` and `eval/make_charts.py`._")
        return
    n = results.get("n_test", "?")
    gr.HTML(f"<div class='oc-section-title'>Fine-tuned classifier at a glance</div>"
            f"<div class='oc-section-sub'>QLoRA 4-bit run, held-out test set of {n} synthetic logs, measured in "
            f"<code>training/OnCall_AI_Training.ipynb</code> on a {_esc(results.get('gpu', 'GPU'))}.</div>" + kpi_tiles(results))
    summary = open(summary_path, encoding="utf-8").read().replace("### Model comparison on the held-out test set", "")
    gr.HTML("<div class='oc-section-title'>Five approaches on the same test set</div>"
            "<div class='oc-section-sub'>Rules baseline · base model zero-shot · cloud LLM zero-shot · LoRA fp16 · QLoRA 4-bit. "
            "All numbers come from <code>results/comparison.json</code>; nothing is estimated.</div>")
    with gr.Group():
        gr.Markdown(summary)
    gr.HTML("<div class='oc-section-title'>Charts</div>" + figure_grid())


# ----------------------------------------------------------------------------- architecture tab
def _svg_node(x, y, w, h, title, sub, accent=False, dashed=False):
    stroke = "var(--oc-accent)" if accent else "var(--oc-border)"
    dash = " stroke-dasharray='6 4'" if dashed else ""
    return (f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='12' fill='var(--oc-grey-bg)' stroke='{stroke}' stroke-width='1.6'{dash}/>"
            f"<text x='{x + w / 2}' y='{y + 22}' text-anchor='middle' font-size='14' font-weight='700' fill='var(--oc-text)'>{title}</text>"
            f"<text x='{x + w / 2}' y='{y + 41}' text-anchor='middle' font-size='11.5' fill='var(--oc-muted)'>{sub}</text>")


def _svg_arrow(x1, y1, x2, y2, label="", accent=True, dashed=False, lx=None, ly=None):
    color = "var(--oc-accent)" if accent else "var(--oc-muted)"
    dash = " stroke-dasharray='6 4'" if dashed else ""
    mk = "url(#oc-arrow)" if accent else "url(#oc-arrow-muted)"
    svg = f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='{color}' stroke-width='2' marker-end='{mk}'{dash}/>"
    if label:
        lx = (x1 + x2) / 2 if lx is None else lx
        ly = (y1 + y2) / 2 - 8 if ly is None else ly
        svg += f"<text x='{lx}' y='{ly}' text-anchor='middle' font-size='11.5' font-weight='600' fill='{color}'>{label}</text>"
    return svg


def workflow_svg() -> str:
    W, H, Y, FY = 138, 56, 60, 220
    xs = {"ingest": 110, "classify": 290, "retrieve": 470, "analyze": 650, "verify": 830, "draft_report": 1010}
    parts = ["<defs>"
             "<marker id='oc-arrow' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='7' markerHeight='7' orient='auto-start-reverse'>"
             "<path d='M0 0L10 5L0 10z' fill='var(--oc-accent)'/></marker>"
             "<marker id='oc-arrow-muted' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='7' markerHeight='7' orient='auto-start-reverse'>"
             "<path d='M0 0L10 5L0 10z' fill='var(--oc-muted)'/></marker></defs>"]
    # input and END markers
    parts.append("<rect x='10' y='72' width='72' height='32' rx='16' fill='var(--oc-accent)'/>"
                 "<text x='46' y='93' text-anchor='middle' font-size='12.5' font-weight='700' fill='#fff'>log</text>")
    parts.append(_svg_arrow(82, 88, xs["ingest"], 88))
    parts.append("<circle cx='1182' cy='88' r='17' fill='none' stroke='var(--oc-accent)' stroke-width='2'/>"
                 "<circle cx='1182' cy='88' r='9' fill='var(--oc-accent)'/>"
                 "<text x='1182' y='125' text-anchor='middle' font-size='11' fill='var(--oc-muted)'>END</text>")
    # main path
    nodes = [("ingest", "redact secrets / PII"), ("classify", "QLoRA Qwen2.5-0.5B"), ("retrieve", "FAISS + MiniLM"),
             ("analyze", "cloud LLM (JSON)"), ("verify", "grounding check"), ("draft_report", "blameless report")]
    for name, sub in nodes:
        parts.append(_svg_node(xs[name], Y, W, H, name, sub, accent=True))
    order = [n for n, _ in nodes]
    for a, b in zip(order, order[1:]):
        label = {"classify": "confident", "verify": "grounded"}.get(a, "")
        parts.append(_svg_arrow(xs[a] + W, 88, xs[b], 88, label, ly=50))
    parts.append(_svg_arrow(xs["draft_report"] + W, 88, 1165, 88))
    # fallback paths
    parts.append(_svg_node(xs["classify"], FY, 150, H, "triage_fallback", "unknown → human triage", dashed=True))
    parts.append(_svg_node(xs["verify"], FY, 160, H, "fallback_analysis", "generic steps, flagged", dashed=True))
    parts.append(_svg_arrow(xs["classify"] + 65, Y + H, xs["classify"] + 65, FY, "low confidence", accent=False, dashed=True, lx=xs["classify"] + 65 + 62))
    parts.append(_svg_arrow(xs["verify"] + 65, Y + H, xs["verify"] + 65, FY, "ungrounded", accent=False, dashed=True, lx=xs["verify"] + 65 + 50))
    # fallback -> draft_report (elbow lines)
    dx, dy = xs["draft_report"] + W / 2, Y + H
    parts.append(f"<path d='M{xs['classify'] + 150} {FY + 28} H{xs['classify'] + 165} V{FY + 56 + 22} H{dx} V{dy + 2}' fill='none' "
                 f"stroke='var(--oc-muted)' stroke-width='2' stroke-dasharray='6 4' marker-end='url(#oc-arrow-muted)'/>")
    parts.append(f"<path d='M{xs['verify'] + 160} {FY + 28} H{dx} V{dy + 2}' fill='none' stroke='var(--oc-muted)' stroke-width='2' "
                 f"stroke-dasharray='6 4' marker-end='url(#oc-arrow-muted)'/>")
    return ("<div class='oc-diagram'><svg viewBox='0 0 1210 320' role='img' aria-label='OnCall AI LangGraph workflow'>"
            + "".join(parts) + "</svg>"
            "<div class='oc-legend'><span><i style='background:var(--oc-accent)'></i>happy path (confident classification, grounded analysis)</span>"
            "<span><i style='background:var(--oc-muted)'></i>fallback edges chosen by the LangGraph router</span></div></div>")


ARCH_CARDS = [
    ("🧠", "Classifier", "Qwen2.5-0.5B-Instruct fine-tuned with QLoRA (4-bit NF4 base, LoRA r=16 on the attention and MLP projections). "
     "The adapter is merged into fp16 weights and loaded from the Hugging Face Hub for CPU inference; confidence is the geometric mean "
     "token probability of the generated JSON label."),
    ("📚", "Knowledge base", "12 runbooks (Markdown), the severity policy, report template and postmortem guidelines (TXT) and a "
     "known-error database (CSV) are chunked into 100+ passages, embedded with all-MiniLM-L6-v2 and indexed with FAISS (IndexFlatL2)."),
    ("☁️", "Cloud LLM", "An OpenAI-compatible endpoint (Groq) writes the root-cause analysis and the incident report in JSON mode, "
     "with timeouts, Retry-After aware retries, a per-day-quota fallback model and error mapping to HTTP 503."),
    ("🚀", "Service", "FastAPI exposes <code>/api/analyze</code>, <code>/health</code> and <code>/docs</code> with input validation, request IDs, "
     "response-time headers, rotating logs and secret redaction. This Gradio UI is mounted on the same process; the container runs on Modal "
     "(serverless CPU) and also targets Hugging Face Spaces via the Dockerfile."),
]

LIFECYCLE = [
    ("ingest", "Secrets, tokens, e-mail addresses and IPs are redacted before anything is logged or sent to a model."),
    ("classify", "The fine-tuned model returns <code>{incident_type, severity}</code>. Below the confidence threshold "
                 "(<code>CLASSIFIER_MIN_CONFIDENCE</code>) the router takes <b>triage_fallback</b>: unknown incident, human triage steps."),
    ("retrieve", "Top-k passages for the incident type are fetched from the FAISS index; the best distance is kept for the gate."),
    ("analyze", "The cloud LLM explains the root cause, quotes evidence from the log and lists fix steps, citing the passages."),
    ("verify", "Grounding check: the analysis must cite the runbook, pass the distance gate (<code>RAG_MAX_DISTANCE</code>) and contain "
               "at least two fix steps, otherwise <b>fallback_analysis</b> marks the result as unverified and <i>needs human review</i>."),
    ("draft_report", "A blameless incident report (Markdown) is drafted from the verified analysis and returned with timings per node."),
]


def architecture_tab():
    gr.HTML("<div class='oc-section-title'>LangGraph workflow</div>"
            "<div class='oc-section-sub'>One request walks this graph; conditional edges route on classifier confidence and on the grounding check.</div>"
            + workflow_svg())
    cards = "".join(f"<div class='oc-card'><div class='oc-icon'>{i}</div><h3>{t}</h3><p class='oc-muted' style='font-size:.92rem'>{b}</p></div>"
                    for i, t, b in ARCH_CARDS)
    gr.HTML("<div class='oc-section-title'>Components</div><div class='oc-grid'>" + cards + "</div>")
    rows = "".join(f"<tr><td><code>{n}</code></td><td>{d}</td></tr>" for n, d in LIFECYCLE)
    gr.HTML("<div class='oc-section-title'>Request lifecycle</div><div class='oc-card' style='padding:6px 10px'>"
            "<table class='oc-table'><thead><tr><th style='width:150px'>node</th><th>what happens</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>")


# ----------------------------------------------------------------------------- about tab
ABOUT_STEPS = [
    ("🔒", "Redact", "Secrets and personal data are scrubbed before anything leaves the server."),
    ("🏷️", "Classify", "A QLoRA-fine-tuned Qwen2.5-0.5B assigns one of 12 incident types and a P1-P4 severity, on CPU."),
    ("📖", "Retrieve", "The matching runbook, severity policy and known-error records are pulled from a FAISS index (RAG)."),
    ("💡", "Explain & verify", "A cloud LLM explains the root cause and fix steps; the answer is checked against the runbook before it is trusted."),
    ("📝", "Draft", "A blameless incident report is written, ready to paste into the incident channel or ticket."),
]

CONCEPTS = [
    ("LoRA / QLoRA fine-tuning, 4-bit NF4 quantisation, hyper-parameter comparison", "Exp 2, 3", "training notebook → <code>app/classifier.py</code>"),
    ("RAG over Markdown, TXT and CSV sources with a FAISS vector index", "Exp 4, 5", "<code>knowledge_base/</code> → <code>app/knowledge.py</code>"),
    ("LangGraph stateful workflow with conditional routing and fallbacks", "Exp 6", "<code>app/workflow.py</code>"),
    ("Production API: validation, error handling, logging, latency, cloud LLM, secrets, deployment", "Exp 7", "<code>app/api.py</code>, <code>app/llm.py</code>, <code>deploy/</code>"),
]


def about_tab():
    steps = "".join(f"<div class='oc-card'><span class='oc-step-no'>{i}</span><div style='font-size:1.3rem'>{ic}</div><h3>{t}</h3>"
                    f"<p class='oc-muted' style='font-size:.92rem'>{b}</p></div>" for i, (ic, t, b) in enumerate(ABOUT_STEPS, 1))
    gr.HTML("<div class='oc-card' style='margin-bottom:14px'><h3>What is OnCall AI?</h3>"
            "<p class='oc-muted' style='font-size:.95rem'>An intelligent production incident analyzer built as the ESE mini project for "
            "<b>LLM Production &amp; Deployment</b>. It turns a raw log excerpt into a classified, runbook-grounded explanation and a "
            "ready-to-share incident report, and it shows the trade-offs between a rules baseline, zero-shot models and a fine-tuned "
            "small model measured on the same test set.</p></div>"
            "<div class='oc-section-title'>What happens to a pasted log</div><div class='oc-grid oc-grid-5'>" + steps + "</div>")
    rows = "".join(f"<tr><td>{c}</td><td>{e}</td><td>{w}</td></tr>" for c, e, w in CONCEPTS)
    gr.HTML("<div class='oc-section-title'>Concepts from the lab</div><div class='oc-card' style='padding:6px 10px'>"
            "<table class='oc-table'><thead><tr><th>concept</th><th style='width:90px'>experiment</th><th>where in the project</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>")
    links = [("Source code", GITHUB_URL, "FastAPI service, workflow, notebook, evaluation artefacts"),
             ("Fine-tuned model", MODEL_URL, "Merged QLoRA checkpoint with a full model card"),
             ("Live demo", DEMO_URL, "Modal, serverless CPU; first request after idle takes ~30 s"),
             ("API docs", "/docs", "OpenAPI / Swagger for POST /api/analyze and GET /health")]
    gr.HTML("<div class='oc-section-title'>Links</div><div class='oc-links'>" + "".join(
        f"<a href='{u}' target='_blank' rel='noopener'><b>{t}</b><span>{_esc(u if u.startswith('http') else d)}</span></a>" for t, u, d in links)
        + f"</div><div class='oc-footer'>Author: <b>{AUTHOR}</b> · LLM Production &amp; Deployment, ESE mini project · "
          "Training data is synthetic (template-generated logs); see the model card for limitations.</div>")


# ----------------------------------------------------------------------------- page
HERO = f"""
<div class="oc-hero">
  <div>
    <div class="oc-kicker">LLM Production &amp; Deployment · ESE mini project</div>
    <h1>🛠️ OnCall AI</h1>
    <p>Intelligent production incident analyzer. Paste a log excerpt and get the incident type and severity, the matching runbook,
    a verified root-cause explanation and a draft incident report.</p>
    <div class="oc-pills"><span>QLoRA Qwen2.5-0.5B classifier</span><span>FAISS runbook RAG</span><span>LangGraph workflow</span><span>FastAPI + Gradio</span></div>
  </div>
  <div class="oc-hero-links">
    <a href="/docs" target="_blank" rel="noopener">API docs</a>
    <a class="ghost" href="{GITHUB_URL}" target="_blank" rel="noopener">GitHub</a>
    <a class="ghost" href="{MODEL_URL}" target="_blank" rel="noopener">Model</a>
  </div>
</div>"""


def build_ui() -> gr.Blocks:
    examples = load_examples()
    with gr.Blocks(title="OnCall AI") as demo:
        gr.HTML(HERO)
        with gr.Tabs():
            with gr.Tab("🔎 Analyze incident"):
                with gr.Row(equal_height=False):
                    with gr.Column(scale=5):
                        log_in = gr.Textbox(label="Log excerpt / stack trace / alert", lines=14,
                                            placeholder="Paste the relevant lines from your logs here...")
                        with gr.Row():
                            env_in = gr.Dropdown(["auto", "prod", "staging", "dev"], value="auto", label="Environment hint", scale=2)
                            run_btn = gr.Button("Analyze", variant="primary", scale=1, size="lg")
                        gr.Examples(examples=[[text, "auto"] for _, text in examples], inputs=[log_in, env_in],
                                    example_labels=[name for name, _ in examples], label="Example incidents (click to load)")
                    with gr.Column(scale=6):
                        badge_out = gr.HTML(value=EMPTY_RESULT)
                        analysis_out = gr.Markdown()
                with gr.Accordion("📚 Runbook passages used (RAG sources)", open=False):
                    sources_out = gr.Markdown()
                with gr.Accordion("📝 Incident report (Markdown)", open=True):
                    report_out = gr.Markdown()
                    report_file = gr.File(label="Download report")
                with gr.Accordion("🧭 Workflow trace and raw JSON", open=False):
                    meta_out = gr.Markdown()
                    json_out = gr.Code(language="json", label="Result JSON")

                run_btn.click(analyze, inputs=[log_in, env_in],
                              outputs=[badge_out, analysis_out, sources_out, report_out, report_file, meta_out, json_out])
            with gr.Tab("📊 Model comparison"):
                comparison_tab()
            with gr.Tab("🧩 Architecture"):
                architecture_tab()
            with gr.Tab("ℹ️ About"):
                about_tab()
    return demo
