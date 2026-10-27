"""Ask the city. Eight questions about the 25 villagers, each answered from the Qloo calls that built the city and the
Wikipedia rows paired with it. Seven make no new call; "who would love X" makes three. Every answer lists what it
stands on (villager, Qloo call, item, or public row) and check() rejects an answer that cites something the city
does not hold. No model: the answers are counts over Qloo's own lists, so they can be checked line by line."""
from collections import Counter
from itertools import combinations
import village
from taste_match import entities, secret

AGES = ["24_and_younger", "25_to_29", "30_to_34", "35_to_44", "45_to_54", "55_and_older"]
AGE_WORDS = {"24_and_younger": "under 25", "25_to_29": "25 to 29", "30_to_34": "30 to 34", "35_to_44": "35 to 44",
             "45_to_54": "45 to 54", "55_and_older": "55 and older"}
QUESTIONS = {
    "closest": "Which two neighbours are most alike?",
    "outlier": "Who is the odd one out?",
    "eat": "Where in London would the most villagers go?",
    "watch": "What could the whole city watch tonight?",
    "play": "Which podcast or game do most villagers share?",
    "crowd": "Whose fans are youngest, and whose are oldest?",
    "loudest": "Whose love is most looked up this month?",
    "who_loves": "Who in the city would love this?",
    "would_love": "Would this panel love it?",
    "turnout": "Which night suits this crowd?",
    "pair_with": "What should we pair it with?",
}
WHO_LOVES_TYPES = ("artist", "movie", "tv_show")
MIN_POOL = 5   # a villager whose Qloo lists came back near empty is left out of likeness questions, and the answer says so

def people(city):
    return [v for v in city.get("villagers", []) if v.get("name") and v.get("found")]

def ids(v, types=None):
    return {g["id"]: g for g in v.get("pool", []) if g.get("id") and (types is None or g.get("type") in types)}

def cite(v, g):
    return {"villager": v["name"], "call": g["call"], "item": g["name"], "type": g.get("type")}

def shared(city, types, what):
    """The item that appears in the most villagers' lists of these types."""
    vs = people(city)
    count, first = Counter(), {}
    for v in vs:
        for i, g in ids(v, types).items():
            count[i] += 1; first.setdefault(i, g)
    if not count:
        return {"answer": f"No villager has {what} in their Qloo lists yet. The streets may still be moving in.", "names": [], "cites": []}
    top, n = sorted(count.items(), key=lambda kv: (-kv[1], first[kv[0]]["name"]))[0]
    holders = [v for v in vs if top in ids(v, types)]
    g = first[top]
    names = [v["name"] for v in holders]
    if n < 2:
        return {"answer": f"Nothing in {what} appears in two villagers' lists; tastes here do not overlap on {what}. "
                          f"The top of {holders[0]['name']}'s list is {g['name']}.", "names": names, "cites": [cite(holders[0], g)]}
    listed = ", ".join(names[:6]) + (f" and {len(names) - 6} more" if len(names) > 6 else "")
    return {"answer": f"{g['name']}. It is in {n} of {len(vs)} villagers' Qloo lists: {listed}.", "names": names,
            "cites": [cite(v, ids(v, types)[top]) for v in holders]}

def overlap(a, b):
    sa, sb = ids(a), ids(b)
    return [i for i in sa if i in sb]

def closest(city):
    vs = [v for v in people(city) if len(ids(v)) >= MIN_POOL]
    if len(vs) < 2:
        return {"answer": "The city needs two villagers with full Qloo lists first.", "names": [], "cites": []}
    a, b = max(combinations(vs, 2), key=lambda p: (len(overlap(*p)), p[0]["name"] < p[1]["name"]))
    both = overlap(a, b)
    if not both:
        return {"answer": "No two villagers share a single item in their Qloo lists.", "names": [], "cites": []}
    items = [ids(a)[i]["name"] for i in both[:4]]
    where = lambda v: f"{v['street']}" if v.get("street") else "the plaza"
    return {"answer": f"{a['name']} ({a['found']['name']}, {where(a)}) and {b['name']} ({b['found']['name']}, {where(b)}): "
                      f"{len(both)} things in common in Qloo's lists, such as {', '.join(items)}.",
            "names": [a["name"], b["name"]],
            "cites": [c for i in both[:4] for c in (cite(a, ids(a)[i]), cite(b, ids(b)[i]))]}

