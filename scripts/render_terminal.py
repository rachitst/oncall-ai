"""Render a captured terminal transcript (text file) to a PNG for the report: python scripts/render_terminal.py in.txt out.png [title]"""
import html, os, sys, tempfile
from playwright.sync_api import sync_playwright

src, out = sys.argv[1], sys.argv[2]
title = sys.argv[3] if len(sys.argv) > 3 else os.path.basename(src)
body = html.escape(open(src, encoding="utf-8").read())
page_html = f"""<html><body style="margin:0;background:#1e1e1e"><div style="padding:14px 18px;font:13px/1.45 'DejaVu Sans Mono',monospace;color:#d4d4d4;width:1200px">
<div style="color:#9cdcfe;margin-bottom:8px">{html.escape(title)}</div><pre style="margin:0;white-space:pre-wrap">{body}</pre></div></body></html>"""
tmp = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8"); tmp.write(page_html); tmp.close()
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1240, "height": 600}, device_scale_factor=2)
    pg.goto("file://" + tmp.name); pg.locator("div").first.screenshot(path=out); b.close()
print("saved", out)
