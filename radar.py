"""Hipster radar: pick an archetype, get the artists it will love next, with the evidence.
Qloo decides who is in the archetype (tags on recorded calls). Wikipedia momentum makes the call, because the
pre-registered backtest (PREREG.txt) found momentum works and the Qloo neighbour term adds nothing."""
import statistics
import backtest

ARCHETYPES = [
    {"id": "digger", "name": "The Vinyl Digger", "blurb": "Owns three copies of the same Brazilian record. Different pressings.",
     "tags": {"jazz", "funk", "soul", "neo soul", "jazz fusion", "brazilian", "mpb", "samba", "afrobeat", "world music", "bossa nova"}},
    {"id": "monk", "name": "The Warehouse Monk", "blurb": "Last seen at 6am. Says the closing set was the real set.",
     "tags": {"techno", "house", "deep house", "minimal", "idm", "outsider house", "uk garage", "electronica", "ambient", "breakbeat"}},
    {"id": "poet", "name": "The Post-Punk Poet", "blurb": "Black coat in July. Liked the band before the second guitarist.",
     "tags": {"post punk", "post-punk", "post-punk revival", "punk", "art punk", "garage rock", "garage - rock", "gothic rock", "new wave", "punk rock"}},
    {"id": "romantic", "name": "The Bedroom Pop Romantic", "blurb": "Fairy lights, a cassette four-track, feelings at 2am.",
     "tags": {"indie pop", "dream pop", "synthpop", "electropop", "art pop", "lo - fi", "bedroom pop", "chillwave"}},
    {"id": "sneaker", "name": "The Sneakerhead", "blurb": "Knows the drop date. Knows the producer. Queues for both.",
     "tags": {"hip hop", "hip - hop", "rap", "grime", "uk drill", "drill", "trap"}},
    {"id": "wine", "name": "The Natural Wine Person", "blurb": "It is a little funky. That is the point.",
     "tags": {"folk", "singer-songwriter", "singer & songwriter", "singer songwriter", "folk rock", "indie folk", "chamber pop", "alternative r&b"}},
]
BY_ID = {a["id"]: a for a in ARCHETYPES}
PICKS = 5

def members(universe, archetype, series):
    return [i for i, e in universe.items() if i in series and archetype["tags"] & set(e["tags"])]

def anchors(universe, archetype, series, n=3):
    """The n tribe artists that carry the most archetype tags; ties go to the more popular. Seeds the life calls."""
    m = members(universe, archetype, series)
    return sorted(m, key=lambda i: (-len(archetype["tags"] & set(universe[i]["tags"])), -universe[i]["popularity"], i))[:n]

def calls(universe, series, archetype, t):
    """Top picks for one archetype at cutoff week t, plus each pick's evidence. Uses only weeks up to t."""
    out = []
    for i in members(universe, archetype, series):
        w = series[i]
        if t - 7 < 0 or t >= len(w) or None in w[t - 7:t + 1] or statistics.median(w[t - 7:t + 1]) < backtest.FLOOR:
            continue
        out.append((backtest.momentum(w, t), i))
    out.sort(key=lambda x: (-x[0], x[1]))
    picks = []
    for m, i in out[:PICKS]:
        e, w = universe[i], series[i]
        past = statistics.median(w[t - 7:t + 1])
        pick = {"id": i, "name": e["name"], "momentum": round(m, 3), "spark": w[max(0, t - 11):t + 1],
                "why_tags": sorted(archetype["tags"] & set(e["tags"])),
                "qloo": e["seen_in"][:3], "neighbours": len(e["neighbours"])}
        if t + 8 < len(w) and None not in w[t + 1:t + 9]:
            ratio = statistics.median(w[t + 1:t + 9]) / past
            pick["after"] = w[t + 1:t + 9]
            pick["ratio"] = round(ratio, 2)
            pick["called_it"] = ratio >= backtest.JUMP
        picks.append(pick)
    return {"eligible": len(out), "picks": picks}

def track_record(universe, series, archetype, start=backtest.TEST[0], end=backtest.TEST[1]):
    """Exploratory, not pre-registered: the archetype's own hit rate on the held-out weeks, top 5 per week."""
    made = hits = 0
    base = []
    mem = members(universe, archetype, series)
    for t in range(backtest.week_index(start), backtest.week_index(end) + 1):
        for p in calls(universe, series, archetype, t)["picks"]:
            if "called_it" in p:
                made += 1; hits += p["called_it"]
        elig = [series[i] for i in mem if t - 7 >= 0 and t + 8 < len(series[i]) and None not in series[i][t - 7:t + 9]
                and statistics.median(series[i][t - 7:t + 1]) >= backtest.FLOOR]
        if elig:
            base.append(sum(statistics.median(w[t + 1:t + 9]) >= backtest.JUMP * statistics.median(w[t - 7:t + 1])
                            for w in elig) / len(elig))
    return {"calls": made, "called_it": hits, "base_rate": round(sum(base) / len(base), 4) if base else None}
