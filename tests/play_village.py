"""Plays all 10 gifts of Taste City on a phone viewport and reports console errors.
Run the app first (python3 match_app.py), then: python3 tests/play_village.py http://127.0.0.1:8811 /tmp/shots/"""
import sys, time
from playwright.sync_api import sync_playwright
D = sys.argv[2] if len(sys.argv) > 2 else "./"   
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8811"
errors = []
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    t0 = time.time()
    pg.goto(BASE + "/village?me=Radiohead")
    pg.wait_for_selector("#panel:not([hidden]) .chip", timeout=60000)
    print("loaded in", round(time.time() - t0, 1), "s")
    pg.wait_for_timeout(1500)
    pg.screenshot(path=D + "03-iphone-gift.png")
    right = 0
    for r in range(10):
        chips = pg.locator(".chip")
        n = chips.count()
        chips.nth(r % n).tap()
        pg.wait_for_timeout(300)
        if r == 0:
            pg.screenshot(path=D + "04-iphone-picked.png")
        pg.locator("#give").tap()
        pg.wait_for_timeout(700)
        v = pg.locator(".verdict").inner_text()
        right += v.startswith("Right")
        if r in (0, 1):
            pg.screenshot(path=D + f"05-iphone-verdict-{r + 1}.png")
        print(r + 1, v[:90])
        pg.locator("#next").tap()
        pg.wait_for_timeout(300)
    pg.wait_for_timeout(500)
    pg.screenshot(path=D + "06-iphone-end.png")
    print("end:", pg.locator(".verdict").inner_text(), "| right", right)
    print("errors:", errors)
    b.close()