def outlier(city):
    vs = [v for v in people(city) if len(ids(v)) >= MIN_POOL]
    if len(vs) < 3:
        return {"answer": "The city needs three villagers with full Qloo lists first.", "names": [], "cites": []}
    score = {v["name"]: sum(len(overlap(v, w)) for w in vs if w is not v) for v in vs}
    odd = min(vs, key=lambda v: (score[v["name"]], v["name"]))
    left = len(people(city)) - len(vs)
    kinds = lambda v: {g.get("type") for g in v.get("pool", [])}
    peers = set().union(*(kinds(v) for v in vs if v.get("street") == odd.get("street")))
    gone = sorted(peers - kinds(odd))   # a list Qloo did not return makes anyone look odd; say so
    return {"answer": f"{odd['name']}, who loves {odd['found']['name']}. Their Qloo lists share {score[odd['name']]} items "
                      f"with the other {len(vs) - 1} villagers combined." + (f" {left} villager(s) with near-empty lists were left out." if left else "")
                      + (f" Part of this is missing data: Qloo returned no {' or '.join(gone)} list for {odd['name']}." if gone else ""),
            "names": [odd["name"]], "cites": [{"villager": odd["name"], "call": odd["found"]["call"], "item": odd["found"]["name"], "type": "found"}]}

def few(names, k=4):
    return ", ".join(names[:k]) + (f" and {len(names) - k} more" if len(names) > k else "")

def crowd(city):
    vs = [v for v in people(city) if (v.get("who") or {}).get("age") in AGES]
    if not vs:
        return {"answer": "No villager has Qloo demographics yet.", "names": [], "cites": []}
    young = min(vs, key=lambda v: (AGES.index(v["who"]["age"]), v["name"]))
    old = max(vs, key=lambda v: (AGES.index(v["who"]["age"]), v["name"]))
    same = lambda band: [v["name"] for v in vs if v["who"]["age"] == band]
    y, o = same(young["who"]["age"]), same(old["who"]["age"])
    return {"answer": f"Youngest: fans of {young['found']['name']} ({young['name']}) skew {AGE_WORDS[young['who']['age']]}"
                      + (f", with {few([n for n in y if n != young['name']])}" if len(y) > 1 else "") + ". "
                      f"Oldest: fans of {old['found']['name']} ({old['name']}) skew {AGE_WORDS[old['who']['age']]}"
                      + (f", with {few([n for n in o if n != old['name']])}" if len(o) > 1 else "") + ".",
            "names": [young["name"], old["name"]],
            "cites": [{"villager": v["name"], "call": v["who"]["call"], "item": v["who"]["age"], "type": "demographics"} for v in (young, old)]}

def loudest(city):
    vs = [v for v in people(city) if isinstance((v.get("wiki") or {}).get("views_30d"), int)]
    if not vs:
        return {"answer": "No Wikipedia rows yet.", "names": [], "cites": [], "rows": []}
    vs.sort(key=lambda v: (-v["wiki"]["views_30d"], v["name"]))
    top, low = vs[0], vs[-1]
    w = lambda v: f"{v['wiki']['title']} ({v['wiki']['views_30d']:,} views in 30 days)"
    return {"answer": f"{top['name']}'s love, {w(top)}. The quietest is {low['name']}'s, {w(low)}. "
                      f"Attention is not taste: this counts English Wikipedia readers, not fans.",
            "names": [top["name"], low["name"]],
            "cites": [{"villager": v["name"], "call": v["found"]["call"], "item": v["found"]["name"], "type": "found"} for v in (top, low)],
            "rows": [v["wiki"] for v in (top, low)]}

