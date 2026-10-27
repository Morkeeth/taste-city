"""Capture Taste City's first 15 seconds at phone and desktop sizes with Metal."""
import atexit
import functools
import pathlib
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright


ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path(sys.argv[1]).resolve()
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
url = f"http://127.0.0.1:{server.server_port}/village.html?demo=1&population=25"


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"],
        ignore_default_args=["--enable-unsafe-swiftshader"],
    )
    for width, height in ((390, 844), (1440, 1000)):
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_selector("#load[hidden]", state="attached")
        page.wait_for_timeout(1000)
        boxes = page.locator(".outlet-sign:visible").evaluate_all(
            "nodes => nodes.map(node => { const r = node.getBoundingClientRect(); return ({left:r.left, right:r.right, top:r.top, bottom:r.bottom}); })"
        )
        if not boxes or any(box["left"] < 0 or box["right"] > width for box in boxes):
            raise SystemExit(f"Outlet label outside {width}px viewport: {boxes}")
        page.screenshot(path=str(OUT / f"taste-city-{width}x{height}.png"))
        page.close()
    browser.close()

    browser = playwright.chromium.launch(
        args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"],
        ignore_default_args=["--enable-unsafe-swiftshader"],
    )
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000},
        record_video_dir=str(VIDEO_DIR),
        record_video_size={"width": 1440, "height": 1000},
    )
    page = context.new_page()
    started = time.monotonic()
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector("#load[hidden]", state="attached")
    page.wait_for_timeout(max(0, int((10 - (time.monotonic() - started)) * 1000)))
    page.locator("#navorg").click()
    page.wait_for_timeout(max(0, int((30 - (time.monotonic() - started)) * 1000)))
    video = page.video
    context.close()
    browser.close()
    webm = pathlib.Path(video.path())

server.shutdown()
server.server_close()

mp4 = OUT / "taste-city-first-30s-1440x1000.mp4"
subprocess.run(
    [
        "ffmpeg", "-y", "-i", str(webm), "-vf", "format=yuv420p",
        "-c:v", "libx264", "-movflags", "+faststart", str(mp4),
    ],
    check=True,
)
print(OUT / "taste-city-390x844.png")
print(OUT / "taste-city-1440x1000.png")
print(mp4)
