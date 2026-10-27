"""The agent writes each person's week (PLAN.md slice 1). A model loop with 3 Qloo tools: search, insights by type,
places in a city. Every week row must cite a call ID the agent made in this run (A01 ...), and the named thing must be in
that call's answer; validate() fails the row otherwise. Raw Qloo answers stay in cache/agent-weeks.json (gitignored).
Cost per week is logged from the model's own receipt.
Run: python3 agent_week.py poet        (one person)   python3 agent_week.py all   (all six)   python3 agent_week.py monk,wine
The Qloo key comes from QLOO_API_KEY, else the macOS keychain, into this process only. ask_model() is the only part that knows
which model runs; tonight it is Claude Code headless (claude -p) on the subscription, the hosted slice swaps that one function."""
import json, os, pathlib, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
import life, radar

HERE = pathlib.Path(__file__).resolve().parent
BASE, MODEL = "https://hackathon.api.qloo.com", "claude-sonnet-5-5"
CITY = os.environ.get("HIPSTER_CITY", "London")   # HIPSTER_CITY=Paris writes cache/agent-weeks-paris.json
OUT = HERE / "cache" / ("agent-weeks.json" if CITY == "London" else f"agent-weeks-{CITY.lower()}.json")
TURNS, QLOO_CAP, USD_CAP = 10, 9, 1.50   # per person
DAYS = [("Mon", "listen"), ("Tue", "eat"), ("Wed", "film"), ("Thu", "out"), ("Fri", "late"), ("Sat", "day"), ("Sun", "show")]
TYPES = ("artist", "movie", "tv_show", "brand", "book", "podcast", "videogame")

SYSTEM = f"""You plan one week in {CITY} for a person whose taste you only know from three artists they love.
You may only name things a Qloo tool gave you. Tools:
- search: args {{"query": str, "type": one of {list(TYPES)}}}. Finds Qloo entities by name, to get their entity_id.
- insights: args {{"type": one of {list(TYPES)}, "seeds": [entity_id, ...], "take": 1-8}}. What people with this taste also love.
- places: args {{"seeds": [entity_id, ...], "take": 1-25, "kind": optional Qloo place genre such as restaurant, cafe, bar, wine_bar, pub, nightclub}}.
  Places in {CITY} people with this taste love, with their kind and ambience. Without kind you mostly get landmarks and galleries.
- finish: args {{"week": [7 rows]}}. One row per day, in this order: {", ".join(f"{d} {w}" for d, w in DAYS)}.
  listen = an artist new to them (not one of the three). eat = a place to eat. film = a film at home. out = a bar or pub.
  late = a club or music venue. day = a daytime place (record shop, gallery, park, market, shop). show = a TV show at home.
  Row: {{"day": "Mon", "what": "listen", "name": exact name from a tool result, or null if no result fits,
  "call": the call ID of the result you took it from (or of the call that had nothing that fits), "why": max 12 words}}.
A null name is better than a wrong one. Never use a name you know from memory. You have {QLOO_CAP} tool calls and {TURNS} turns.
Reply with one action per turn."""

SCHEMA = {"type": "object", "required": ["action", "args"], "properties": {
    "thought": {"type": "string"}, "action": {"type": "string", "enum": ["search", "insights", "places", "finish"]},
    "args": {"type": "object"}}}

def ask_model(system, prompt):
    """One model turn. Returns (action dict, cost in USD). The only model-specific code in this file."""
    cmd = ["claude", "-p", "--output-format", "json", "--model", MODEL, "--tools", "", "--no-session-persistence",
           "--setting-sources", "", "--system-prompt", system, "--json-schema", json.dumps(SCHEMA)]
    for attempt in range(2):
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=300, cwd="/tmp")
        try:
            d = json.loads(r.stdout)
            if d.get("structured_output"):
                return d["structured_output"], float(d.get("total_cost_usd") or 0)
        except json.JSONDecodeError:
            pass
    raise RuntimeError(f"model gave no action: {r.stdout[-300:]} {r.stderr[-300:]}")

