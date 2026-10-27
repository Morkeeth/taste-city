"""Taste Match: two people, three loves each, one city. Where do their tastes meet?
Code resolves the six loves and fans out Qloo calls for each person and for both together (parallel, capped).
Then an agent reads those answers, may make up to EXTRA more Qloo calls, and finishes with cited picks.
validate() rejects any pick whose name is not in the call it cites. Nothing is recorded: this runs live.
Keys: QLOO_API_KEY and ANTHROPIC_API_KEY from the environment. Set TASTE_KEYCHAIN=1 to fall back to the
macOS keychain (a developer convenience, off by default so a missing key says so by name).
Run: python3 taste_match.py "Radiohead,Fleabag,Wes Anderson" "Beyonce,Succession,Nobu" London"""
import json, os, subprocess, sys, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor
import anthropic
from qloo_client import Live

MODEL = "claude-sonnet-5-5"
EXTRA, TURNS, QLOO_CAP = 3, 4, 24
LOVE_TYPES = ("artist", "movie", "tv_show", "book", "brand", "podcast", "videogame", "place")
OUT_TYPES = ("artist", "movie", "tv_show", "place")

class MissingKey(RuntimeError):
    pass

def secret(env, service, account=None):
    """The key named by `env`. Never printed, never part of an error message."""
    v = os.environ.get(env)
    if v:
        return v
    if os.environ.get("TASTE_KEYCHAIN") == "1":
        cmd = ["security", "find-generic-password", "-s", service, "-w"] + (["-a", account] if account else [])
        try:
            v = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            v = ""
        if v:
            return v
    raise MissingKey(f"Set {env} in the environment (export {env}=...) and start again.")

def entities(call):
    r = (call.get("response") or {}).get("results", [])
    return r.get("entities", []) if isinstance(r, dict) else (r if isinstance(r, list) else [])

def short(e):
    t = (e.get("types") or [e.get("subtype") or ""])[0].split(":")[-1]
    row = {"name": e.get("name"), "id": e.get("entity_id"), "type": t}
    p = e.get("properties") or {}
    if p.get("address"):
        row["address"] = p["address"][:80]
    aff = (e.get("query") or {}).get("affinity")
    if aff is not None:
        row["affinity"] = round(float(aff), 3)
    return row

class Run:
    def __init__(self, qloo, city):
        self.q, self.city, self.calls = qloo, city, []

    def get(self, purpose, path, params):
        c = self.q.get(purpose, path, params)
        c["url"] = path + "?" + urllib.parse.urlencode(params, safe=":,")   # no host, never the key
        self.calls.append(c)
        return c

    def resolve(self, text):
        c = self.get(f"find {text}", "/search", {"query": text[:80], "types": ",".join(f"urn:entity:{t}" for t in LOVE_TYPES), "take": 3})
        hits = entities(c)
        return (short(hits[0]) | {"asked": text, "call": c["id"]}) if hits else {"asked": text, "name": None, "call": c["id"]}

    def insights(self, purpose, ftype, seeds, take=8, tag=""):
        p = {"filter.type": f"urn:entity:{ftype}", "signal.interests.entities": ",".join(seeds[:6]), "take": take}
        if ftype == "place":
            p["filter.location.query"] = self.city
        if tag:
            p["filter.tags"] = tag
        return self.get(purpose, "/v2/insights", p)

def brief(call):
    return {"call": call["id"], "purpose": call["purpose"], "status": call["status"], "results": [short(e) for e in entities(call)]}

