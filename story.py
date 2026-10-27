"""Each archetype as a person: a week in London, one tension, one checkable call for next week.
Built from cache/life.json (live_life.py, live_week.py) and the cached Wikipedia series. Code-owned rules, no model.
Run: python3 story.py  (prints the stories; --freeze writes the predictions file with its sha256)."""
import hashlib, json, pathlib, statistics, sys
import backtest, life, radar

HERE = pathlib.Path(__file__).resolve().parent
CHECK_WEEK = "2026-10-25"   # next week, seen from 19 Oct 2026; the series ends at the week to 2026-10-11
RISE = 1.5                  # a hit: views in CHECK_WEEK >= 1.5 x the median of the 8 weeks to the cutoff
GAP = 2                     # weeks from the cutoff to the checked week (11 Oct -> 25 Oct)

FOOD = ("restaurant", "cafe", "coffee", "bakery", "food market", "japanese", "italian", "asian", "mediterranean", "british",
        "latin american", "pizza", "sushi", "steak", "turkish", "grill", "bistro", "brasserie")
EVENING = ("pub", "bar", "wine", "lounge")
LATE = ("night club", "live music", "event venue", "concert", "music venue", "disco", "karaoke")
DAY = ("record", "music store", "museum", "gallery", "park", "garden", "book", "market", "clothing", "florist", "tattoo", "recording studio")

# Want (a taste word Qloo puts on the tribe's artists) against Do (an ambience word Qloo puts on their places).
TENSIONS = [(("introspective", "thoughtful"), ("Lively", "Social", "Large group", "Bustling")),
            (("underground", "cult", "experimental"), ("Historic", "Classic", "Elegant", "Touristic")),
            (("youthful", "young"), ("Historic", "Classic", "Elegant")),
            (("nostalgic",), ("Modern",)),
            (("dance-loving", "energetic"), ("Quiet", "Comfortable"))]

def kind_in(e, keys):
    first, rest = life.kinds(e)
    return any(k in first for k in keys) or (not first and any(k in rest for k in keys))

def ambience(e):
    return {t["name"] for t in (e.get("tags") or []) if ":ambience:" in t.get("id", "")}

def pick(places, keys, used):
    for e, cid in sorted(places, key=lambda p: -life.aff(p[0])):
        if e["name"] not in used and kind_in(e, keys):
            used.add(e["name"]); return e, cid
    return None, None

def line(day, clock, what, e=None, cid=None, name=None):
    return {"day": day, "clock": clock, "what": what, "name": name or (e["name"] if e else None), "call": cid,
            "affinity": life.aff(e) if e else None, "at": "place" if e is not None and what in ("eat", "out", "late", "day") else "home"}

def one_week_rule(series, members, t):
    """Top momentum pick at week t and whether it held: views at t+GAP >= RISE x median(t-7..t)."""
    w = None
    for m, i in sorted(((backtest.momentum(series[i], t), i) for i in members
                        if t + GAP < len(series[i]) and None not in series[i][t - 7:t + GAP + 1]
                        and statistics.median(series[i][t - 7:t + 1]) >= backtest.FLOOR), key=lambda x: (-x[0], x[1])):
        w = i; break
    if w is None:
        return None
    s = series[w]
    return s[t + GAP] >= RISE * statistics.median(s[t - 7:t + 1])

def base(series, members, t):
    """Share of eligible tribe artists for whom the one-week rule held at week t: what a random pick gets."""
    ok = [series[i][t + GAP] >= RISE * statistics.median(series[i][t - 7:t + 1]) for i in members
          if t + GAP < len(series[i]) and None not in series[i][t - 7:t + GAP + 1] and statistics.median(series[i][t - 7:t + 1]) >= backtest.FLOOR]
    return sum(ok) / len(ok) if ok else None

def odds(series, members):
    """How often the one-week rule held for this tribe's top pick in the held-out weeks (backtest.TEST), and for a random pick."""
    t0, t1 = backtest.week_index(backtest.TEST[0]), backtest.week_index(backtest.TEST[1])
    res = [r for r in (one_week_rule(series, members, t) for t in range(t0, t1 + 1)) if r is not None]
    rnd = [b for b in (base(series, members, t) for t in range(t0, t1 + 1)) if b is not None]
    return {"weeks": len(res), "held": sum(res), "rate": round(sum(res) / len(res), 3) if res else None,
            "random": round(sum(rnd) / len(rnd), 3) if rnd else None}

