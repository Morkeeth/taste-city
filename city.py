"""Taste City: the village grows into a city while you play. The plaza is the village (five villagers, the gift game).
Then four streets move in, one request each, five villagers a street: 20 more people, 25 in all. A street villager is
found in Qloo and asked about eight things: who their fans are, and what those fans love in music, film, TV, places
in London, podcasts and games. The plaza villagers get places, podcasts and games too. Every villager also carries one
public row: Wikipedia pageviews for their love, joined through the Wikidata id Qloo returns (CC0).
Live Qloo calls only, nothing recorded, no model. Run: python3 city.py 1"""
import sys
from concurrent.futures import ThreadPoolExecutor
import village, wiki
from taste_match import secret

CITY_TYPES = ("artist", "movie", "tv_show", "place", "podcast", "videogame")
EXTRA_TYPES = ("place", "podcast", "videogame")
STREET_CAP = 40   # 5 villagers x 8 calls (search, demographics, six insights)
STREETS = [
    ("Mill Lane", ["Mitski", "Arctic Monkeys", "Beyoncé", "Fred again..", "Adele"], ["Ada", "Bram", "Cleo", "Dev", "Edie"]),
    ("Station Road", ["Ted Lasso", "The Bear", "Stranger Things", "Severance", "Peaky Blinders"], ["Finn", "Gus", "Hana", "Ines", "Jude"]),
    ("Orchard Row", ["Paddington 2", "Oppenheimer", "Amélie", "Barbie", "Everything Everywhere All at Once"], ["Kit", "Lior", "Maya", "Nell", "Omar"]),
    ("Harbour Street", ["Lana Del Rey", "The Office", "Coldplay", "Gilmore Girls", "Stormzy"], ["Pia", "Quinn", "Ravi", "Suki", "Tove"]),
]
SPARES = ["Frank Ocean", "Phoebe Bridgers", "Ratatouille", "Normal People", "Bluey", "Massive Attack"]

def street(n, taken=(), key=None):
    """Street n (1 to 4): five new villagers, 40 Qloo calls, plus their Wikipedia rows."""
    if not 1 <= n <= len(STREETS):
        return {"error": f"There are {len(STREETS)} streets."}
    name, loves, names = STREETS[n - 1]
    taken = {t.lower() for t in taken}
    spares = [s for s in SPARES if s.lower() not in taken]
    loves = [l if l.lower() not in taken else spares.pop(0) for l in loves]
    calls = village.Calls(key or secret("QLOO_API_KEY", "QLOO_API_KEY", "qloo-hackathon"), prefix=f"S{n}.", cap=STREET_CAP)
    with ThreadPoolExecutor(3) as ex:
        vs = list(ex.map(lambda p: village.build_villager(calls, *p, types=CITY_TYPES), zip(loves, names)))
    vs = [v for v in vs if v.get("found") and v.get("pool")]
    rows = wiki.rows([v["found"].get("wikidata") for v in vs])
    for v in vs:
        v["street"] = name
        v["pool"] = [{k: g[k] for k in ("id", "name", "type", "call")} for g in v["pool"]]
        v["wiki"] = rows.get(v["found"].get("wikidata"))
    return {"street": n, "name": name, "villagers": vs, "calls": calls_out(calls)}

def plaza(people, key=None):
    """The plaza's villagers ({name, id, wikidata} each, at most 6): places, podcasts and games, 3 Qloo calls each."""
    people = [p for p in people if p.get("id")][:6]
    calls = village.Calls(key or secret("QLOO_API_KEY", "QLOO_API_KEY", "qloo-hackathon"), prefix="P.", cap=3 * len(people) or 1)
    jobs = [(p, village.insight(t, p["id"])) for p in people for t in EXTRA_TYPES]
    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(lambda j: calls.get(f"{j[0]['name']}: {j[1][0]} for {j[0].get('love') or j[0]['name']}", j[1][1], j[1][2]), jobs))
    rows = wiki.rows([p.get("wikidata") for p in people])
    out = {p["name"]: {"name": p["name"], "pool": [], "wiki": rows.get(p.get("wikidata"))} for p in people}
    for (p, (t, _, _)), c in zip(jobs, res):
        out[p["name"]]["pool"] += village.pool_rows(t, c)
    return {"extras": list(out.values()), "calls": calls_out(calls)}

def calls_out(calls):
    return [{"id": c["id"], "purpose": c["purpose"], "status": c["status"], "url": c["url"]} for c in calls.log]

if __name__ == "__main__":
    import time
    t0 = time.time()
    r = street(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
    for v in r.get("villagers", []):
        w = v.get("wiki") or {}
        print(v["name"], "|", v["love"], "->", v["found"]["name"], "|", v["who"]["age"], "|", len(v["pool"]), "rows |", w.get("title"), w.get("views_30d"))
    print(len(r.get("calls", [])), "calls", round(time.time() - t0, 1), "s", r.get("error"))