def fan_out(run, a_loves, b_loves):
    with ThreadPoolExecutor(6) as ex:
        found = list(ex.map(run.resolve, a_loves + b_loves))
    A, B = found[:len(a_loves)], found[len(a_loves):]
    sa, sb = [x["id"] for x in A if x.get("name")], [x["id"] for x in B if x.get("name")]
    if not sa or not sb:
        return A, B, [], {}
    jobs = [(f"{who} {t}", t, s) for t in OUT_TYPES for who, s in (("A only", sa), ("B only", sb), ("both", sa + sb))]
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda j: run.insights(*j), jobs))
    seen = {"A only": {}, "B only": {}}
    for (purpose, t, _), c in zip(jobs, res):
        who = purpose.rsplit(" ", 1)[0]
        if who in seen:
            seen[who].update({e.get("entity_id"): 1 for e in entities(c)})
    briefs = []
    for (purpose, t, _), c in zip(jobs, res):
        b = brief(c)
        if purpose.startswith("both"):
            for r in b["results"]:
                r["in_A_list"], r["in_B_list"] = r["id"] in seen["A only"], r["id"] in seen["B only"]
        briefs.append(b)
    return A, B, briefs, seen

SYSTEM = """Two people want to talk about taste. You get what each loves and live Qloo taste-graph answers:
what people with A's taste love, with B's, and with both tastes together. Rows from the "both" calls carry
in_A_list / in_B_list: true means that thing also came up for that person alone. A row in both lists is a real bridge.
Find where their tastes meet, and what each should show the other. Use only names from tool results, with the call ID
you took each one from. Never use a name from memory. You may call qloo_more up to {extra} times if the answers are
thin (for example a place kind such as bar, restaurant or cafe in {city}). Then call finish. Call the two people
by A_name and B_name in your text, never "A" or "B". Plain words, no hype."""

TOOLS = [
    {"name": "qloo_more", "description": "One more Qloo insights call. Returns ranked entities with call ID.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["type", "seeds"], "properties": {
         "type": {"type": "string", "enum": list(OUT_TYPES)},
         "seeds": {"type": "array", "items": {"type": "string"}, "description": "entity ids from the loves or from results"},
         "place_kind": {"type": "string", "description": "optional Qloo place genre, e.g. bar, restaurant, cafe, wine_bar"}}}},
    {"name": "finish", "description": "The answer. Every name must come from the call it cites.", "strict": True,
     "input_schema": {"type": "object", "additionalProperties": False,
                      "required": ["headline", "meet", "a_shows_b", "b_shows_a", "difference", "ask_each_other"], "properties": {
         "headline": {"type": "string", "description": "Where these two tastes meet, max 12 words"},
         "meet": {"type": "array", "description": "3 to 4 meeting points: one to listen to, one to watch, one place in the city if any",
                  "items": {"type": "object", "additionalProperties": False, "required": ["what", "name", "call", "why"], "properties": {
                      "what": {"type": "string", "enum": ["listen", "watch", "go"]}, "name": {"type": "string"},
                      "call": {"type": "string"}, "why": {"type": "string", "description": "max 16 words"}}}},
         "a_shows_b": {"type": "object", "additionalProperties": False, "required": ["name", "call", "why"], "properties": {
             "name": {"type": "string"}, "call": {"type": "string"}, "why": {"type": "string"}}},
         "b_shows_a": {"type": "object", "additionalProperties": False, "required": ["name", "call", "why"], "properties": {
             "name": {"type": "string"}, "call": {"type": "string"}, "why": {"type": "string"}}},
         "difference": {"type": "string", "description": "One sentence: where the two tastes pull apart"},
         "ask_each_other": {"type": "string", "description": "One question these two should argue about tonight"}}}}]

def validate(ans, calls):
    by, bad = {c["id"]: {e.get("name") for e in entities(c)} for c in calls}, []
    picks = [(f"meet {i + 1}", m) for i, m in enumerate(ans.get("meet") or [])] + [("a_shows_b", ans.get("a_shows_b") or {}), ("b_shows_a", ans.get("b_shows_a") or {})]
    if not 2 <= len(ans.get("meet") or []) <= 4:
        bad.append("meet needs 2 to 4 rows")
    for label, p in picks:
        if p.get("call") not in by:
            bad.append(f"{label}: call {p.get('call')} was not made")
        elif p.get("name") not in by[p["call"]]:
            bad.append(f"{label}: {p.get('name')} is not in call {p['call']}")
    return bad

