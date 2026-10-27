"""Capture the live Brand Planner judge path at desktop and phone sizes."""
import datetime
import json
import pathlib
import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from capture_contract import validate_layout, validate_moves


def capture(port, shots):
    shots = pathlib.Path(shots)
    url = f"http://127.0.0.1:{port}/?demo=1&judge=1&population=25"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        errors, taste_requests, taste_responses = [], [], []
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: taste_requests.append(request.url) if "/api/taste" in request.url else None)
        def record_response(response):
            if "/api/taste" not in response.url:
                return
            row = {"status": response.status, "url": response.url}
            try:
                row["body"] = response.json()
            except Exception:
                row["body"] = response.text()[:2000]
            taste_responses.append(row)
        page.on("response", record_response)

        def fail(reason):
            panel_text = page.locator("#panel").inner_text() if page.locator("#panel").count() else ""
            screenshot = shots / "qloo-brand-plan-failure-1440x1000.png"
            page.screenshot(path=str(screenshot))
            failure = {
                "captured_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "url": url,
                "reason": reason,
                "brand_plan_state": page.locator("body").get_attribute("data-brand-plan"),
                "panel_text": panel_text,
                "taste_requests": len(taste_requests),
                "taste_responses": taste_responses,
                "browser_errors": errors,
                "screenshot": str(screenshot),
            }
            (shots / "capture-failure.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n")
            browser.close()
            raise SystemExit(f"{reason}\nPanel: {panel_text}\nFailure proof: {shots / 'capture-failure.json'}")

        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_selector("#load[hidden]", state="attached")
        page.locator("#runbrand").click()
        try:
            page.wait_for_function("['ready','error'].includes(document.body.dataset.brandPlan)", timeout=60000)
        except PlaywrightTimeoutError:
            fail("Brand Planner reached neither ready nor error within 60 seconds.")
        if page.locator("body").get_attribute("data-brand-plan") == "error":
            fail("Brand Planner returned an on-screen error.")
        page.wait_for_selector(".brand-move")
        page.wait_for_timeout(800)
        moves = page.locator(".brand-move").evaluate_all("""nodes => nodes.map(node => ({
          role: node.querySelector('span')?.textContent || '',
          entity: node.querySelector('b')?.textContent || '',
          entity_type: node.dataset.entityType || '',
          evidence: node.querySelector('small')?.textContent || ''
        }))""")
        food = validate_moves(moves, errors, len(taste_requests))
        page.screenshot(path=str(shots / "qloo-brand-plan-1440x1000.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(500)
        nav_box = page.locator("#navorg").bounding_box()
        layout = page.evaluate("({innerWidth, scrollWidth: document.documentElement.scrollWidth})")
        validate_layout(nav_box, layout["innerWidth"], layout["scrollWidth"])
        page.screenshot(path=str(shots / "qloo-brand-plan-390x844.png"))
        state = page.evaluate("window.__tasteCity.snapshot()")
        browser.close()

    proof = {
        "captured_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "url": url,
        "screenshots": [str(shots / "qloo-brand-plan-390x844.png"), str(shots / "qloo-brand-plan-1440x1000.png")],
        "taste_requests": len(taste_requests),
        "brand_moves": moves,
        "state": state,
        "checks": {"hospitality_entity_type": food["entity_type"], "brand_nav_inside_390px": True, "phone_has_no_horizontal_overflow": True},
    }
    (shots / "live-capture.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(proof, ensure_ascii=False))


if __name__ == "__main__":
    capture(sys.argv[1], sys.argv[2])