def who_loves(city, thing, key=None):
    """Find the thing in Qloo, ask what its fans love in music, film and TV (2 calls), and count which villager's lists
    hold the most of it. 3 Qloo calls."""
    thing = (thing or "").strip()[:80]
    if not thing:
        return {"answer": "Name one thing to ask about.", "names": [], "cites": []}
    calls = village.Calls(key or secret("QLOO_API_KEY", "QLOO_API_KEY", "qloo-hackathon"), prefix="Q.", cap=3)
    found = calls.get(f"find {thing}", "/search", {"query": thing, "types": ",".join(f"urn:entity:{t}" for t in village.FIND_TYPES), "take": 1})
    hits = entities(found)
    new = lambda: [{"id": c["id"], "purpose": c["purpose"], "status": c["status"], "url": c["url"]} for c in calls.log]
    if not hits:
        return {"answer": f"Qloo did not find {thing}.", "names": [], "cites": [], "calls": new()}
    e = hits[0]
    fans = {}
    for t in ("artist", "movie"):
        c = calls.get(f"fans of {e.get('name')}: {t}", *village.insight(t, e["entity_id"])[1:])
        for g in village.pool_rows(t, c):
            fans[g["id"]] = g
    score = []
    for v in people(city):
        mine = ids(v)
        both = [i for i in fans if i in mine]
        direct = e["entity_id"] in mine
        score.append((direct, len(both), v, both))
    score.sort(key=lambda s: (not s[0], -s[1], s[2]["name"]))
    direct, n, v, both = score[0]
    if not direct and not n:
        return {"answer": f"Nobody in the city. People who love {e.get('name')} like none of the things in our villagers' lists.",
                "names": [], "cites": [], "calls": new()}
    lead = f"{v['name']}, who loves {v['found']['name']}." + (f" {e.get('name')} is already in their Qloo lists." if direct else "")
    runner = [s for s in score[1:3] if s[0] or s[1]]
    return {"answer": f"{lead} People who love {e.get('name')} also love {n} things in {v['name']}'s lists"
                      + (f", such as {', '.join(fans[i]['name'] for i in both[:3])}" if both else "") + "."
                      + (f" Next: {', '.join(s[2]['name'] + f' ({s[1]})' for s in runner)}." if runner else ""),
            "names": [v["name"]] + [s[2]["name"] for s in runner],
            "cites": [cite(v, ids(v)[i]) for i in both[:3]] + ([cite(v, ids(v)[e["entity_id"]])] if direct else []),
            "evidence": [{"call": fans[i]["call"], "item": fans[i]["name"]} for i in both[:3]],
            "calls": new()}

def would_love(city, thing, key=None):
    """Count panel members with a direct match or a Qloo-list overlap with the thing's fans."""
    thing = (thing or "").strip()[:80]
    if not thing:
        return {"answer": "Name an act, film or show to test.", "names": [], "cites": []}
    calls = village.Calls(key or secret("QLOO_API_KEY", "QLOO_API_KEY", "qloo-hackathon"), prefix="Q.", cap=3)
    found = calls.get(f"find {thing}", "/search", {"query": thing, "types": ",".join(f"urn:entity:{t}" for t in village.FIND_TYPES), "take": 1})
    hits = entities(found)
    new = lambda: [{"id": c["id"], "purpose": c["purpose"], "status": c["status"], "url": c["url"]} for c in calls.log]
    if not hits:
        return {"answer": f"Qloo did not find {thing}.", "names": [], "cites": [], "calls": new()}
    target = hits[0]
    fans = {}
    for t in ("artist", "movie"):
        call = calls.get(f"fans of {target.get('name')}: {t}", *village.insight(t, target["entity_id"])[1:])
        for item in village.pool_rows(t, call):
            fans[item["id"]] = item
    yes, cites, evidence = [], [], []
    for person in people(city):
        mine = ids(person)
        direct = target["entity_id"] if target["entity_id"] in mine else None
        shared_ids = [item_id for item_id in fans if item_id in mine]
        proof = direct or (shared_ids[0] if shared_ids else None)
        if proof:
            yes.append(person["name"])
            cites.append(cite(person, mine[proof]))
            if proof in fans:
                evidence.append({"call": fans[proof]["call"], "item": fans[proof]["name"]})
    total = len(people(city))
    names = few(yes, 6) if yes else "none"
    return {"answer": f"{len(yes)} of {total} panel members have a Qloo-list match with fans of {target.get('name')}: {names}.",
            "names": yes, "cites": cites, "evidence": evidence, "calls": new()}

