"""Fetch the pairing source: English Wikipedia daily pageviews for every universe artist.
Wikidata id -> enwiki title (wbgetentities, 50 per call), then one daily pageviews call per title.
Writes cache/titles.json and cache/views.json. No key. The User-Agent carries no email (hack.md log, 14 Oct)."""
import json, pathlib, sys, time, urllib.parse, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
import universe

UA = "hipster-backtest/0.1 (hackathon research; https://github.com/Morkeeth)"
CACHE = universe.HERE / "cache"
START, END = "20230701", "20261011"

def get(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, {}
            if e.code == 429:
                time.sleep(2 ** attempt); continue
            return e.code, {}
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 ** attempt)
    return 0, {}

def titles(qids):
    out = {}
    for i in range(0, len(qids), 50):
        chunk = qids[i:i + 50]
        url = ("https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&props=sitelinks&sitefilter=enwiki&ids="
               + "|".join(chunk))
        status, body = get(url)
        for q, ent in (body.get("entities") or {}).items():
            t = (ent.get("sitelinks") or {}).get("enwiki", {}).get("title")
            if t:
                out[q] = t
        time.sleep(0.2)
    return out

def views(title):
    art = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
           f"{art}/daily/{START}/{END}")
    status, body = get(url)
    return title, status, {it["timestamp"][:8]: it["views"] for it in body.get("items", [])}

def main():
    CACHE.mkdir(exist_ok=True)
    u = universe.load()
    qids = sorted({e["wikidata"].upper() for e in u.values() if e["wikidata"]})
    tpath = CACHE / "titles.json"
    t = json.load(open(tpath)) if tpath.exists() else titles(qids)
    json.dump(t, open(tpath, "w"), indent=1)
    print(f"wikidata ids {len(qids)}, enwiki titles {len(t)}", file=sys.stderr)
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(views, sorted(set(t.values()))))
    bad = [(ti, s) for ti, s, _ in res if s != 200]
    json.dump({ti: v for ti, s, v in res if s == 200}, open(CACHE / "views.json", "w"))
    print(f"pageview series {len(res) - len(bad)} ok, {len(bad)} failed {bad[:5]}", file=sys.stderr)

if __name__ == "__main__":
    main()
