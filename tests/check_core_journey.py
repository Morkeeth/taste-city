"""Portable no-key browser journey: audience -> local sample -> personal/business plan.

Run after installing requirements-dev.txt and a Playwright browser:
  python3 tests/check_core_journey.py
Use --channel chrome for an installed Chrome. No live provider call is allowed.
"""
import argparse
import json
from pathlib import Path
import sys
import threading
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import match_app
from playwright.sync_api import sync_playwright


def check(channel=None):
    server=ThreadingHTTPServer(('127.0.0.1',0),match_app.H)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    rows=[]
    try:
        with patch('qloo_client.Live.get',side_effect=AssertionError('Sample attempted a provider request')),sync_playwright() as pw:
            options={'headless':True,'args':['--enable-unsafe-swiftshader']}
            if channel:options['channel']=channel
            browser=pw.chromium.launch(**options)
            try:
                for purpose in ('consumer','business'):
                    page=browser.new_page(viewport={'width':390,'height':844})
                    errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{server.server_address[1]}/?demo=1&setup=1')
                    page.locator('#setup'+purpose).click()
                    assert page.locator('body').get_attribute('data-journey-stage')=='audience'
                    page.locator('#trytaste').click()
                    page.locator('[data-local-place]').first.wait_for()
                    assert page.locator('#planlocal').is_disabled()
                    assert page.locator('#runbrand').count()==0
                    page.locator('#culturedoors').click()
                    assert page.locator('[data-culture-door]').count()==5
                    page.locator('#backlocalculture').click()
                    page.locator('[data-local-place]').first.click()
                    page.locator('#planlocal').click()
                    assert page.locator('[data-local-context]').count()==1
                    if purpose=='consumer':
                        page.locator('#savelocal').click()
                        saved=page.evaluate("JSON.parse(localStorage.getItem('taste-city-local-plan'))")
                        assert saved['local_context']['mode']=='synthetic'
                        assert len(saved['local_context']['places'])==1
                        page.locator('#backlocal').click()
                        page.locator('#togame').click()
                        page.locator('.gift').wait_for()
                    else:
                        page.locator('#runbrand').click()
                        page.locator('#chooseideaA').wait_for()
                        page.locator('#chooseideaA').click()
                        page.locator('#buyernotes').fill('Fictional test: check real availability before any commitment.')
                        page.locator('#savebuyer').click()
                        saved=page.evaluate("JSON.parse(localStorage.getItem('taste-city-buyer-brief'))")
                        assert saved['local_context']['mode']=='synthetic'
                        assert len(saved['local_context']['places'])==1
                    assert not errors,errors
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                    rows.append({'purpose':purpose,'saved_places':len(saved['local_context']['places']),'mode':'synthetic','page_errors':errors,'horizontal_scroll':False})
                    page.close()
            finally:browser.close()
    finally:server.shutdown();server.server_close()
    return {'pass':True,'provider_calls':0,'viewport':'390x844','journeys':rows}

if __name__=='__main__':
    args=argparse.ArgumentParser();args.add_argument('--channel');opts=args.parse_args()
    print(json.dumps(check(opts.channel),indent=2))
