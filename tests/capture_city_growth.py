"""Capture the offline village -> town -> city journey at 1920x1080.

Uses labelled local concept fixtures. It makes no Qloo or model call.
"""
import atexit
import functools
import pathlib
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright


ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT.parent).resolve()
OUT.mkdir(parents=True, exist_ok=True)
VIDEO_DIR = OUT / ".capture-video"
VIDEO_DIR.mkdir(exist_ok=True)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


handler = functools.partial(QuietHandler, directory=str(ROOT))
server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
atexit.register(server.server_close)
URL = f"http://127.0.0.1:{server.server_port}/village.html?demo=1&population=5"


with sync_playwright() as p:
    browser = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        device_scale_factor=1,
        record_video_dir=str(VIDEO_DIR),
        record_video_size={"width": 1920, "height": 1080},
    )
    page = context.new_page()
    errors = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_selector("#load[hidden]", state="attached")
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUT / "village.png"))

    for population in range(6, 26):
        page.evaluate("population => window.__tasteCity.setPopulation(population)", population)
        page.wait_for_timeout(360)
        if population == 15:
            page.screenshot(path=str(OUT / "town.png"))
    page.wait_for_timeout(1800)
    page.screenshot(path=str(OUT / "city.png"))
    page.evaluate("window.__tasteCity.openOutlet('echo')")
    page.locator('[data-taste-pick="Björk"]').click()
    page.locator('[data-taste-pick="Radiohead"]').click()
    page.locator("#trytaste").click()
    page.wait_for_timeout(700)
    page.screenshot(path=str(OUT / "taste-response.png"))
    result = page.evaluate("window.__tasteCity.snapshot()")
    result["fps"] = page.locator("body").get_attribute("data-render-fps")
    video = page.video
    context.close()
    browser.close()
    webm = pathlib.Path(video.path())

server.shutdown()
server.server_close()

if errors:
    raise SystemExit("Browser errors: " + "; ".join(errors))

mp4 = OUT / "qloo-city-growth.mp4"
subprocess.run([
    "ffmpeg", "-y", "-i", str(webm), "-vf", "format=yuv420p",
    "-c:v", "libx264", "-movflags", "+faststart", str(mp4),
], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print({"screens": [str(OUT / name) for name in ("village.png", "town.png", "city.png", "taste-response.png")], "video": str(mp4), "state": result, "errors": errors})
