"""POST /api/brand-taste: public website to Qloo taste profile."""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import brand_profile
import core_context
from taste_city import QlooUnavailable
from taste_match import MissingKey


class handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        started = time.perf_counter()
        try:
            size = min(int(self.headers.get("Content-Length") or 0), 64000)
            body = json.loads(self.rfile.read(size) or b"{}")
            context=core_context.for_request(body) if body.get('local_core') is True else None
            if body.get("demo") is True:
                import demo_replay
                try:
                    result=demo_replay.website(body)
                    if context: result['local_context']=core_context.public(context)
                    return self.reply(200,result)
                except ValueError as error:
                    return self.reply(400, {"error": str(error)})
            if context:
                result=brand_profile.build(body.get('url'),context['graph']['city'],prefer_cache=True,local_filter=core_context.place_filter(context))
            else:
                result = brand_profile.build(body.get("url"), body.get("city") or "London", prefer_cache=True)
            if context: result['local_context']=core_context.public(context)
            result["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
            return self.reply(200, result)
        except (brand_profile.InvalidBrandURL, core_context.InvalidLocalContext) as error:
            return self.reply(400, {"error": str(error)})
        except (brand_profile.SiteUnavailable, QlooUnavailable) as error:
            return self.reply(502, {"error": str(error)})
        except MissingKey as error:
            return self.reply(503, {"error": str(error)})
        except Exception:
            return self.reply(500, {"error": "The brand taste profile failed. Try again."})
