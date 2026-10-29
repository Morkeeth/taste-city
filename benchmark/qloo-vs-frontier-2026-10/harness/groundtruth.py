"""Ground-truth checks G1 (places) and G2 (artists, films, books) for Qloo bench answers. No Qloo calls.

Step 1 extract: one claude -p call per answer set lists the named entities in each answer. An extracted name is
  kept only if it appears verbatim in that answer's text, so the extractor cannot add names.
Step 2 check, each lookup cached in gt-cache.json:
  G1 place  -> OpenStreetMap Nominatim search "<name>, London". Exists = a result inside Greater London's bounding box.
              Usage policy (operations.osmfoundation.org/policies/nominatim): at most 1 request per second, an identifying
              User-Agent, results cached. Data (c) OpenStreetMap contributors, ODbL.
  G2 work   -> Wikidata wbsearchentities exact label match (exists), then English Wikipedia pageviews for the last
              60 full days via the Wikimedia REST API. LESSER_KNOWN is frozen below before any lookup.
Run: python3 groundtruth.py extract | check | summary"""
import json, re, subprocess, sys, tempfile, time, urllib.parse, urllib.request
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent
SETS = {}  # the 29 Oct held-out sets lived outside this folder; the functions below are what the ladder uses
UA = 'TasteCityResearch/0.1 (+https://github.com/Morkeeth/taste-city) groundtruth.py'
LONDON = (51.28, 51.70, -0.52, 0.34)          # lat min, lat max, lon min, lon max (Greater London bbox)
LESSER_KNOWN = 30_000                           # frozen 29 Oct: under 30,000 enwiki views in 60 days (about 500 a day)
CACHE = OUT/'gt-cache.json'
cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
_last = [0.0]


def get(url, pace=1.1):
    if url in cache:
        return cache[url]
    wait = pace - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body = {'http_error': e.code}
        _last[0] = time.time()
        # An API error is not an answer: never cache it, and never let it read as "does not exist".
        if isinstance(body, dict) and ('error' in body or body.get('http_error') in (429, 500, 502, 503, 504)):
            time.sleep(5 * (attempt + 1))
            continue
        cache[url] = body
        CACHE.write_text(json.dumps(cache))
        return body
    return {'unanswered': True}


EXTRACT = ('List every specific named real-world entity in each answer below: venues, shops, institutions, places, towns, '
           'artists, bands, films, books, albums, events, brands. Do not list generic things ("a bookshop", "jazz"). '
           'Copy each name exactly as written in the answer. Return ONLY JSON: {"<id>": [{"name": str, "kind": '
           '"place"|"town"|"artist"|"film"|"book"|"album"|"other"}]}. Do not use tools or read files.\n\n{items}')


def extract():
    out = OUT/'entities.json'
    data = json.loads(out.read_text()) if out.exists() else {}
    for set_name, path in SETS.items():
        if set_name in data:
            continue
        answers = json.loads(path.read_text())
        items = '\n\n'.join(f'[{k}]\n{v["text"]}' for k, v in answers.items())
        with tempfile.TemporaryDirectory() as d:
            p = subprocess.run(['claude', '-p', '--setting-sources', '', '--strict-mcp-config', '--tools', '',
                                '--model', 'claude-opus-5-5', '--output-format', 'json', EXTRACT.replace('{items}', items)],
                               cwd=d, capture_output=True, text=True, timeout=900)
        raw = json.loads(p.stdout)['result']
        got = json.loads(raw[raw.index('{'):raw.rindex('}')+1])
        kept, dropped = {}, 0
        for k, ents in got.items():
            text = answers.get(k, {}).get('text', '')
            ok = [e for e in ents if e.get('name') and e['name'] in text]
            dropped += len(ents) - len(ok)
            kept[k] = ok
        data[set_name] = {'entities': kept, 'dropped_not_verbatim': dropped}
        out.write_text(json.dumps(data, indent=1, ensure_ascii=False))
        print(set_name, sum(map(len, kept.values())), 'entities kept,', dropped, 'dropped')


def check_place(name):
    q = urllib.parse.urlencode({'q': f'{name}, London', 'format': 'jsonv2', 'limit': 3})
    res = get(f'https://nominatim.openstreetmap.org/search?{q}')
    hits = [r for r in res if isinstance(r, dict) and LONDON[0] <= float(r['lat']) <= LONDON[1]
            and LONDON[2] <= float(r['lon']) <= LONDON[3]] if isinstance(res, list) else []
    return {'exists_in_london': bool(hits), 'osm': hits[0]['display_name'][:90] if hits else None}


def check_town(name):
    q = urllib.parse.urlencode({'q': name, 'format': 'jsonv2', 'limit': 1, 'countrycodes': 'gb'})
    res = get(f'https://nominatim.openstreetmap.org/search?{q}')
    return {'exists_in_uk': bool(res) and isinstance(res, list), 'osm': res[0]['display_name'][:90] if res else None}


