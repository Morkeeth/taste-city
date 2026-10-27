"""Taste City, the game. Five villagers each love one thing. Qloo says what people with that love also love,
across films, TV, books, music and brands, and who those people are (age, gender). Each round a gift arrives:
something only one villager's Qloo list returned. The player hands it to the villager they think will love it.
Live Qloo calls only, nothing recorded, no model. Run: python3 village.py "Radiohead,Dolly Parton" """
import random, sys, urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from qloo_client import Live
from taste_match import secret, entities, short, MissingKey
import wiki

SEEDS = ["Radiohead", "Taylor Swift", "Kendrick Lamar", "Dolly Parton", "Daft Punk", "Billie Eilish", "Metallica", "BTS",
         "Fleabag", "The Sopranos", "Succession", "The Great British Bake Off", "Spirited Away", "Mad Max: Fury Road",
         "Pride and Prejudice", "Harry Potter", "Dune", "The Lord of the Rings", "Bad Bunny", "Studio Ghibli"]
NAMES = ["Mabel", "Otis", "Juno", "Felix", "Rosa", "Arlo", "Iris", "Theo"]
GIFT_TYPES = ("movie", "tv_show", "book", "artist", "brand")
FIND_TYPES = ("artist", "movie", "tv_show", "brand")   # a book alone as seed gets HTTP 400 on cross-domain insights
SKIP_TAGS = {"Mature", "Intense", "Drama", "Comedy", "Fiction", "Pop", "Rock", "Entertainment", "Nonfiction", "Biography",
             "Literature", "Novels", "School", "Autobiography", "Audiobook", "Memoir", "Novel", "Adult", "Fiction & Literature"}
ROUNDS, CAP = 10, 48
LABEL = {"movie": "film", "tv_show": "TV show", "book": "book", "artist": "music", "brand": "brand",
         "place": "place", "podcast": "podcast", "videogame": "game"}
CITY = "London"   # place insights are asked for this city

class Calls:
    def __init__(self, key, prefix="", cap=CAP):
        self.q, self.log, self.prefix = Live(key, max_calls=cap, pause=0), [], prefix

    def get(self, purpose, path, params):
        c = self.q.get(purpose, path, params)
        c["id"] = self.prefix + c["id"]   # streets of the city number their calls S1.L01, so ids stay unique city-wide
        c["url"] = path + "?" + urllib.parse.urlencode(params, safe=":,")
        self.log.append(c)
        return c

def age_band(demo):
    """Qloo demographics give skews per age band. The villager's look follows the strongest positive band."""
    q = ((demo.get("response") or {}).get("results", {}).get("demographics") or [{}])[0].get("query") or {}
    age, gender = q.get("age") or {}, q.get("gender") or {}
    band = max(age, key=age.get) if age else None
    lean = None
    if gender:
        g = max(gender, key=gender.get)
        lean = g if gender[g] >= 0.08 else "even"
    return {"age": band, "age_skew": age, "gender_lean": lean, "call": demo["id"]}

def insight(t, seed_id):
    p = {"filter.type": f"urn:entity:{t}", "signal.interests.entities": seed_id, "take": 10}
    if t == "place":
        p["filter.location.query"] = CITY
    return (t, "/v2/insights", p)

def pool_rows(t, c):
    return [{"id": e.get("entity_id"), "name": e.get("name"), "type": t, "call": c["id"]} for e in entities(c) if e.get("name")]

