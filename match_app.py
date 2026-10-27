"""Local server for Taste City and Taste Match. Run: python3 match_app.py, then open http://127.0.0.1:8811/
Serves village.html at / (the front door), match.html at /match, pair.html at /pair and /pair/<id> (the share
loop), and the same /api/match, /api/village and /api/pair handlers that the host runs. Keys come from QLOO_API_KEY and ANTHROPIC_API_KEY in the environment."""
import os, pathlib, sys
from http.server import ThreadingHTTPServer
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from api.match import handler as Api   # the hosted function
from api.village import handler as VillageApi
from api.street import handler as StreetApi
from api.ask import handler as AskApi
from api.pair import handler as PairApi
from api.panel import handler as PanelApi
from api.taste import handler as TasteApi
from api.scenario import handler as ScenarioApi
from api.brand_taste import handler as BrandTasteApi
from api.brand_source import handler as BrandSourceApi
from api.agent_plan import handler as AgentPlanApi

HERE = pathlib.Path(__file__).resolve().parent
PAGES = {"/": "village.html", "/village": "village.html", "/village.html": "village.html",
         "/match": "match.html", "/match.html": "match.html", "/pair": "pair.html", "/pair.html": "pair.html",
         "/panel": "panel.html", "/panel.html": "panel.html",
         "/vendor/three.module.min.js": "vendor/three.module.min.js", "/vendor/three.core.min.js": "vendor/three.core.min.js"}
KEYS = ("QLOO_API_KEY", "ANTHROPIC_API_KEY")

class H(Api):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/village":
            return VillageApi.do_GET(self)
        if path == "/api/street":
            return StreetApi.do_GET(self)
        if path == "/api/pair":
            return PairApi.do_GET(self)
        if path.startswith("/pair/"):   # the friend's link; the page reads its id from the path
            path = "/pair"
        if path in PAGES:
            b = (HERE / PAGES[path]).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8" if path.endswith(".js") else "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            return self.wfile.write(b)
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/street":
            return StreetApi.do_POST(self)
        if path == "/api/ask":
            return AskApi.do_POST(self)
        if path == "/api/pair":
            return PairApi.do_POST(self)
        if path == "/api/panel":
            return PanelApi.do_POST(self)
        if path == "/api/taste":
            return TasteApi.do_POST(self)
        if path == "/api/scenario":
            return ScenarioApi.do_POST(self)
        if path == "/api/brand_source":
            return BrandSourceApi.do_POST(self)
        if path == "/api/agent-plan":
            return AgentPlanApi.do_POST(self)
        if path == "/api/brand-taste":
            return BrandTasteApi.do_POST(self)
        return Api.do_POST(self)

def missing_keys(env=os.environ):
    """Names of the keys the app needs and cannot see. Names only, never a value."""
    return [k for k in KEYS if not env.get(k)]

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8811
    for k in missing_keys():
        print(f"{k} is not set. {'The village needs it.' if k == 'QLOO_API_KEY' else 'Taste Match (the agent) needs it; the village game runs without it.'}", flush=True)
    print(f"Taste City on http://127.0.0.1:{port}/  (Taste Match at /match)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
