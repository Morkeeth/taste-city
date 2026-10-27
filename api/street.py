"""GET /api/street?n=1&taken=a|b builds street n of the city (five villagers, 40 live Qloo calls, Wikipedia rows).
POST /api/street {"people": [{name, love, id, wikidata}]} adds places, podcasts and games for the plaza's villagers.
Vercel runs this file as a Python function; match_app.py runs the same handler locally."""
import json, os, sys, urllib.parse
from http.server import BaseHTTPRequestHandler
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import city

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
            n = int((q.get("n") or ["0"])[0] or 0)
            taken = [x for x in (q.get("taken", [""])[0] or "").split("|") if x.strip()][:8]
            r = city.street(n, taken)
            return self.reply(400 if r.get("error") else 200, r)
        except ValueError:
            return self.reply(400, {"error": "n must be a street number."})
        except city.village.MissingKey as e:   # the message names the variable, never a value
            return self.reply(503, {"error": str(e)})
        except Exception as e:
            return self.reply(500, {"error": f"{type(e).__name__}: the street failed, try again."})

    def do_POST(self):
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 8000)
            people = (json.loads(self.rfile.read(n) or b"{}").get("people") or [])
            people = [{k: str(p.get(k) or "")[:80] for k in ("name", "love", "id", "wikidata")} for p in people if isinstance(p, dict)]
            return self.reply(200, city.plaza(people))
        except city.village.MissingKey as e:
            return self.reply(503, {"error": str(e)})
        except Exception as e:
            return self.reply(500, {"error": f"{type(e).__name__}: the plaza failed, try again."})
