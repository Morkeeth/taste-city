"""POST /api/ask {"q": "closest", "arg": "for who_loves", "city": {"villagers": [...]}} answers one question about the
city from the Qloo calls that built it. Only who_loves makes new Qloo calls (3). Vercel runs this file as a Python
function; match_app.py runs the same handler locally."""
import json, os, sys
from http.server import BaseHTTPRequestHandler
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import city_ask

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

    def do_POST(self):
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 2_000_000)
            req = json.loads(self.rfile.read(n) or b"{}")
            r = city_ask.ask(req.get("city") or {}, str(req.get("q") or ""), str(req.get("arg") or ""))
            return self.reply(400 if r.get("error") else 200, r)
        except city_ask.village.MissingKey as e:   # the message names the variable, never a value
            return self.reply(503, {"error": str(e)})
        except Exception as e:
            return self.reply(500, {"error": f"{type(e).__name__}: the question failed, try again."})
