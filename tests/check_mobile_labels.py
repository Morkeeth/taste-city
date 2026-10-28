"""Phone check: after the sample result shows and the city settles, no visible 3D label may sit over
the header or the open card, and taps on the result rows must land on the card. Desktop labels
must stay. Local server without provider keys. Run: python3 tests/check_mobile_labels.py URL OUTDIR TAG"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE, OUT, TAG = sys.argv[1].rstrip("/"), Path(sys.argv[2]), sys.argv[3]
SCHEME = sys.argv[4] if len(sys.argv) > 4 else "light"
OUT.mkdir(parents=True, exist_ok=True)

PROBE = """() => {
  const vis = el => { const s = getComputedStyle(el); return s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity || '1') > 0.05; };
  const hit = (r, c) => r.left < c.right && r.right > c.left && r.top < c.bottom && r.bottom > c.top;
  const covers = [document.querySelector('header').getBoundingClientRect()];
  const panel = document.getElementById('panel'); if (!panel.hidden) covers.push(panel.getBoundingClientRect());
  const labels = [...document.getElementById('labels').children].filter(vis);
  const over = labels.filter(el => covers.some(c => hit(el.getBoundingClientRect(), c))).map(el => el.textContent.trim().slice(0, 40));
  const rows = [...panel.querySelectorAll('button, a, .row, li')].filter(vis);
  const stolen = rows.map(el => { const r = el.getBoundingClientRect(); const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return t && !panel.contains(t) ? (el.textContent.trim().slice(0, 30) + ' -> ' + (t.textContent || '').trim().slice(0, 30)) : null; }).filter(Boolean);
  return { visible_labels: labels.length, over_header_or_card: over, taps_stolen: stolen };
}"""


def phone_result(p):
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, color_scheme=SCHEME)
    pg.goto(f"{BASE}/?demo=1&setup=1"); pg.wait_for_selector("#setupconsumer"); pg.click("#setupconsumer")
    pg.wait_for_selector("#trytaste"); pg.click("#trytaste"); pg.wait_for_timeout(6000)  # result, then city animation settles
    out = pg.evaluate(PROBE); pg.screenshot(path=str(OUT / f"{TAG}-phone-result.png")); b.close(); return out


def desktop_result(p):
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.goto(f"{BASE}/?demo=1&setup=1"); pg.wait_for_selector("#setupconsumer"); pg.click("#setupconsumer")
    pg.wait_for_selector("#trytaste"); pg.click("#trytaste"); pg.wait_for_timeout(6000)
    out = pg.evaluate("() => ({ visible_labels: [...document.getElementById('labels').children].filter(el => getComputedStyle(el).visibility !== 'hidden').length, covered_class: document.querySelectorAll('#labels .covered').length })")
    pg.screenshot(path=str(OUT / f"{TAG}-desktop-result.png")); b.close(); return out


with sync_playwright() as p:
    res = {"phone": phone_result(p), "desktop": desktop_result(p)}
(OUT / f"{TAG}-labels.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
ok = not res["phone"]["over_header_or_card"] and not res["phone"]["taps_stolen"] and res["desktop"]["covered_class"] == 0 and res["desktop"]["visible_labels"] > 0
print(TAG, "PASS" if ok else "FAIL", json.dumps(res, ensure_ascii=False)[:900])
sys.exit(0 if ok else 1)
