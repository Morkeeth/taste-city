"""POST /api/scenario for the cached-first brand and festival engine."""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scenario_engine
import taste_city


class handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Server-Timing", f"total;dur={body.get('total_ms', 0)}" if isinstance(body, dict) else "total;dur=0")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        started = time.perf_counter()
        try:
            size = min(int(self.headers.get("Content-Length") or 0), 8000)
            body = json.loads(self.rfile.read(size) or b"{}")
            if body.get("demo") is True:
                import demo_replay
                try:
                    return self.reply(200, demo_replay.scenario(body))
                except ValueError as error:
                    return self.reply(400, {"error": str(error)})
            request = scenario_engine.clean_request(body)
            qloo_started = time.perf_counter()
            graph = taste_city.build(
                request["picks"], request["city"], prefer_cache=True,
                profile=f"{request['flow']}:{request['experiment']}",
            )
            qloo_ms = round((time.perf_counter() - qloo_started) * 1000, 1)
            result = scenario_engine.build(body, graph)
            result["qloo_ms"] = qloo_ms
            result["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
            return self.reply(200, result)
        except (scenario_engine.InvalidScenario, taste_city.InvalidTaste) as error:
            return self.reply(400, {"error": str(error), "total_ms": round((time.perf_counter() - started) * 1000, 1)})
        except taste_city.MissingKey as error:
            return self.reply(503, {"error": str(error), "total_ms": round((time.perf_counter() - started) * 1000, 1)})
        except taste_city.QlooUnavailable as error:
            return self.reply(502, {"error": str(error), "total_ms": round((time.perf_counter() - started) * 1000, 1)})
        except Exception as error:
            return self.reply(500, {"error": f"{type(error).__name__}: the scenario failed, try again.", "total_ms": round((time.perf_counter() - started) * 1000, 1)})