def story(d, aid, u, series):
    a, C, A = d["archetypes"][aid], {c["id"]: c for c in d["calls"]}, radar.BY_ID[aid]
    p = life.profile(d, aid)
    places = [(e, cid) for key, cid in a["calls"].items() if key.startswith("place") for e in life.ents(C[cid])]
    used = set()
    anchors = {x["name"] for x in a["anchors"]}
    new_art = [e for e in life.ents(C[a["calls"]["artists"]]) if e["name"] not in anchors]
    film = life.ents(C[a["calls"]["movie"]])[:1]
    show = life.ents(C[a["calls"]["tv_show"]])[:1]
    week = [line("Mon", "08:00", "listen", new_art[0] if new_art else None, a["calls"]["artists"])]
    week[0]["at"] = "home"
    e, cid = pick(places, FOOD, used); week.append(line("Tue", "19:00", "eat", e, cid))
    week.append(line("Wed", "21:00", "film", film[0] if film else None, a["calls"]["movie"])); week[-1]["at"] = "home"
    e, cid = pick(places, EVENING, used); week.append(line("Thu", "19:00", "out", e, cid))
    e, cid = pick(places, LATE, used); week.append(line("Fri", "23:00", "late", e, cid))
    e, cid = pick(places, DAY, used); week.append(line("Sat", "11:00", "day", e, cid))
    week.append(line("Sun", "21:00", "show", show[0] if show else None, a["calls"]["tv_show"])); week[-1]["at"] = "home"
    # tension: the strongest want/do pair, by share of tribe artists times share of the week's places
    mem = radar.members(u, A, series)
    wk_places = list({e["name"]: e for e, _ in places if e["name"] in used}.values())
    best = None
    for want, do in TENSIONS:
        ws = sum(1 for i in mem if set(want) & set(u[i]["tags"])) / max(1, len(mem))
        hits = [e["name"] for e in wk_places if ambience(e) & set(do)]
        ds = len(hits) / max(1, len(wk_places))
        if ws > 0 and hits and (best is None or ws * ds > best["score"]):
            best = {"score": round(ws * ds, 3), "want": want[0], "want_share": round(ws, 2), "tribe": len(mem),
                    "do": [w for w in do if any(w in ambience(e) for e in wk_places)], "do_places": hits, "week_places": len(wk_places),
                    "calls": sorted({cid for e, cid in places if e["name"] in hits})}
    # the call for next week
    last = max(len(w) for w in series.values()) - 1
    r = radar.calls(u, series, A, last)
    top = r["picks"][0] if r["picks"] else None
    pred = None
    if top:
        med = statistics.median(series[top["id"]][last - 7:last + 1])
        titles = json.loads((HERE / "cache" / "titles.json").read_text())
        pred = {"artist": top["name"], "wikipedia": titles.get(u[top["id"]]["wikidata"]) or titles.get(u[top["id"]]["wikidata"].upper()), "rose": round(2.718281828 ** top["momentum"], 2), "cutoff": str(backtest.week_end(last)),
                "check_week": CHECK_WEEK, "needs_views": int(RISE * med + 0.999), "median_8w": int(med),
                "qloo": [s["anchor"] for s in top["qloo"]], "odds": odds(series, mem)}
    return {"id": aid, "person": p["person"], "archetype": A["name"], "city": d["city"], "age": p["crowd"]["age"] if p["crowd"] else None,
            "lean": p["crowd"], "brands": p["wears"][:2], "week": week, "tension": best, "prediction": pred}

def load():
    if not life.LIFE.exists():
        return None
    d = json.loads(life.LIFE.read_text())
    if not all("places25" in a["calls"] for a in d["archetypes"].values()):
        return None
    u, series, _ = backtest.load_series()
    return {aid: story(d, aid, u, series) for aid in d["archetypes"]}

def rival(S, aid):
    """The default partner for the side-by-side: the most different week, then one with a tension, then another age band."""
    a = S[aid]
    others = [k for k in S if k != aid]
    return max(others, key=lambda k: (distance(a, S[k]), S[k]["tension"] is not None, S[k]["age"] != a["age"], -others.index(k)))

def distance(a, b):
    """How different two weeks are: share of place, film, show and artist names they do not share."""
    na = {x["name"] for x in a["week"] if x["name"]}; nb = {x["name"] for x in b["week"] if x["name"]}
    return round(1 - len(na & nb) / max(1, len(na | nb)), 2)

if __name__ == "__main__":
    S = load()
    if "--freeze" in sys.argv:
        out = pathlib.Path(sys.argv[sys.argv.index("--freeze") + 1])
        body = json.dumps({"frozen": "2026-10-19", "rule": f"hit if English Wikipedia views in the week to {CHECK_WEEK} >= {RISE} x the median of the 8 weeks to the cutoff",
                           "predictions": {k: v["prediction"] for k, v in S.items()}}, indent=1, ensure_ascii=False)
        out.write_text(body); print(out, hashlib.sha256(body.encode()).hexdigest())
    else:
        for k, v in S.items():
            print(json.dumps(v, ensure_ascii=False)[:1400], "\n")
