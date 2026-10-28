"""Headless check of the sample and first-use guidance against a local server started without
provider keys, so no Qloo or model request can happen. Run: python3 tests/check_sample_guidance.py URL OUTDIR"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE, OUT = sys.argv[1].rstrip("/"), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
SAMPLE = ["Björk", "Radiohead", "Little Simz"]
results = []


def check(name, ok, detail=""):
    results.append({"check": name, "ok": bool(ok), "detail": detail})


def run(view, size):
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport=size)
        # 1. default sample journey: For me
        page.goto(f"{BASE}/?demo=1&setup=1")
        page.wait_for_selector("[data-first-use]")
        check(f"{view}: first-use guide on setup", page.locator("[data-first-use]").is_visible())
        check(f"{view}: sample guide names the working example", "Björk, Radiohead and Little Simz in London" in page.inner_text("[data-sample-guide]"))
        page.screenshot(path=str(OUT / f"{view}-1-setup.png"))
        page.click("#setupconsumer")
        page.wait_for_selector("[data-taste-pick]")
        pressed = [c.get_attribute("data-taste-pick") for c in page.locator('[data-taste-pick][aria-pressed="true"]').all()]
        check(f"{view}: sample tastes chosen before any tap", sorted(pressed) == sorted(SAMPLE), str(pressed))
        check(f"{view}: other tastes marked live only", all(c.is_disabled() for c in page.locator('[data-taste-pick][aria-pressed="false"]').all()))
        check(f"{view}: city fixed to London", page.input_value("#discoverycity") == "London" and page.get_attribute("#discoverycity", "readonly") is not None)
        page.screenshot(path=str(OUT / f"{view}-2-discovery.png"))
        page.click("#trytaste")
        page.wait_for_timeout(1500)
        text = page.inner_text("#panel") if page.locator("#panel").count() else page.content()
        check(f"{view}: default sample discovery returns a result", "This result is unavailable" not in text, text[:160])
        page.screenshot(path=str(OUT / f"{view}-3-discovery-result.png"))
        # 2. forced error is recoverable
        page.route("**/api/taste", lambda r: r.fulfill(status=400, content_type="application/json", body=json.dumps({"error": "The fictional sample uses Björk, Radiohead and Little Simz in London. Use live mode for other tastes."})))
        page.goto(f"{BASE}/?demo=1&setup=1")
        page.click("#setupconsumer"); page.click("#trytaste"); page.wait_for_selector("#usesample")
        check(f"{view}: error offers the working sample", page.locator("#usesample").is_visible())
        page.screenshot(path=str(OUT / f"{view}-4-error-recovery.png"))
        page.click("#usesample"); page.wait_for_selector("#trytaste")
        check(f"{view}: recovery returns to a ready sample", page.is_enabled("#trytaste"))
        page.unroute("**/api/taste")
        # 3. business sample
        page.goto(f"{BASE}/?demo=1&setup=1")
        page.click("#setupbusiness"); page.wait_for_selector("[data-brand-pick]")
        bp = [c.get_attribute("data-brand-pick") for c in page.locator('[data-brand-pick][aria-pressed="true"]').all()]
        check(f"{view}: business sample audience fixed", sorted(bp) == sorted(SAMPLE), str(bp))
        page.click("#runbrand"); page.wait_for_timeout(2000)
        text = page.inner_text("#panel")
        check(f"{view}: business sample comparison returns a result", "This result is unavailable" not in text, text[:160])
        page.screenshot(path=str(OUT / f"{view}-5-business-result.png"))
        # 4. live mode without a key: own choices allowed, clear failure, way to the sample
        page.goto(f"{BASE}/?setup=1")
        page.click("#setupconsumer"); page.wait_for_selector("[data-taste-pick]")
        cards = page.locator("[data-taste-pick]").all()
        check(f"{view}: live mode lets you choose any tastes", not any(c.is_disabled() for c in cards))
        for c in cards[3:6]:
            c.click()
        page.click("#trytaste"); page.wait_for_selector("#usesample", timeout=20000)
        check(f"{view}: live failure without a key points to the sample", "labelled sample" in page.inner_text("#usesample"))
        page.screenshot(path=str(OUT / f"{view}-6-live-no-key.png"))
        b.close()


run("desktop", {"width": 1440, "height": 900})
run("mobile", {"width": 390, "height": 844})
(OUT / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False))
bad = [r for r in results if not r["ok"]]
print(f"{len(results) - len(bad)}/{len(results)} passed")
for r in bad:
    print("FAIL", r)
sys.exit(1 if bad else 0)