def turnout(city):
    """Count every returned Qloo age skew, with one demographics cite per panel member."""
    vs = [v for v in people(city) if (v.get("who") or {}).get("age") in AGES]
    if not vs:
        return {"answer": "Qloo returned no audience age skews for this panel.", "names": [], "cites": []}
    counts = Counter(v["who"]["age"] for v in vs)
    ordered = sorted(counts.items(), key=lambda row: (-row[1], AGES.index(row[0])))
    summary = ", ".join(f"{AGE_WORDS[band]}: {n}" for band, n in ordered)
    top = ordered[0][0]
    names = [v["name"] for v in vs if v["who"]["age"] == top]
    return {"answer": f"Qloo age skews across {len(vs)} panel members: {summary}. The largest group is {AGE_WORDS[top]}.",
            "names": names,
            "cites": [{"villager": v["name"], "call": v["who"]["call"], "item": v["who"]["age"], "type": "demographics"} for v in vs]}

def ask(city, q, arg=None, key=None):
    if q not in QUESTIONS:
        return {"error": f"Ask one of: {', '.join(QUESTIONS)}."}
    if q == "who_loves":
        out = who_loves(city, arg, key)
    elif q == "would_love":
        out = would_love(city, arg, key)
    elif q == "turnout":
        out = turnout(city)
    elif q == "pair_with":
        out = shared(city, ("artist",), "artists")
    elif q == "eat":
        out = shared(city, ("place",), "places in London")
    elif q == "watch":
        out = shared(city, ("movie", "tv_show"), "films and shows")
    elif q == "play":
        out = shared(city, ("podcast", "videogame"), "podcasts and games")
    else:
        out = {"closest": closest, "outlier": outlier, "crowd": crowd, "loudest": loudest}[q](city)
    out = {"q": q, "question": QUESTIONS[q] if q != "who_loves" else f"Who in the city would love {arg}?", "rows": [], "calls": []} | out
    out["villagers"] = len(people(city))
    out["problems"] = check(out, city)
    return out

def check(ans, city):
    """Every cite must be something the city holds: a pool item under the call that returned it, a villager's search
    call, or their demographics call. Every named villager must live here. Every row must be that villager's row."""
    by = {v["name"]: v for v in people(city)}
    bad = []
    for n in ans.get("names", []):
        if n not in by:
            bad.append(f"{n} does not live in this city")
    for c in ans.get("cites", []):
        v = by.get(c.get("villager"))
        if not v:
            bad.append(f"cite names {c.get('villager')}, who does not live here"); continue
        if c.get("type") == "found":
            ok = v["found"].get("call") == c.get("call") and v["found"].get("name") == c.get("item")
        elif c.get("type") == "demographics":
            ok = (v.get("who") or {}).get("call") == c.get("call") and (v.get("who") or {}).get("age") == c.get("item")
        else:
            ok = any(g.get("call") == c.get("call") and g.get("name") == c.get("item") for g in v.get("pool", []))
        if not ok:
            bad.append(f"{c.get('call')} did not return {c.get('item')} for {v['name']}")
    rows = [(v.get("wiki") or {}).get("url") for v in by.values()]
    for r in ans.get("rows", []):
        if r.get("url") not in rows:
            bad.append(f"row {r.get('title')} is not a villager's row")
    return bad
