"""Build the comparison charts and summary from results/comparison.json (written by the training notebook).

Usage: python eval/make_charts.py [--results results]
Produces results/figures/*.png and results/comparison_summary.md (shown in the UI's "Model comparison" tab and used
in the report).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.taxonomy import INCIDENT_TYPE_IDS  # noqa: E402

COLORS = ["#94a3b8", "#60a5fa", "#f59e0b", "#2563eb", "#16a34a"]


def bar(ax, names, values, title, ylabel, fmt="{:.2f}", ylim=None):
    bars = ax.bar(names, values, color=COLORS[: len(names)])
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_ylabel(ylabel)
    if ylim:
        ax.set_ylim(*ylim)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), fmt.format(v), ha="center", va="bottom", fontsize=9)
    ax.tick_params(axis="x", labelrotation=15)
    ax.grid(axis="y", alpha=0.3)


def main(results_dir: str) -> None:
    path = os.path.join(results_dir, "comparison.json")
    data = json.load(open(path))
    runs = data["runs"]                     # list of dicts, in display order
    figs = os.path.join(results_dir, "figures")
    os.makedirs(figs, exist_ok=True)
    names = [r["name"] for r in runs]

    # 1. accuracy / macro-F1 for incident type and severity
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    bar(axes[0], names, [r["type_accuracy"] for r in runs], "Incident-type accuracy (test set)", "accuracy", ylim=(0, 1.05))
    bar(axes[1], names, [r["type_macro_f1"] for r in runs], "Incident-type macro-F1 (test set)", "macro-F1", ylim=(0, 1.05))
    fig.tight_layout(); fig.savefig(os.path.join(figs, "01_type_accuracy_f1.png"), dpi=150); plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    bar(axes[0], names, [r["severity_accuracy"] for r in runs], "Severity accuracy (test set)", "accuracy", ylim=(0, 1.05))
    bar(axes[1], names, [r["severity_macro_f1"] for r in runs], "Severity macro-F1 (test set)", "macro-F1", ylim=(0, 1.05))
    fig.tight_layout(); fig.savefig(os.path.join(figs, "02_severity_accuracy_f1.png"), dpi=150); plt.close(fig)

    # 2. resources: training time, peak GPU memory, trainable params (only runs that trained)
    trained = [r for r in runs if r.get("train_time_s")]
    if trained:
        fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
        bar(axes[0], [r["name"] for r in trained], [r["train_time_s"] for r in trained], "Training time", "seconds", fmt="{:.0f}")
        bar(axes[1], [r["name"] for r in trained], [r["peak_train_memory_gb"] for r in trained], "Peak GPU memory during training", "GB")
        bar(axes[2], [r["name"] for r in trained], [r["trainable_params"] / 1e6 for r in trained], "Trainable parameters", "millions")
        fig.tight_layout(); fig.savefig(os.path.join(figs, "03_training_resources.png"), dpi=150); plt.close(fig)

    # 3. inference latency and model memory
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    bar(axes[0], names, [r["avg_inference_ms"] for r in runs], "Average inference time per log", "ms", fmt="{:.0f}")
    mem_runs = [r for r in runs if r.get("model_memory_gb") is not None]
    if mem_runs:
        bar(axes[1], [r["name"] for r in mem_runs], [r["model_memory_gb"] for r in mem_runs], "GPU memory of the loaded model", "GB")
    fig.tight_layout(); fig.savefig(os.path.join(figs, "04_inference_latency_memory.png"), dpi=150); plt.close(fig)

    # 4. confusion matrix of the best run (QLoRA if present)
    best = next((r for r in runs if "QLoRA" in r["name"]), runs[-1])
    if best.get("confusion_matrix"):
        cm = np.array(best["confusion_matrix"])
        labels = [t.replace("_", "\n") for t in INCIDENT_TYPE_IDS]
        fig, ax = plt.subplots(figsize=(11, 9))
        im = ax.imshow(cm, cmap="Blues")
        ax.set_xticks(range(len(labels))); ax.set_yticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=90, fontsize=7); ax.set_yticklabels(labels, fontsize=7)
        ax.set_xlabel("Predicted"); ax.set_ylabel("True")
        ax.set_title(f"Incident-type confusion matrix - {best['name']}", fontweight="bold")
        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                if cm[i, j]:
                    ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=7, color="white" if cm[i, j] > cm.max() / 2 else "black")
        fig.colorbar(im, ax=ax, fraction=0.046)
        fig.tight_layout(); fig.savefig(os.path.join(figs, "05_confusion_matrix.png"), dpi=150); plt.close(fig)

    # 5. training loss curves
    curves = [r for r in runs if r.get("loss_curve")]
    if curves:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for r, c in zip(curves, COLORS[2:]):
            steps = [p["step"] for p in r["loss_curve"]]
            ax.plot(steps, [p["loss"] for p in r["loss_curve"]], label=f"{r['name']} train loss", color=c)
            if r.get("eval_curve"):
                ax.plot([p["step"] for p in r["eval_curve"]], [p["eval_loss"] for p in r["eval_curve"]],
                        marker="o", linestyle="--", label=f"{r['name']} eval loss", color=c)
        ax.set_xlabel("training step"); ax.set_ylabel("loss"); ax.set_title("Fine-tuning loss curves", fontweight="bold")
        ax.legend(); ax.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(os.path.join(figs, "06_loss_curves.png"), dpi=150); plt.close(fig)

    # summary markdown table
    lines = ["### Model comparison on the held-out test set", "",
             f"Test samples: {data.get('n_test', '?')} · 12 incident types · 4 severity levels · "
             f"GPU: {data.get('gpu', '?')}", "",
             "| Approach | Type acc. | Type F1 | Sev. acc. | Sev. F1 | Parse fail | Infer ms | Train s | Peak train GB | Trainable params |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        lines.append(f"| {r['name']} | {r['type_accuracy']:.3f} | {r['type_macro_f1']:.3f} | {r['severity_accuracy']:.3f} | "
                     f"{r['severity_macro_f1']:.3f} | {r.get('parse_failures', 0)} | {r['avg_inference_ms']:.0f} | "
                     f"{r['train_time_s'] if r.get('train_time_s') else '-'} | "
                     f"{r['peak_train_memory_gb'] if r.get('peak_train_memory_gb') else '-'} | "
                     f"{r['trainable_params']:,} |" if r.get("trainable_params") else
                     f"| {r['name']} | {r['type_accuracy']:.3f} | {r['type_macro_f1']:.3f} | {r['severity_accuracy']:.3f} | "
                     f"{r['severity_macro_f1']:.3f} | {r.get('parse_failures', 0)} | {r['avg_inference_ms']:.0f} | - | - | - |")
    if data.get("notes"):
        lines += ["", *[f"- {n}" for n in data["notes"]]]
    open(os.path.join(results_dir, "comparison_summary.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nfigures:", sorted(os.listdir(figs)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results"))
    main(ap.parse_args().results)
