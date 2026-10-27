"""Public website source only. No model or Qloo request."""
import json,os,sys
from http.server import BaseHTTPRequestHandler
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import brand_profile
class handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,code,body):
        data=json.dumps(body,ensure_ascii=False).encode();self.send_response(code)
        self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_POST(self):
        try:
            body=json.loads(self.rfile.read(min(int(self.headers.get('Content-Length') or 0),4000)) or b'{}')
            url,html=brand_profile.fetch_public_html(body.get('url'))
            return self.reply(200,{'page':brand_profile.page_profile(url,html),'notice':'Website text only. Audience interests require your confirmation; no Qloo request was made.'})
        except brand_profile.InvalidBrandURL as e:return self.reply(400,{'error':str(e)})
        except brand_profile.SiteUnavailable as e:return self.reply(502,{'error':str(e)})
        except Exception:return self.reply(500,{'error':'The website source could not be read.'})
