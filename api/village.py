"""GET /api/village?me=one+love&loves=a|b. Builds a five-resident taste city from live Qloo calls.
Vercel runs this file as a Python function; match_app.py runs the same handler locally."""
import json, os, sys, urllib.parse
from http.server import BaseHTTPRequestHandler
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import village

class handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, body):
        b = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        try:
            loves = [x for x in (q.get("loves", [""])[0] or "").split("|") if x.strip()]
            r = village.village(loves, q.get("me", [""])[0])
            return self.reply(502 if r.get("error") else 200, r)
        except village.MissingKey as e:   # the message names the variable, never a value
            return self.reply(503, {"error": str(e)})
        except Exception as e:
            return self.reply(500, {"error": f"{type(e).__name__}: the village failed, try again."})
