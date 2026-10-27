"""POST /api/agent-plan: live Qloo-backed adaptive planning, no model API."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agent_planner
import scenario_engine
import taste_city
from qloo_client import BudgetSpent


class handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, body):
        payload = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        try:
            size = min(int(self.headers.get('Content-Length') or 0), 8000)
            body = json.loads(self.rfile.read(size) or b'{}')
            return self.reply(200, agent_planner.plan(body))
        except (ValueError, scenario_engine.InvalidScenario, taste_city.InvalidTaste) as error:
            return self.reply(400, {'error': str(error)})
        except taste_city.MissingKey as error:
            return self.reply(503, {'error': str(error)})
        except (taste_city.QlooUnavailable, agent_planner.AgentUnavailable, BudgetSpent) as error:
            return self.reply(502, {'error': str(error)})
        except Exception:
            return self.reply(500, {'error': 'The live Taste Agent could not finish this plan.'})
