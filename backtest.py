"""Hipster backtest, exactly as PREREG.txt fixes it. Run: python3 backtest.py  (writes cache/backtest.json)."""
import datetime as dt, json, math, random, statistics, sys
import universe

K, FLOOR, JUMP, NEIGHBOUR_WEIGHT = 10, 700, 1.5, 1.0
DEV = ("2024-01-07", "2024-12-29")
TEST = ("2025-01-05", "2026-08-16")
FIRST_MONDAY = dt.date(2023, 7, 3)

def weekly(daily, first=FIRST_MONDAY, last=dt.date(2026, 10, 11)):
    """Daily {YYYYMMDD: views} to a list of Monday-to-Sunday totals. A week with a missing day is None."""
    out, d = [], first
    while d + dt.timedelta(6) <= last:
        days = [(d + dt.timedelta(i)).strftime("%Y%m%d") for i in range(7)]
        out.append(sum(daily[x] for x in days) if all(x in daily for x in days) else None)
        d += dt.timedelta(7)
    return out

def week_end(t):
    return FIRST_MONDAY + dt.timedelta(7 * t + 6)

def week_index(sunday):
    return (dt.date.fromisoformat(sunday) - FIRST_MONDAY).days // 7

def momentum(w, t):
    return math.log(1 + (w[t - 1] + w[t]) / 2) - math.log(1 + statistics.median(w[t - 7:t - 1]))

def cutoff(series, graph, t):
    """One cutoff. series: {id: weekly list}. Returns eligible ids, breakout set, and the ranking of each arm."""
    elig = [i for i, w in series.items()
            if t - 7 >= 0 and t + 8 < len(w) and None not in w[t - 7:t + 9] and statistics.median(w[t - 7:t + 1]) >= FLOOR]
    past = {i: statistics.median(series[i][t - 7:t + 1]) for i in elig}
    hit = {i for i in elig if statistics.median(series[i][t + 1:t + 9]) >= JUMP * past[i]}
    m = {i: momentum(series[i], t) for i in elig}
    q = {}
    for i in elig:
        nb = [m[j] for j in graph.get(i, ()) if j in m]
        q[i] = m[i] + NEIGHBOUR_WEIGHT * (sum(nb) / len(nb) if nb else 0.0)
    top = lambda score: sorted(elig, key=lambda i: (-score[i], i))[:K]
    return elig, hit, {"P": top(past), "M": top(m), "Q": top(q)}, q

def prec(picks, hit):
    return sum(i in hit for i in picks) / len(picks) if picks else 0.0

def block_ci(xs, block=8, n=2000, seed=7):
    rng, L = random.Random(seed), len(xs)
    means = []
    for _ in range(n):
        s = []
        while len(s) < L:
            j = rng.randrange(0, L - block + 1)
            s.extend(xs[j:j + block])
        means.append(sum(s[:L]) / L)
    means.sort()
    return [round(means[int(0.025 * n)], 4), round(means[int(0.975 * n) - 1], 4)]

def run(series, graph, start, end):
    rows = []
    for t in range(week_index(start), week_index(end) + 1):
        elig, hit, arms, q = cutoff(series, graph, t)
        if not elig:
            continue
        w = {i: series[i] for i in arms["Q"]}
        peaks = [max(range(1, 9), key=lambda h: w[i][t + h]) for i in arms["Q"] if i in hit]
        rows.append({"week": str(week_end(t)), "eligible": len(elig), "base": len(hit) / len(elig),
                     **{a: prec(p, hit) for a, p in arms.items()}, "q_peak_weeks": peaks})
    s = {"cutoffs": len(rows), "mean_eligible": round(statistics.mean(r["eligible"] for r in rows), 1)}
    for a in ("base", "P", "M", "Q"):
        xs = [r[a] for r in rows]
        s[a] = {"mean": round(statistics.mean(xs), 4), "ci": block_ci(xs)}
    for a, b in (("Q", "P"), ("Q", "M"), ("Q", "base"), ("M", "P")):
        xs = [r[a] - r[b] for r in rows]
        s[f"{a}-{b}"] = {"mean": round(statistics.mean(xs), 4), "ci": block_ci(xs)}
    s["Q_lift"] = round(s["Q"]["mean"] / s["base"]["mean"], 2) if s["base"]["mean"] else None
    pk = [p for r in rows for p in r["q_peak_weeks"]]
    s["Q_hit_median_weeks_to_peak"] = statistics.median(pk) if pk else None
    return s, rows

def verdict(s):
    k1 = s["Q-P"]["ci"][0] > 0 and s["Q-base"]["ci"][0] > 0
    k2 = s["Q-M"]["ci"][0] > 0
    return {"K1_hipster_is_a_result": k1, "K2_qloo_earns_its_place": k2}

def load_series():
    u = universe.load()
    titles = json.load(open(universe.HERE / "cache" / "titles.json"))
    views = json.load(open(universe.HERE / "cache" / "views.json"))
    series = {}
    for i, e in u.items():
        ti = titles.get((e["wikidata"] or "").upper())
        if ti in views:
            series[i] = weekly(views[ti])
    graph = {i: [j for j in e["neighbours"] if j in series] for i, e in u.items() if i in series}
    return u, series, graph

if __name__ == "__main__":
    u, series, graph = load_series()
    out = {"artists_with_series": len(series)}
    for name, (a, b) in (("dev", DEV), ("test", TEST)):
        s, rows = run(series, graph, a, b)
        out[name] = {"summary": s, "verdict": verdict(s), "rows": rows}
        print(name, json.dumps(s), json.dumps(verdict(s)))
    json.dump(out, open(universe.HERE / "cache" / "backtest.json", "w"), indent=1)
