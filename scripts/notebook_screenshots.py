"""Crop cells of the executed training notebook into docs/screenshots/ (evidence for the report).

Usage: python scripts/notebook_screenshots.py            # needs nbconvert + playwright (chromium)
Converts training/OnCall_AI_Training.ipynb to HTML and screenshots selected code cells (input + output) at 2x scale.
"""
import os, subprocess, sys, tempfile
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NB = os.path.join(ROOT, "training", "OnCall_AI_Training.ipynb")
OUT = os.path.join(ROOT, "docs", "screenshots")
# (0-based index among CODE cells, screenshot name, selector inside the cell or None for the whole cell)
TARGETS = [
    (2, "colab_step3_env_dataset.png", None),
    (6, "colab_step7_groq.png", None),
    (9, "colab_step10_lora_training.png", None),
    (10, "colab_step11_qlora_training.png", None),
    (11, "colab_comparison_table.png", ".jp-OutputArea-child:first-child"),
    (12, "colab_step13_merge_push.png", None),
]

tmp = tempfile.mkdtemp()
subprocess.run([sys.executable, "-m", "nbconvert", "--to", "html", NB, "--output-dir", tmp, "--output", "nb.html"],
               check=True, capture_output=True)
os.makedirs(OUT, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1300, "height": 900}, device_scale_factor=2)
    page.goto("file://" + os.path.join(tmp, "nb.html"), wait_until="domcontentloaded", timeout=120_000)
    page.wait_for_selector(".jp-CodeCell", timeout=60_000)
    page.add_style_tag(content="body{background:#fff} .jp-Cell{background:#fff;padding:8px 12px} "
                               ".jp-OutputArea-output pre{white-space:pre-wrap} .jp-Cell-outputWrapper{max-height:none}")
    cells = page.locator(".jp-CodeCell")
    print("code cells:", cells.count())
    for idx, name, inner in TARGETS:
        cell = cells.nth(idx)
        target = cell.locator(inner) if inner else cell
        target.scroll_into_view_if_needed()
        target.screenshot(path=os.path.join(OUT, name))
        print("saved", name)
    browser.close()