def build_villager(calls, love, name, types=GIFT_TYPES):
    found = calls.get(f"find {love}", "/search", {"query": love[:80], "types": ",".join(f"urn:entity:{t}" for t in FIND_TYPES), "take": 1})
    hits = entities(found)
    if not hits:
        return {"name": name, "love": love, "found": None}
    seed = short(hits[0]) | {"call": found["id"], "wikidata": wiki.qid(hits[0])}
    img = ((hits[0].get("properties") or {}).get("image") or {}).get("url")
    jobs = [("demo", "/v2/insights", {"filter.type": "urn:demographics", "signal.interests.entities": seed["id"]})] + [
        insight(t, seed["id"]) for t in types]
    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(lambda j: calls.get(f"{name}: {j[0]} for {seed['name']}", j[1], j[2]), jobs))
    tags, pool = Counter(), []
    for (t, _, _), c in zip(jobs[1:], res[1:]):
        for rank, e in enumerate(entities(c)):
            raw = sorted(e.get("tags") or [], key=lambda x: ":genre:" not in (x.get("id") or "") + (x.get("type") or ""))   # genres first, odd keywords last
            names = list(dict.fromkeys(x.get("name") for x in raw if x.get("name") and x.get("name") not in SKIP_TAGS))
            if t in ("movie", "tv_show", "artist"):   # book and brand tags are shelf labels (Nonfiction, Car & SUV), not taste
                tags.update(names[:8])
            p = e.get("properties") or {}
            pool.append({"id": e.get("entity_id"), "name": e.get("name"), "type": t, "label": LABEL[t], "rank": rank + 1,
                         "affinity": round(float((e.get("query") or {}).get("affinity") or 0), 2),
                         "popularity": round(float(e.get("popularity") or 0), 2),
                         "image": (p.get("image") or {}).get("url"), "year": p.get("release_year"),
                         "tags": names[:4], "call": c["id"]})
    return {"name": name, "love": love, "found": seed, "image": img, "who": age_band(res[0]),
            "traits": [t for t, _ in tags.most_common(5)], "pool": pool}

def rounds(villagers, rng):
    """Gifts only one villager's lists returned, so every gift has one right answer by Qloo's own data.
    Even spread over villagers, mid-list picks first (rank 2 to 7), never the villager's own love."""
    owners = Counter(g["id"] for v in villagers for g in {x["id"]: x for x in v["pool"]}.values())
    per = {}
    for i, v in enumerate(villagers):
        own = [g for g in v["pool"] if owners[g["id"]] == 1 and g["id"] != v["found"]["id"] and g["name"]]
        rng.shuffle(own)
        own.sort(key=lambda g: (not 2 <= g["rank"] <= 7, g["image"] is None))
        seen_types, picked = set(), []
        for g in own:   # one of each type first, so a villager's gifts vary
            if g["type"] not in seen_types:
                picked.append(g); seen_types.add(g["type"])
        per[i] = picked + [g for g in own if g not in picked]
    out, i = [], 0
    while len(out) < ROUNDS and any(per.values()):
        if per[i % len(villagers)]:
            out.append(per[i % len(villagers)].pop(0) | {"owner": i % len(villagers)})
        i += 1
    rng.shuffle(out)
    return out

def village(loves=None, me=None, key=None, seed=None):
    rng = random.Random(seed)
    loves = [x.strip()[:80] for x in (loves or []) if x.strip()][:5]
    taken = {x.lower() for x in loves + [me or ""]}
    loves += [s for s in rng.sample(SEEDS, len(SEEDS)) if s.lower() not in taken][:5 - len(loves)]
    names = rng.sample(NAMES, 5)
    if me and me.strip():   # the player moves in as the sixth villager
        loves.append(me.strip()[:80]); names.append("You")
    calls = Calls(key or secret("QLOO_API_KEY", "QLOO_API_KEY", "qloo-hackathon"))
    with ThreadPoolExecutor(3) as ex:
        vs = list(ex.map(lambda p: build_villager(calls, *p), zip(loves, names)))
    vs = [v for v in vs if v.get("found") and v.get("pool")]
    if len(vs) < 3:
        return {"error": "Qloo did not answer for enough of these loves. Try again or try other names."}
    gifts = rounds(vs, rng)
    pools = [[{k: g[k] for k in ("id", "name", "type", "call")} for g in v.pop("pool")] for v in vs]   # for the city's questions
    return {"villagers": vs, "gifts": gifts, "pools": pools,
            "calls": [{"id": c["id"], "purpose": c["purpose"], "status": c["status"], "url": c["url"]} for c in calls.log]}

if __name__ == "__main__":
    import json, time
    t0 = time.time()
    r = village(sys.argv[1].split(",") if len(sys.argv) > 1 else None, seed=1)
    for v in r.get("villagers", []):
        print(v["name"], "|", v["love"], "->", v["found"]["name"], v["found"]["type"], "|", v["who"]["age"], v["who"]["gender_lean"], "|", v["traits"])
    for g in r.get("gifts", []):
        print(" gift", g["label"], g["name"], "->", r["villagers"][g["owner"]]["name"], g["call"], "img" if g["image"] else "-")
    print(len(r.get("calls", [])), "calls", round(time.time() - t0, 1), "s", r.get("error"))
