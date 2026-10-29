"""Capture the report screenshots (1400x900) into docs/screenshots/ with Playwright (Chromium).

Usage: python scripts/screenshots.py [--base http://127.0.0.1:7860] [--bad-base http://127.0.0.1:7861]
                                     [--only ui,swagger,errors] [--out docs/screenshots]
Names follow docs/REPORT_STRUCTURE.md. The 503 screenshot needs a second server started with an invalid LLM_API_KEY.
"""
import argparse, json, os, sys, time
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://127.0.0.1:7860")
ap.add_argument("--bad-base", default="http://127.0.0.1:7861")
ap.add_argument("--only", default="ui,swagger,errors")
ap.add_argument("--out", default=os.path.join(ROOT, "docs", "screenshots"))
args = ap.parse_args()
os.makedirs(args.out, exist_ok=True)
only = set(args.only.split(","))
SAMPLES = {"01": "ui_analyze_prod_db.png", "05": "ui_analyze_crashloop.png", "07": "ui_lowconfidence.png"}


def shot(page, name, full=False):
    path = os.path.join(args.out, name)
    page.screenshot(path=path, full_page=full)
    print("saved", name)


def focus_accordion(page, label, open_it=False):
    """Scroll an accordion heading to the top of the viewport (optionally opening it first)."""
    head = page.get_by_text(label, exact=True).first
    if open_it:
        head.click(); time.sleep(1.2)
    head.evaluate("e => e.closest('.label-wrap, button, .block') ? e.closest('.label-wrap, button, .block').scrollIntoView({block: 'start'}) : e.scrollIntoView({block: 'start'})")
    time.sleep(0.8)


def swagger_try(page, base, body, name, op="operations-default-analyze_api_analyze_post"):
    page.goto(f"{base}/docs", wait_until="domcontentloaded"); time.sleep(3)
    page.click(f"#{op} .opblock-summary")
    page.click(f"#{op} button.try-out__btn")
    page.fill(f"#{op} textarea.body-param__text", json.dumps(body, indent=2))
    page.click(f"#{op} button.execute")
    page.wait_for_selector(f"#{op} .live-responses-table", timeout=240_000)
    page.locator(f"#{op} .responses-wrapper").scroll_into_view_if_needed()
    page.evaluate("window.scrollBy(0, 120)")
    time.sleep(0.5)
    shot(page, name)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    if "swagger" in only:
        page.goto(f"{args.base}/docs", wait_until="domcontentloaded"); time.sleep(3); time.sleep(1); shot(page, "swagger_docs.png")
        log = open(os.path.join(ROOT, "data", "samples", "01_database_pool_exhausted_prod.log")).read()
        swagger_try(page, args.base, {"log_text": log, "environment": "prod"}, "swagger_analyze_200.png")
    if "errors" in only:
        swagger_try(page, args.base, {"log_text": "", "environment": ""}, "swagger_422.png")
        swagger_try(page, args.bad_base, {"log_text": "FATAL: too many connections for role \"app\"", "environment": "prod"},
                    "swagger_503_wrong_key.png")

    if "ui" in only:
        for idx, name in SAMPLES.items():
            page.goto(args.base, wait_until="domcontentloaded"); time.sleep(3)
            # click the example row, then Analyze
            page.locator("button").filter(has_text=f"{idx} ").first.click()
            time.sleep(1)
            page.get_by_role("button", name="Analyze", exact=True).click()
            page.wait_for_selector(".oc-sev", timeout=300_000)      # severity badge of the result card
            time.sleep(1.5)
            shot(page, name)
            if idx == "01":
                focus_accordion(page, "📚 Runbook passages used (RAG sources)", open_it=True); shot(page, "ui_sources.png")
                focus_accordion(page, "📝 Incident report (Markdown)"); shot(page, "ui_report.png")
                focus_accordion(page, "🧭 Workflow trace and raw JSON", open_it=True); shot(page, "ui_trace.png")
        page.goto(args.base, wait_until="domcontentloaded"); time.sleep(3)
        page.get_by_role("tab", name="Model comparison").click(); time.sleep(1.5); shot(page, "ui_comparison_tab.png")
        page.evaluate("window.scrollTo(0, 1100)"); time.sleep(0.8); shot(page, "ui_comparison_charts.png")
        page.evaluate("window.scrollTo(0, 0)")
        page.get_by_role("tab", name="Architecture").click(); time.sleep(1); shot(page, "ui_architecture_tab.png")
        page.get_by_role("tab", name="About").click(); time.sleep(1); shot(page, "ui_about_tab.png")
        # dark theme (Gradio honours ?__theme=dark): the custom CSS must stay readable in both themes
        page.goto(args.base + "/?__theme=dark", wait_until="domcontentloaded"); time.sleep(3); time.sleep(1.5)
        shot(page, "ui_dark_analyze.png")
        page.get_by_role("tab", name="Architecture").click(); time.sleep(1); shot(page, "ui_dark_architecture.png")
    browser.close()
