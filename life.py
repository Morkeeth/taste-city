"""How each archetype lives, derived from cache/life.json (live_life.py). Code-owned rules, no model:
a place joins the day only if its Qloo tags name a kind of place you would go to, and each slot takes
the highest-affinity place of its kind. Every line keeps the Qloo call ID it came from."""
import json, pathlib

HERE = pathlib.Path(__file__).resolve().parent
LIFE = HERE / "cache" / "life.json"

# Invented first names. The archetype is Qloo's; the person is ours, and the page says so.
NAMES = {"digger": "Inês", "monk": "Kai", "poet": "Ruth", "romantic": "Juno", "sneaker": "Dre", "wine": "Ola"}

# Slot -> words that must appear in a place's Qloo tags, genre or name. First match wins, in this order.
SLOTS = [("late", "23:00", ("night club", "nightclub", "live music", "event venue", "concert", "music venue", "dance", "disco")),
         ("evening", "19:00", ("restaurant", "bar", "pub", "wine", "lounge", "bistro", "brasserie")),
         ("day", "11:00", ("record", "music store", "museum", "gallery", "park", "garden", "book", "cafe", "coffee", "florist", "market", "recording studio"))]

def ents(call):
    r = call["body"].get("results", {})
    return r.get("entities", []) if isinstance(r, dict) else r

def kinds(e):
    """The place kind only: first the primary genre, then the category and genre tag names. Never ambience tags or translations."""
    g = e.get("properties", {}).get("primary_genre") or {}
    first = (g.get("id") or "").rsplit(":", 1)[-1].replace("_", " ") if isinstance(g, dict) else ""
    rest = [t.get("name", "") for t in (e.get("tags") or [])
            if (t.get("type", "").endswith(":category") or ":genre:place" in t.get("id", "")) and t.get("name") not in ("Place", "Tourist attraction")]
    return first.lower(), " | ".join(rest).lower()

def slot_of(e):
    for w in kinds(e):
        for name, _, keys in SLOTS:
            if w and any(k in w for k in keys):
                return name
    return None

def aff(e):
    return round(e.get("query", {}).get("affinity", 0), 3)

def top(call, n):
    seen, out = set(), []
    for e in ents(call):
        if e["name"] in seen:
            continue
        seen.add(e["name"]); out.append({"name": e["name"], "affinity": aff(e), "call": call["id"]})
    return out[:n]

def crowd(call):
    """Mean of the anchors' relative age and gender indices. An index above 0 leans in; it is not a share."""
    rows = [d["query"] for d in call["body"].get("results", {}).get("demographics", [])]
    if not rows:
        return None
    ages = {k: sum(r["age"][k] for r in rows) / len(rows) for k in rows[0]["age"]}
    male = sum(r["gender"]["male"] for r in rows) / len(rows)
    band = max(ages, key=ages.get)
    return {"age": band.replace("_", " "), "age_index": round(ages[band], 2), "lean": "male" if male > 0 else "female",
            "lean_index": round(abs(male), 2), "call": call["id"]}

def profile(d, aid):
    a = d["archetypes"][aid]
    C = {c["id"]: c for c in d["calls"]}
    places, dropped = [], []
    for key, cid in a["calls"].items():
        if not key.startswith("place"):
            continue
        for e in ents(C[cid]):
            s = slot_of(e)
            p = {"name": e["name"], "affinity": aff(e), "call": cid, "slot": s,
                 "area": (e.get("properties", {}).get("neighborhood") or "").strip() or None}
            (places if s else dropped).append(p)
    day, used = [], set()
    for name, clock, _ in reversed(SLOTS):
        cands = sorted((p for p in places if p["slot"] == name and p["name"] not in used), key=lambda p: (-p["affinity"], p["name"]))
        if cands:
            used.add(cands[0]["name"]); day.append({**cands[0], "time": clock})
    shows, films, brands = top(C[a["calls"]["tv_show"]], 3), top(C[a["calls"]["movie"]], 3), top(C[a["calls"]["brand"]], 3)
    return {"id": aid, "person": NAMES[aid], "city": d["city"], "fetched": d["fetched"],
            "listens": [x["name"] for x in a["anchors"]],
            "watches": {"show": shows[0] if shows else None, "film": films[0] if films else None, "more": [x["name"] for x in shows[1:] + films[1:]]},
            "wears": brands,
            "day": day, "home_show": shows[0] if shows else None,
            "dropped": [p["name"] for p in dropped], "considered": len(places) + len(dropped),
            "crowd": crowd(C[a["calls"]["demographics"]])}

def load():
    if not LIFE.exists():
        return None
    d = json.loads(LIFE.read_text())
    return {aid: profile(d, aid) for aid in d["archetypes"]}

if __name__ == "__main__":
    for aid, p in (load() or {}).items():
        print(aid, p["person"], "| day:", [(s["time"], s["name"]) for s in p["day"]], "| wears:", [b["name"] for b in p["wears"]],
              "| show:", p["home_show"]["name"], "| crowd:", p["crowd"], "| dropped:", p["dropped"])