KIND_WORDS = {'artist': r'musician|singer|band|rapper|producer|composer|DJ|artist|duo|group|ensemble|songwriter|record',
              'film': r'film|movie', 'book': r'novel|book|memoir|literary|poetry|essay|non-fiction',
              'album': r'album|EP|record'}


def check_work(name, kind):
    q = urllib.parse.urlencode({'action': 'wbsearchentities', 'search': name, 'language': 'en', 'limit': 5, 'format': 'json'})
    res = get(f'https://www.wikidata.org/w/api.php?{q}', pace=1.0)
    if res.get('unanswered'):
        return {'exists': None, 'qid': None, 'views_60d': None, 'note': 'Wikidata did not answer'}
    norm = lambda x: re.sub(r'[^\w]+', ' ', x).strip().casefold()
    exact = [r for r in res.get('search', []) if norm(r.get('label', '')) == norm(name)
             or norm(name) in [norm(a) for a in r.get('aliases', [])]]
    want = KIND_WORDS.get(kind)
    fit = [r for r in exact if want and re.search(want, r.get('description', ''), re.I)]
    if not exact:
        return {'exists': False, 'qid': None, 'views_60d': None}
    if want and not fit:
        return {'exists': None, 'qid': None, 'views_60d': None,
                'note': 'label found, but no candidate described as a ' + kind}
    exact = fit or exact
    qid = exact[0]['id']
    ent = get(f'https://www.wikidata.org/wiki/Special:EntityData/{qid}.json', pace=1.0)
    title = (((ent.get('entities') or {}).get(qid) or {}).get('sitelinks') or {}).get('enwiki', {}).get('title')
    views = None
    if title:
        end = date(2026, 10, 28); start = end - timedelta(days=59)   # frozen window: 30 Aug to 28 Oct 2026
        t = urllib.parse.quote(title.replace(' ', '_'), safe='')
        pv = get(f'https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/'
                 f'{t}/daily/{start:%Y%m%d}/{end:%Y%m%d}', pace=1.0)
        views = sum(i['views'] for i in pv.get('items', [])) if 'items' in pv else None
    return {'exists': True, 'qid': qid, 'enwiki': title, 'views_60d': views,
            'lesser_known': views is not None and views < LESSER_KNOWN}


def check():
    ents = json.loads((OUT/'entities.json').read_text()); out = {}
    for set_name, d in ents.items():
        for k, lst in d['entities'].items():
            for e in lst:
                kind = e['kind']
                key = f"{kind}|{e['name']}"
                if key in out:
                    continue
                out[key] = check_place(e['name']) if kind == 'place' else check_town(e['name']) if kind == 'town' \
                    else check_work(e['name'], kind) if kind in ('artist', 'film', 'book', 'album') else {'skipped': kind}
                print(key, out[key], flush=True)
    (OUT/'gt-checks.json').write_text(json.dumps(out, indent=1, ensure_ascii=False))


def summary():
    ents = json.loads((OUT/'entities.json').read_text()); chk = json.loads((OUT/'gt-checks.json').read_text())
    res = {}
    for set_name, d in ents.items():
        answers = json.loads(SETS[set_name].read_text())
        for k, lst in d['entities'].items():
            a = answers[k]; cell = res.setdefault(set_name, {}).setdefault(f"{a['answerer']}|{a['arm']}", {
                'answers': 0, 'named': 0, 'places': 0, 'places_real_london': 0, 'towns': 0, 'towns_real_uk': 0,
                'works': 0, 'works_exist': 0, 'works_lesser_known': 0, 'not_found': []})
            cell['answers'] += 1
            for e in lst:
                c = chk.get(f"{e['kind']}|{e['name']}", {}); cell['named'] += 1
                if e['kind'] == 'place':
                    cell['places'] += 1; cell['places_real_london'] += c.get('exists_in_london', False)
                    if not c.get('exists_in_london'): cell['not_found'].append(e['name'])
                elif e['kind'] == 'town':
                    cell['towns'] += 1; cell['towns_real_uk'] += c.get('exists_in_uk', False)
                elif e['kind'] in ('artist', 'film', 'book', 'album'):
                    cell['works'] += 1; cell['works_exist'] += bool(c.get('exists')); cell['works_unknown'] = cell.get('works_unknown', 0) + (c.get('exists') is None)
                    cell['works_lesser_known'] += bool(c.get('lesser_known'))
                    if c.get('exists') is False: cell['not_found'].append(e['name'])
    (OUT/'gt-summary.json').write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    {'extract': extract, 'check': check, 'summary': summary}[sys.argv[1]]()
