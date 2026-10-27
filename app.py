"""Hipster web app. Run: python3 app.py --port 8792, then open http://127.0.0.1:8792/
Recorded Qloo calls and cached Wikipedia views only. This file has no network client."""
import argparse, json, pathlib, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import backtest, life, radar, story

HERE = pathlib.Path(__file__).resolve().parent

class Data:
    def __init__(self, universe, series, summary=None, lives=None, stories=None):
        self.universe, self.series, self.summary, self.lives, self.stories = universe, series, summary, lives or {}, stories or {}
        self.agent = agent_stories(self.stories)
        self.last = max(len(w) for w in series.values()) - 1
        self.weeks = [str(backtest.week_end(t)) for t in range(backtest.week_index(backtest.TEST[0]), self.last + 1)]
        self.records = {a["id"]: radar.track_record(universe, series, a) for a in radar.ARCHETYPES}

    def archetypes(self):
        return [{"id": a["id"], "name": a["name"], "blurb": a["blurb"], "tags": sorted(a["tags"]),
                 "members": len(radar.members(self.universe, a, self.series)), "record": self.records[a["id"]]}
                for a in radar.ARCHETYPES]

    def cutoff(self, aid, week):
        a = radar.BY_ID.get(aid)
        if not a or (week is not None and week not in self.weeks):
            return None, None
        return a, backtest.week_index(week) if week else self.last

    def radar(self, aid, week):
        a, t = self.cutoff(aid, week)
        if not a:
            return None
        out = radar.calls(self.universe, self.series, a, t)
        out.update({"archetype": aid, "week": str(backtest.week_end(t)), "now": t == self.last})
        return out

    def city(self, aid, week):
        """The 3D map: every artist in the tribe, grouped by the Qloo similar-artist call it first appeared in.
        views is the Wikipedia total for the cutoff week only, so the map never shows the future."""
        a, t = self.cutoff(aid, week)
        if not a:
            return None
        blocks = {}
        for i in radar.members(self.universe, a, self.series):
            e, w = self.universe[i], self.series[i]
            blocks.setdefault(e["seen_in"][0]["anchor"], []).append({"id": i, "name": e["name"], "views": w[t] if t < len(w) else None})
        districts = [{"anchor": k, "members": sorted(v, key=lambda m: m["name"])} for k, v in blocks.items()]
        districts.sort(key=lambda d: (-len(d["members"]), d["anchor"]))
        return {"archetype": aid, "week": str(backtest.week_end(t)), "districts": districts}

CLOCK = {"Mon": "08:00", "Tue": "19:00", "Wed": "21:00", "Thu": "19:00", "Fri": "23:00", "Sat": "11:00", "Sun": "21:00"}

def agent_stories(stories):
    """The agent's weeks (agent_week.py) in the shape of a story, beside the rule's. Only weeks that passed validate() are shown.
    Each row keeps the rule's pick for the same day, so the page can show both."""
    f = HERE / "cache" / "agent-weeks.json"
    if not f.exists() or not stories:
        return {}
    out = {}
    for aid, w in json.loads(f.read_text()).get("weeks", {}).items():
        if aid not in stories or w.get("problems") or not w.get("week"):
            continue
        rule = {r["day"]: r for r in stories[aid]["week"]}
        week = [{"day": r["day"], "clock": CLOCK[r["day"]], "what": r["what"], "name": r.get("name"), "call": r.get("call"), "why": r.get("why"),
                 "at": "place" if r.get("name") and r["what"] in ("eat", "out", "late", "day") else "home", "rule": rule.get(r["day"], {}).get("name")}
                for r in w["week"]]
        out[aid] = {**stories[aid], "week": week, "tension": None, "by": "agent",
                    "agent": {**w["cost"], "model": w["model"], "ran": w["ran"], "same": sum(1 for r in week if r["name"] == r["rule"])}}
    return out

VENDOR = {"/vendor/three.module.min.js", "/vendor/three.core.min.js"}

def handler(data):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json"):
            b = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_HEAD(self):
            u = urllib.parse.urlparse(self.path)
            if u.path == "/" or u.path in VENDOR:
                self.send_response(200)
                self.end_headers()
                return
            self.send_response(404)
            self.end_headers()

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path == "/":
                return self.send(200, (HERE / "hipster.html").read_bytes(), "text/html; charset=utf-8")
            if u.path in VENDOR:
                return self.send(200, (HERE / u.path[1:]).read_bytes(), "text/javascript; charset=utf-8")
            if u.path == "/api/archetypes":
                return self.send(200, {"archetypes": data.archetypes(), "weeks": data.weeks, "backtest": data.summary})
            if u.path == "/api/radar":
                r = data.radar(q.get("a", [""])[0], q.get("week", [None])[0])
                return self.send(200, r) if r else self.send(404, {"error": "unknown archetype or week"})
            if u.path == "/api/life":
                r = data.lives.get(q.get("a", [""])[0])
                return self.send(200, r) if r else self.send(404, {"error": "no life recorded for this archetype"})
            if u.path == "/api/stories":
                S = data.agent if q.get("by", [""])[0] == "agent" else data.stories
                if not S:
                    return self.send(404, {"error": "no stories recorded"})
                return self.send(200, {"stories": S, "rival": {k: story.rival(S, k) for k in S}})
            if u.path == "/api/city":
                r = data.city(q.get("a", [""])[0], q.get("week", [None])[0])
                return self.send(200, r) if r else self.send(404, {"error": "unknown archetype or week"})
            self.send(404, {"error": "not found"})
    return H

def serve(data, port):
    return ThreadingHTTPServer(("127.0.0.1", port), handler(data))

def load():
    u, series, _ = backtest.load_series()
    bt = HERE / "cache" / "backtest.json"
    summary = None
    if bt.exists():
        b = json.load(open(bt))
        summary = {k: {"summary": b[k]["summary"], "verdict": b[k]["verdict"]} for k in ("dev", "test")}
    return Data(u, series, summary, life.load(), story.load())

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8792)
    port = ap.parse_args().port
    srv = serve(load(), port)
    print(f"Hipster on http://127.0.0.1:{port}/")
    srv.serve_forever()
