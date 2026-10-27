"""Headless still and performance proof for both Taste City Engine flows."""
import datetime
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright


def capture(port, output):
    output = pathlib.Path(output)
    output.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:{port}/?demo=1&judge=1&population=25"
    proof = {
        "captured_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "url": url,
        "flows": {},
        "browser_errors": [],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.on("console", lambda message: proof["browser_errors"].append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: proof["browser_errors"].append(str(error)))
        requests = []
        page.on("request", lambda request: requests.append(request.url) if "/api/scenario" in request.url else None)
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_selector("#load[hidden]", state="attached")

        for flow in ("brand", "festival"):
            if flow == "festival":
                page.locator("#navfest").click()
            started = page.evaluate("performance.now()")
            page.locator("#runbrand").click()
            page.wait_for_function("document.body.dataset.brandPlan === 'ready'", timeout=30000)
            page.wait_for_selector(".archetype")
            finished = page.evaluate("performance.now()")
            desktop = output / f"{flow}-1440x1000.png"
            page.screenshot(path=str(desktop))
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(350)
            phone = output / f"{flow}-390x844.png"
            page.screenshot(path=str(phone))
            layout = page.evaluate("({innerWidth, scrollWidth:document.documentElement.scrollWidth})")
            state = page.evaluate("window.__tasteCity.snapshot()")
            proof["flows"][flow] = {
                "time_to_result_ms": round(finished - started, 1),
                "first_paint_ms": state["firstPaintMs"],
                "archetypes": page.locator(".archetype").count(),
                "scenario_requests_total": len(requests),
                "mode": state["tasteMode"],
                "phone_overflow": layout["scrollWidth"] != layout["innerWidth"],
                "screenshots": [str(phone), str(desktop)],
            }
            page.set_viewport_size({"width": 1440, "height": 1000})
            if flow == "brand":
                page.locator("#editscenario").click()
        browser.close()
    if proof["browser_errors"]:
        raise SystemExit("Browser errors: " + "; ".join(proof["browser_errors"]))
    if any(row["phone_overflow"] or row["archetypes"] != 6 for row in proof["flows"].values()):
        raise SystemExit("Flow layout or archetype count failed: " + json.dumps(proof["flows"]))
    path = output / "engine-capture.json"
    path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(proof, ensure_ascii=False))


if __name__ == "__main__":
    capture(sys.argv[1], sys.argv[2])
