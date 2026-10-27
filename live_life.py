"""How each archetype lives: one live Qloo pass per character, saved to cache/life.json (gitignored).
Run: cd ~/CODE/hack-proofs/qloo/hipster && python3 live_life.py
The key is read from QLOO_API_KEY, or else the macOS keychain, into this process only, sent as X-Api-Key, and never printed or written.
Each archetype is seeded with its 3 most tag-dense tribe artists (radar.anchors). Per archetype: places in London,
movies, TV shows, brands, and the audience demographics. 5 calls x 6 archetypes = 30 calls, hard cap 40."""
import json, os, pathlib, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
import backtest, radar

HERE = pathlib.Path(__file__).resolve().parent
BASE, CAP, CITY = "https://hackathon.api.qloo.com", 40, "London"
DOMAINS = [("place", "urn:entity:place", {"filter.location.query": CITY, "take": 8}),
           ("movie", "urn:entity:movie", {"take": 5}),
           ("tv_show", "urn:entity:tv_show", {"take": 5}),
           ("brand", "urn:entity:brand", {"take": 5}),
           ("demographics", "urn:demographics", {})]

def client(key):
    log = []
    def call(label, params):
        if len(log) >= CAP:
            raise SystemExit(f"{CAP} call cap reached")
        url = BASE + "/v2/insights?" + urllib.parse.urlencode(params, safe=":,")
        req = urllib.request.Request(url, headers={"X-Api-Key": key, "User-Agent": "Hipster/2"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                status, raw = r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read().decode()
        if key in raw:
            raise SystemExit("key echoed in a response, refusing to save")
        body = json.loads(raw) if raw.strip().startswith("{") else {"text": raw[:500]}
        log.append({"id": f"L{len(log) + 1:02}", "label": label, "params": params, "status": status,
                    "seconds": round(time.time() - t0, 2), "body": body})
        print(log[-1]["id"], label, status, flush=True)
        if status in (401, 403, 429):
            raise SystemExit(f"HTTP {status}: stop")
        return log[-1]
    return call, log

def main():
    key = os.environ.get("QLOO_API_KEY") or subprocess.check_output(
        ["security", "find-generic-password", "-s", "QLOO_API_KEY", "-a", "qloo-hackathon", "-w"], text=True).strip()
    u, series, _ = backtest.load_series()
    call, log = client(key)
    out = {"fetched": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "city": CITY, "archetypes": {}}
    try:
        for a in radar.ARCHETYPES:
            ids = radar.anchors(u, a, series)
            seed = {"signal.interests.entities": ",".join(ids)}
            out["archetypes"][a["id"]] = {"anchors": [{"id": i, "name": u[i]["name"]} for i in ids], "calls": {}}
            for name, ftype, extra in DOMAINS:
                c = call(f"{a['id']} {name}", {"filter.type": ftype, **seed, **extra})
                out["archetypes"][a["id"]]["calls"][name] = c["id"]
    finally:
        out["calls"] = log
        (HERE / "cache").mkdir(exist_ok=True)
        (HERE / "cache" / "life.json").write_text(json.dumps(out, indent=1))
        print(len(log), "calls, saved cache/life.json")

if __name__ == "__main__":
    sys.exit(main())
