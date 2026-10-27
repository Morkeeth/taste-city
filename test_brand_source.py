"""Exercise the actual website-source HTTP route without any provider."""
import json,threading,unittest,urllib.request,urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import match_app
from test_brand_profile import HTML
class SourceRoute(unittest.TestCase):
 def test_source_route_returns_page_with_no_qloo_and_rejects_private_url(self):
  server=ThreadingHTTPServer(('127.0.0.1',0),match_app.H)
  threading.Thread(target=server.serve_forever,daemon=True).start()
  def request(url):
   req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/brand_source',data=json.dumps({'url':url}).encode(),headers={'Content-Type':'application/json'})
   return urllib.request.urlopen(req)
  try:
   with patch('brand_profile.fetch_public_html',return_value=('https://example.com/',HTML)),patch('brand_profile.Live',side_effect=AssertionError('Provider must not run')):
    result=json.load(request('https://example.com/'))
    self.assertIn('North Star Coffee',result['page']['title'])
    self.assertIn('no Qloo request',result['notice'])
   with self.assertRaises(urllib.error.HTTPError) as caught: request('http://127.0.0.1/')
   self.assertEqual(caught.exception.code,400)
  finally:server.shutdown();server.server_close()
