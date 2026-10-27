"""Record one roughly 30 second headless flow for each Taste City Engine mode."""
import pathlib
import sys

from playwright.sync_api import sync_playwright


def record_flow(browser, url, output, flow):
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000},
        record_video_dir=str(output),
        record_video_size={"width": 1440, "height": 1000},
    )
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector("#load[hidden]", state="attached")
    page.wait_for_timeout(3500)
    if flow == "festival":
        page.locator("#navfest").click()
    page.wait_for_timeout(3500)
    page.locator("#runbrand").click()
    page.wait_for_function("document.body.dataset.brandPlan === 'ready'", timeout=30000)
    page.wait_for_timeout(5000)
    page.locator(".panel").evaluate("node => node.scrollTo({top:node.scrollHeight * .55, behavior:'smooth'})")
    page.wait_for_timeout(5500)
    page.locator("details summary").click()
    page.locator(".panel").evaluate("node => node.scrollTo({top:node.scrollHeight, behavior:'smooth'})")
    page.wait_for_timeout(4500)
    page.locator("#tastecity").click()
    page.wait_for_timeout(4500)
    video = pathlib.Path(page.video.path())
    context.close()
    video.replace(output / f"{flow}-flow-1440x1000.webm")


def main(port, output):
    output = pathlib.Path(output)
    output.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:{port}/?demo=1&judge=1&population=25"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        record_flow(browser, url, output, "brand")
        record_flow(browser, url, output, "festival")
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