def agent(run, A, B, briefs, client, names=("A", "B")):
    who = lambda xs: [{k: x.get(k) for k in ("asked", "name", "type", "id")} for x in xs]
    msgs = [{"role": "user", "content": json.dumps({"city": run.city, "A_name": names[0], "B_name": names[1], "A_loves": who(A), "B_loves": who(B), "qloo": briefs}, ensure_ascii=False)}]
    system = SYSTEM.format(extra=EXTRA, city=run.city)
    extra, usage = 0, {"input": 0, "output": 0}
    for turn in range(TURNS):
        r = client.messages.create(model=MODEL, max_tokens=4000, system=system, tools=TOOLS, messages=msgs,
                                   output_config={"effort": "low"})
        usage["input"] += r.usage.input_tokens; usage["output"] += r.usage.output_tokens
        msgs.append({"role": "assistant", "content": r.content})
        uses = [b for b in r.content if b.type == "tool_use"]
        if not uses:
            msgs.append({"role": "user", "content": "Call finish now."}); continue
        results, done = [], None
        for u in uses:
            if u.name == "finish":
                bad = validate(u.input, run.calls)
                if not bad or turn == TURNS - 1:
                    done = (u.input, bad)
                    break
                results.append({"type": "tool_result", "tool_use_id": u.id, "is_error": True, "content": f"Rejected, fix and finish again: {bad}"})
            elif extra >= EXTRA:
                results.append({"type": "tool_result", "tool_use_id": u.id, "is_error": True, "content": "No more Qloo calls. Call finish."})
            else:
                extra += 1
                a = u.input
                t = a.get("type") if a.get("type") in OUT_TYPES else "artist"
                kind = str(a.get("place_kind") or "")
                kind = kind if t == "place" and kind.replace("_", "").isalpha() else ""
                c = run.insights(f"agent {t} {kind}".strip(), t, a.get("seeds") or [], tag=kind and f"urn:tag:genre:place:{kind}")
                results.append({"type": "tool_result", "tool_use_id": u.id, "content": json.dumps(brief(c), ensure_ascii=False)})
        if done:
            return done[0], done[1], usage, turn + 1
        msgs.append({"role": "user", "content": results})
    return None, ["agent never finished"], usage, TURNS

def match(a_loves, b_loves, city="London", qloo_key=None, anthropic_key=None, names=("A", "B")):
    t0 = time.time()
    a_loves = [x.strip()[:80] for x in a_loves if x.strip()][:3]
    b_loves = [x.strip()[:80] for x in b_loves if x.strip()][:3]
    city = (city or "London").strip()[:40]
    run = Run(Live(qloo_key or secret("QLOO_API_KEY", "QLOO_API_KEY", "qloo-hackathon"), max_calls=QLOO_CAP, pause=0), city)
    A, B, briefs, _ = fan_out(run, a_loves, b_loves)
    out = {"city": city, "A": A, "B": B, "model": MODEL}
    if not briefs:
        return out | {"error": "Qloo found none of one person's loves. Try other names.", "calls": receipts(run)}
    client = anthropic.Anthropic(api_key=anthropic_key or secret("ANTHROPIC_API_KEY", "anthropic-api-key-20261014"))
    ans, problems, usage, turns = agent(run, A, B, briefs, client, tuple((n or d).strip()[:30] for n, d in zip(names, ("A", "B"))))
    usd = usage["input"] * 2 / 1e6 + usage["output"] * 10 / 1e6
    return out | {"answer": ans, "problems": problems, "calls": receipts(run),
                  "cost": {"qloo_calls": len(run.calls), "turns": turns, "usd": round(usd, 4), "seconds": round(time.time() - t0, 1)}}

def receipts(run):
    return [{"id": c["id"], "purpose": c["purpose"], "status": c["status"], "url": c["url"], "names": [e.get("name") for e in entities(c)][:8]} for c in run.calls]

if __name__ == "__main__":
    a, b = sys.argv[1].split(","), sys.argv[2].split(",")
    r = match(a, b, sys.argv[3] if len(sys.argv) > 3 else "London")
    print(json.dumps({k: r.get(k) for k in ("answer", "problems", "cost", "error")}, indent=1, ensure_ascii=False))
