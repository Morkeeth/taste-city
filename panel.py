"""Build a 25-person Taste Panel from 3 to 10 things a real audience loves.

Every panel member is built by the same Qloo search, demographics and six
cross-domain insight calls used by Taste City. No model and no recorded data.
"""
from concurrent.futures import ThreadPoolExecutor

import city
import city_ask
import village
import wiki
from taste_match import secret


PANEL_NAMES = [
    "Alex", "Bea", "Cam", "Dani", "Eli", "Fran", "Gray", "Hana", "Ivo", "Jules",
    "Kai", "Lena", "Mika", "Noor", "Oli", "Priya", "Quinn", "Remy", "Sol", "Tala",
    "Uma", "Val", "Wren", "Xavi", "Yara",
]
PANEL_CAP = 25 * (2 + len(city.CITY_TYPES))
SEED_TYPES = {"artist", "movie", "tv_show"}


def regulars(text):
    """Clean line input without silently turning repeated lines into people."""
    rows, seen = [], set()
    for raw in str(text or "").splitlines():
        love = raw.strip()[:80]
        if love and love.casefold() not in seen:
            rows.append(love)
            seen.add(love.casefold())
    return rows


def _candidate_seeds(scouts, wanted):
    """Take related music, film and TV results round-robin across regulars."""
    queues = []
    used = {v["found"]["id"] for v in scouts}
    for v in scouts:
        own, local = [], set()
        for item in v.get("pool", []):
            if item.get("type") not in SEED_TYPES or not item.get("id") or not item.get("name"):
                continue
            if item["id"] in used or item["id"] in local:
                continue
            own.append((item["name"], v["love"]))
            local.add(item["id"])
        queues.append(own)
    out = []
    while len(out) < wanted and any(queues):
        for queue in queues:
            while queue and queue[0][0].casefold() in {name.casefold() for name, _ in out}:
                queue.pop(0)
            if queue and len(out) < wanted:
                out.append(queue.pop(0))
    return out


def build(text, key=None):
    loves = regulars(text)
    if not 3 <= len(loves) <= 10:
        raise ValueError("Add 3 to 10 distinct things your regulars love, one per line.")
    calls = village.Calls(key or secret("QLOO_API_KEY", "QLOO_API_KEY", "qloo-hackathon"), prefix="A.", cap=PANEL_CAP)
    with ThreadPoolExecutor(3) as ex:
        scouts = list(ex.map(lambda pair: village.build_villager(calls, *pair, types=city.CITY_TYPES), zip(loves, PANEL_NAMES)))
    scouts = [v for v in scouts if v.get("found") and v.get("pool")]
    if len(scouts) != len(loves):
        raise ValueError("Qloo could not build a person from every line. Try more specific films, shows, artists or brands.")
    seeds = _candidate_seeds(scouts, 25 - len(scouts))
    if len(seeds) < 25 - len(scouts):
        raise ValueError("Qloo did not return enough related tastes to build 25 people. Try a wider mix of loves.")
    jobs = [(love, PANEL_NAMES[len(scouts) + i], source) for i, (love, source) in enumerate(seeds)]
    with ThreadPoolExecutor(3) as ex:
        more = list(ex.map(lambda row: village.build_villager(calls, row[0], row[1], types=city.CITY_TYPES), jobs))
    for v, source in zip(more, [row[2] for row in jobs]):
        v["source"] = source
    for v in scouts:
        v["source"] = v["love"]
    people = [v for v in scouts + more if v.get("found") and v.get("pool")]
    if len(people) != 25:
        raise ValueError("Qloo could not complete all 25 panel members. Try again or replace one of the lines.")
    rows = wiki.rows([v["found"].get("wikidata") for v in people])
    for i, v in enumerate(people):
        v["street"] = f"Panel row {i // 5 + 1}"
        v["wiki"] = rows.get(v["found"].get("wikidata"))
    return {"regulars": loves, "villagers": people, "calls": city.calls_out(calls)}


TEMPLATES = {
    "book_act": "would_love",
    "which_night": "turnout",
    "pair_with": "pair_with",
}


def answer_template(panel_city, template, arg=None, key=None):
    """Answer the three decisions a small venue booker repeats each week."""
    if template not in TEMPLATES:
        raise ValueError(f"Unknown Taste Panel template: {template}")
    return city_ask.ask(panel_city, TEMPLATES[template], arg, key)
