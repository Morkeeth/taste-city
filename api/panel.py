"""POST /api/panel {regulars: "one love per line"} builds 25 live Qloo-backed people."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import panel


class handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, body):
        raw = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 4000)
            req = json.loads(self.rfile.read(n) or b"{}")
            return self.reply(200, panel.build(req.get("regulars") or ""))
        except ValueError as error:
            return self.reply(400, {"error": str(error)})
        except panel.village.MissingKey as error:
            return self.reply(503, {"error": str(error)})
        except Exception as error:
            return self.reply(500, {"error": f"{type(error).__name__}: the panel failed, try again."})
