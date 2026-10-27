"""Capture the Qloo marketplace inside the moving 3D village at 390 x 844.

Run a static server from the repository first, then pass its URL and output folder.
All API responses below are fixed local fixtures. No Qloo or model call is made.
"""
import json
import pathlib
import sys
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright


BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8812"
OUT = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else ".")
OUT.mkdir(parents=True, exist_ok=True)


def villager(name, love, index, street=None):
    return {
        "name": name,
        "love": love,
        "street": street,
        "source": love,
        "found": {"id": f"entity-{index}", "name": love, "call": f"q{index:02d}", "wikidata": ""},
        "who": {"age": ["25_to_29", "30_to_34", "35_to_44"][index % 3], "gender_lean": "even", "call": f"q{index:02d}"},
        "traits": ["design", "music", "film"],
        "pool": [{"id": f"place-{index}", "name": "Apollo Bar", "type": "place", "call": f"q{index:02d}"}],
    }


PLAZA = [
    villager("Maya", "Radiohead", 1), villager("Leo", "The Bear", 2),
    villager("Nora", "Studio Ghibli", 3), villager("Iris", "Fleabag", 4),
    villager("Milo", "Wes Anderson", 5),
]
VILLAGE = {
    "villagers": PLAZA,
    "pools": [v["pool"] for v in PLAZA],
    "gifts": [{"name": "In Rainbows", "type": "artist", "year": 2007, "tags": ["art rock"], "owner": 0, "rank": 1, "affinity": 0.93, "call": "q01", "image": ""}],
    "calls": [{"id": f"q{i:02d}", "purpose": "local fixture", "status": 200} for i in range(1, 6)],
}


def route_api(route):
    req = route.request
    path = urlparse(req.url).path
    if path == "/api/village":
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(VILLAGE))
    if path == "/api/street" and req.method == "POST":
        return route.fulfill(status=200, content_type="application/json", body=json.dumps({"extras": [], "calls": []}))
    if path == "/api/street":
        n = int(parse_qs(urlparse(req.url).query).get("n", [1])[0])
        people = [villager(f"Neighbour {n}.{k}", ["Björk", "A24", "Noma", "MUBI"][n - 1], n * 10 + k, f"District {n}") for k in range(1, 6)]
        return route.fulfill(status=200, content_type="application/json", body=json.dumps({"street": n, "name": f"District {n}", "villagers": people, "calls": []}))
    return route.fulfill(status=200, content_type="application/json", body="{}")


errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route("**/api/**", route_api)
    page.goto(BASE + "/village.html", wait_until="domcontentloaded")
    page.wait_for_selector(".place")
    page.wait_for_timeout(2200)
    page.screenshot(path=str(OUT / "1a.png"))
    page.locator('[data-place="apollo"]').tap()
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "1b.png"))
    page.locator("#navorg").tap()
    page.wait_for_selector(".score-ring")
    page.wait_for_timeout(700)
    page.screenshot(path=str(OUT / "1c.png"))
    residents = int(page.locator("body").get_attribute("data-simulation-residents") or 0)
    moving = int(page.locator("body").get_attribute("data-simulation-moving") or 0)
    print(json.dumps({"viewport": [390, 844], "residents": residents, "moving_now": moving, "screens": ["1a.png", "1b.png", "1c.png"], "errors": errors}))
    if residents < 5 or errors:
        raise SystemExit(1)
    browser.close()
