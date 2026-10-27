"""Screenshots of the three steps at 1440 and 390 px. Run with the app on port 8792 (or pass another port).
Name the GL backend: with the default one, headless Chromium drops the WebGL canvas from phone-size captures."""
import sys
from playwright.sync_api import sync_playwright
OUT, PORT = "cache/shots", sys.argv[1] if len(sys.argv) > 1 else "8792"
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"])
    for w, h in ((1440, 900), (390, 844)):
        for step in (1, 2, 3, 4):
            pg = b.new_page(viewport={"width": w, "height": h}); errs = []
            pg.on("console", lambda m: m.type == "error" and errs.append(m.text)); pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{PORT}/?a=romantic&week=2026-04-05&step={step}"); pg.wait_for_selector("body[data-ready]"); pg.wait_for_timeout(4500)
            pg.screenshot(path=f"{OUT}/step{step}-{w}.png", clip={"x": 0, "y": 0, "width": w, "height": h})
            print(step, w, "scrollWidth", pg.evaluate("document.documentElement.scrollWidth"), "errors", errs); pg.close()
    b.close()
