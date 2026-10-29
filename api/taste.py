"""POST /api/taste with three picks. Live Qloo first, recorded cache fallback."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import taste_city
import core_context
from qloo_client import BudgetSpent
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
                return self.reply(200, sample_demo.local_discovery(body) if body.get('core') is True else sample_demo.discovery(body))
            result = taste_city.build(body.get("picks"), body.get("city") or "London", local=True, radius=body.get("radius", 1000), discovery=body.get("discovery", True), core=body.get("core") is True)
            if body.get('core') is True:
                try:
                    result['planning_token']=core_context.issue(result)
                except core_context.InvalidLocalContext:
                    result['planning_token']=None
                    result['planning_notice']='This local recording can be read, but live business planning evidence is unavailable. Refresh when the server key and providers are available.'
            return self.reply(200, result)
        except (taste_city.InvalidTaste, core_context.InvalidLocalContext) as error:
            return self.reply(400, {"error": str(error)})
        except (json.JSONDecodeError, LocationInvalid) as error:
            return self.reply(400, {"error": str(error)})
        except taste_city.MissingKey as error:
            return self.reply(503, {"error": str(error)})
        except (taste_city.QlooUnavailable, LocationUnavailable, BudgetSpent) as error:
            return self.reply(502, {"error": str(error)})
        except Exception as error:
            return self.reply(500, {"error": f"{type(error).__name__}: the taste city failed, try again."})
