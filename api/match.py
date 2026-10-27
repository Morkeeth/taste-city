"""POST /api/match {"a": [3 loves], "b": [3 loves], "city": "London"}. Vercel runs this file as a Python function;
match_app.py runs the same handler locally. Keys come from the host's environment only."""
import json, os, sys
from http.server import BaseHTTPRequestHandler
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import taste_match

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
            n = min(int(self.headers.get("Content-Length") or 0), 4000)
            req = json.loads(self.rfile.read(n) or b"{}")
            a, b = req.get("a") or [], req.get("b") or []
            if not isinstance(a, list) or not isinstance(b, list) or not any(str(x).strip() for x in a) or not any(str(x).strip() for x in b):
                return self.reply(400, {"error": "Both people need at least one thing they love."})
            return self.reply(200, taste_match.match([str(x) for x in a], [str(x) for x in b], str(req.get("city") or "London"),
                                                    names=(str(req.get("an") or "A"), str(req.get("bn") or "B"))))
        except taste_match.MissingKey as e:   # the message names the variable, never a value
            return self.reply(503, {"error": str(e)})
        except Exception as e:
            return self.reply(500, {"error": f"{type(e).__name__}: the match failed, try again."})