def qloo(key, log):
    def get(path, params):
        if len(log) >= QLOO_CAP:
            return None
        url = BASE + path + "?" + urllib.parse.urlencode(params, safe=":,")
        req = urllib.request.Request(url, headers={"X-Api-Key": key, "User-Agent": "Hipster/agent"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                status, raw = r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read().decode()
        if key in raw:
            raise SystemExit("key echoed in a response, refusing to save")
        body = json.loads(raw) if raw.strip().startswith("{") else {"text": raw[:500]}
        log.append({"id": f"A{len(log) + 1:02}", "path": path, "params": params, "status": status,
                    "seconds": round(time.time() - t0, 2), "body": body})
        if status in (401, 403, 429):
            raise SystemExit(f"HTTP {status}: stop")
        return log[-1]
    return get

def entities(call):
    r = call["body"].get("results", [])
    return r.get("entities", []) if isinstance(r, dict) else (r if isinstance(r, list) else [])

def brief(call):
    """What the model sees of a call: names, IDs, and for places their kind and ambience. Short on purpose."""
    rows = []
    for e in entities(call):
        row = {"name": e.get("name"), "entity_id": e.get("entity_id")}
        if e.get("query", {}).get("affinity") is not None:
            row["affinity"] = life.aff(e)
        if call["path"] == "/v2/insights" and call["params"].get("filter.type") == "urn:entity:place":
            k1, k2 = life.kinds(e)
            row.update({"kind": k1 or k2[:60], "ambience": sorted({t["name"] for t in (e.get("tags") or []) if ":ambience:" in t.get("id", "")})[:4],
                        "area": (e.get("properties", {}).get("neighborhood") or "").strip() or None})
        rows.append(row)
    return {"call": call["id"], "status": call["status"], "results": rows}

def run_tool(get, action, args):
    seeds = ",".join(str(s) for s in (args.get("seeds") or [])[:5])
    t = args.get("type") if args.get("type") in TYPES else "artist"
    if action == "search":
        c = get("/search", {"query": str(args.get("query", ""))[:80], "types": f"urn:entity:{t}", "take": 5})
    elif action == "insights":
        c = get("/v2/insights", {"filter.type": f"urn:entity:{t}", "signal.interests.entities": seeds, "take": max(1, min(8, int(args.get("take") or 5)))})
    elif action == "places":
        c = get("/v2/insights", {"filter.type": "urn:entity:place", "signal.interests.entities": seeds,
                                 "filter.location.query": CITY, "take": max(1, min(25, int(args.get("take") or 20))),
                                 **({"filter.tags": f"urn:tag:genre:place:{k}"} if (k := str(args.get("kind") or "")).replace("_", "").isalpha() else {})})
    else:
        return {"error": f"unknown action {action}"}
    return brief(c) if c else {"error": f"Qloo call cap of {QLOO_CAP} reached, finish now"}

def validate(week, log, anchors=()):
    """Problems with a week, empty if none. A row needs a known day, a call ID from this run, and a name that call returned."""
    by_id, bad = {c["id"]: c for c in log}, []
    if [r.get("day") for r in week] != [d for d, _ in DAYS]:
        bad.append("days are not Mon to Sun in order")
    for r in week:
        cid, name = r.get("call"), r.get("name")
        if not cid:
            bad.append(f"{r.get('day')}: no call ID"); continue
        if cid not in by_id:
            bad.append(f"{r.get('day')}: call {cid} was not made in this run"); continue
        if name is not None and name not in {e.get("name") for e in entities(by_id[cid])}:
            bad.append(f"{r.get('day')}: {name} is not in call {cid}")
        if name in anchors:
            bad.append(f"{r.get('day')}: {name} is one of the three artists they already love")
    return bad

def plan(aid, key, d):
    A = radar.BY_ID[aid]
    anchors = [x["name"] for x in d["archetypes"][aid]["anchors"]]
    log, get, cost, turns, t0 = [], None, 0.0, [], time.time()
    get = qloo(key, log)
    history = [f"Person: {life.NAMES[aid]}, a {A['name']} ({A['blurb']}). The three artists they love: {', '.join(anchors)}."]
    week, problems = None, []
    for n in range(TURNS):
        act, usd = ask_model(SYSTEM, "\n\n".join(history) + f"\n\nTurn {n + 1} of {TURNS}. Qloo calls used: {len(log)} of {QLOO_CAP}. Your action:")
        cost += usd
        a, args = act.get("action"), act.get("args") or {}
        turns.append({"turn": n + 1, "action": a, "args": args, "thought": (act.get("thought") or "")[:300], "usd": round(usd, 4)})
        if a == "finish":
            week = args.get("week") or []
            problems = validate(week, log, anchors)
            if not problems or n == TURNS - 1:
                break
            history.append(f"You: finish. Rejected, fix these and finish again: {problems}")
            continue
        res = run_tool(get, a, args)
        history.append(f"You: {a} {json.dumps(args, ensure_ascii=False)}\nResult: {json.dumps(res, ensure_ascii=False)}")
        if cost > USD_CAP:
            history.append("Budget reached. Finish now with what you have.")
    return {"id": aid, "person": life.NAMES[aid], "archetype": A["name"], "city": CITY, "model": MODEL, "anchors": anchors,
            "week": week, "problems": problems if week is not None else ["agent never finished"],
            "cost": {"usd": round(cost, 4), "turns": len(turns), "qloo_calls": len(log), "seconds": round(time.time() - t0, 1)},
            "turns": turns, "calls": log}

def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "poet"
    key = os.environ.get("QLOO_API_KEY") or subprocess.check_output(
        ["security", "find-generic-password", "-s", "QLOO_API_KEY", "-a", "qloo-hackathon", "-w"], text=True).strip()
    d = json.loads(life.LIFE.read_text())
    out = json.loads(OUT.read_text()) if OUT.exists() else {"weeks": {}}
    for aid in (list(d["archetypes"]) if which == "all" else which.split(",")):
        w = plan(aid, key, d)
        out["weeks"][aid] = {**w, "ran": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
        print(aid, w["person"], "cost", w["cost"], "problems", w["problems"], flush=True)
        for r in w["week"] or []:
            print("  ", r.get("day"), r.get("what"), r.get("name"), r.get("call"), "|", r.get("why"))

if __name__ == "__main__":
    main()
