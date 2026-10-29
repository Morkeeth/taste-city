"""POST /api/taste with three picks. Live Qloo first, recorded cache fallback."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import taste_city
from local_places import LocationInvalid, LocationUnavailable


class handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        try:
            size = min(int(self.headers.get("Content-Length") or 0), 4000)
            body = json.loads(self.rfile.read(size) or b"{}")
            if body.get('demo') is True:
                import sample_demo
                return self.reply(200, sample_demo.discovery(body))
            result = taste_city.build(body.get("picks"), body.get("city") or "London", local=True, radius=body.get("radius", 1000), discovery=body.get("discovery", True))
            return self.reply(200, result)
        except taste_city.InvalidTaste as error:
            return self.reply(400, {"error": str(error)})
        except (json.JSONDecodeError, LocationInvalid) as error:
            return self.reply(400, {"error": str(error)})
        except taste_city.MissingKey as error:
            return self.reply(503, {"error": str(error)})
        except (taste_city.QlooUnavailable, LocationUnavailable) as error:
            return self.reply(502, {"error": str(error)})
        except Exception as error:
            return self.reply(500, {"error": f"{type(error).__name__}: the taste city failed, try again."})
