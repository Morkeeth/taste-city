"""Per-model ladder, 29 Oct. For each frontier model: does the smallest Qloo-based change beat the context-matched control
on GROUND-TRUTH tasks? Step 0 = control (seed audience only). Later steps add exactly one change each.

G1 near-address venues: "5 real places within 1.5 km of <postcode>". Scored by OpenStreetMap Nominatim: found inside a
   bounded box around the postcode, then haversine distance <= 1.5 km. Not found nearby -> searched London-wide ->
   still not found goes to a hand-check list before it can count as invented.
G2 long tail: "5 lesser-known musicians / films / books". Scored by Wikidata existence (kind-checked) and English
   Wikipedia pageviews in a frozen 60-day window; lesser-known = under 30,000 views. Not on Wikidata -> hand-check list.
The model call wraps the claude and codex CLIs (subscription).
Run: python3 ladder.py freeze | answer STEP [models] | score STEP"""
import concurrent.futures as cf, hashlib, json, math, re, subprocess, sys, tempfile, threading, time, urllib.parse
from datetime import datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
import groundtruth as gt  # noqa: E402  (Nominatim/Wikidata/pageview lookups with cache, errors -> unknown)
gt.CACHE = OUT.parent/'data'/'osm-cache.json'; gt.cache = json.loads(gt.CACHE.read_text()) if gt.CACHE.exists() else {}

now = lambda: datetime.now().astimezone().isoformat(timespec='seconds')
sha = lambda b: hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()
MODELS = {'opus': ('claude', 'claude-opus-5-5'), 'fable': ('claude', 'claude-fable-5-1'),
          'sonnet': ('claude', 'claude-sonnet-5-5'), 'gpt': ('codex', 'gpt-6.1-sol')}
POSTCODES = {'E8 3DE': (51.5461200, -0.0751800), 'SE15 5DQ': (51.4703724, -0.0691688), 'SW9 8HE': (51.4625587, -0.1146777),
             'NW1 8AB': (51.5414918, -0.1457377), 'SE8 4NS': (51.4782193, -0.0260554)}   # Nominatim postcode centroids, 29 Oct
RADIUS_KM = 1.5
SEED = 'Audience: London, people whose taste is anchored by Björk, Radiohead and Little Simz.\n\n'
BASE = 'You are advising a small London coffee shop and cultural events team. Do not use tools or read files.\n\n'
FMT = ('Answer as a numbered list of exactly 5 items. Each line: the name only, then " - " and a reason of at most '
       '10 words. No other text.\n\n')
G1 = [{'id': f'g1_{pc.split()[0].lower()}', 'task': 'G1', 'postcode': pc,
       'question': f'Which 5 real places (venues, cafes, galleries, record shops, bookshops, cinemas) within 1.5 km of '
                   f'postcode {pc}, London, would this audience go to?'} for pc in POSTCODES]
G2 = [{'id': 'g2_music_uk', 'task': 'G2', 'kind': 'artist', 'question': 'Which 5 lesser-known UK musicians or bands, not household names, would this audience love?'},
      {'id': 'g2_music_any', 'task': 'G2', 'kind': 'artist', 'question': 'Which 5 lesser-known musicians or bands from outside the UK, not household names, would this audience love?'},
      {'id': 'g2_film', 'task': 'G2', 'kind': 'film', 'question': 'Which 5 lesser-known films, not mainstream hits, should the cafe screen for this audience?'},
      {'id': 'g2_book', 'task': 'G2', 'kind': 'book', 'question': 'Which 5 lesser-known books, not bestsellers, should the reading club pick for this audience?'},
      {'id': 'g2_album', 'task': 'G2', 'kind': 'album', 'question': 'Which 5 lesser-known albums, not famous records, should the cafe play for this audience?'}]


def freeze():
    f = OUT/'FROZEN-LADDER.json'
    if f.exists():
        raise SystemExit('already frozen')
    frozen = {'at': now(), 'questions': G1 + G2, 'models': MODELS, 'radius_km': RADIUS_KM, 'postcodes': POSTCODES,
              'steps': {'0_control': BASE + SEED + FMT + 'Question: {question}'},
              'later_steps_one_change_each': ['1 popularity cap (Qloo filter.popularity.max) for G2, location filter '
                                              '(filter.location + radius) for G1: needs live Qloo calls',
                                              '2 Qloo verifies the model\'s own picks: needs live Qloo calls',
                                              '3 entity citing'],
              'scoring': 'ground truth by lookup (see ladder.py docstring); every not-found hand-checked before it counts',
              'lesser_known_views_60d': gt.LESSER_KNOWN, 'grader': 'none for step 0: scored by lookups, not opinion'}
    body = json.dumps(frozen, indent=1, ensure_ascii=False)
    f.write_text(body); (OUT/'FROZEN-LADDER.sha256').write_text(sha(body)+'\n'); print('frozen', sha(body))


def load():
    body = (OUT/'FROZEN-LADDER.json').read_text()
    assert sha(body) == (OUT/'FROZEN-LADDER.sha256').read_text().strip(), 'frozen inputs changed'
    return json.loads(body)


def run_cli(cli, model, prompt, tries=3):
    for attempt in range(1, tries+1):
        with tempfile.TemporaryDirectory() as d:
            t0 = time.time()
            if cli == 'claude':
                p = subprocess.run(['claude', '-p', '--setting-sources', '', '--strict-mcp-config', '--tools', '', '--model', model,
                                    '--output-format', 'json', prompt], cwd=d, capture_output=True, text=True, timeout=600)
                try:
                    j = json.loads(p.stdout)
                    if not j.get('is_error') and j.get('result'):
                        return j['result'].strip(), {'model': list((j.get('modelUsage') or {}).keys()), 'attempt': attempt, 'seconds': round(time.time()-t0, 1)}
                except Exception:
                    pass
            else:
                f = Path(d)/'last.txt'
                p = subprocess.run(['codex', 'exec', '--skip-git-repo-check', '--ephemeral', '-s', 'read-only', '-m', model,
                                    '-o', str(f), prompt], cwd=d, capture_output=True, text=True, timeout=900)
                if p.returncode == 0 and f.exists() and f.read_text().strip():
                    return f.read_text().strip(), {'model': [model], 'attempt': attempt, 'seconds': round(time.time()-t0, 1)}
    raise RuntimeError(f'{model} failed {tries} times')


def answer(step, models):
    fr, path, lock = load(), OUT/f'answers-{step}.json', threading.Lock()
    data = json.loads(path.read_text()) if path.exists() else {}
    tmpl = fr['steps'][step]
    jobs = [(m, q) for m in models for q in fr['questions'] if f'{m}|{q["id"]}' not in data]

    def one(job):
        m, q = job; cli, model = fr['models'][m]
        text, meta = run_cli(cli, model, tmpl.replace('{question}', q['question']))
        with lock:
            data[f'{m}|{q["id"]}'] = {'model': m, 'qid': q['id'], 'text': text, **meta}
            path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
        print('answered', m, q['id'], meta, flush=True)
    with cf.ThreadPoolExecutor(4) as ex:
        list(ex.map(one, jobs))


def names(text):
    out = []
    for line in text.splitlines():
        m = re.match(r'\s*\d+[.)]\s*\**(.+?)\**\s*(?:[-–—:]\s+.*)?$', line)
        if m:
            n = re.sub(r'\s*\(.*?\)\s*$', '', m.group(1)).strip(' *"[]')
            n = re.sub(r'\s+by\s+[A-Z][^,]*$', '', n)                                  # "Title by Author" -> title
            al = re.match(r'^(.+?),\s*["\u201c](.+?)["\u201d]?$', n)                     # 'Artist, "Album"' -> album
            n = al.group(2) if al else n
            out.append(n.strip(' *"[]'))
    return out


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 6371 * 2 * math.asin(math.sqrt(h))


def place(name, pc):
    lat, lon = POSTCODES[pc]; d = 0.03
    q = urllib.parse.urlencode({'q': name, 'format': 'jsonv2', 'limit': 5, 'bounded': 1,
                                'viewbox': f'{lon-d*1.6},{lat+d},{lon+d*1.6},{lat-d}'})
    res = gt.get(f'https://nominatim.openstreetmap.org/search?{q}')
    if isinstance(res, dict) and res.get('unanswered'):
        return {'status': 'unknown'}
    best = min(((km((lat, lon), (float(r['lat']), float(r['lon']))), r['display_name'][:80]) for r in res), default=None) if isinstance(res, list) else None
    if best and best[0] <= RADIUS_KM:
        return {'status': 'in_radius', 'km': round(best[0], 2), 'osm': best[1]}
    london = gt.check_place(name)
    if best or london.get('exists_in_london'):
        return {'status': 'exists_out_of_radius', 'km': round(best[0], 2) if best else None, 'osm': (best or [None, london.get('osm')])[1]}
    return {'status': 'not_found_hand_check'}


def score(step):
    fr = load(); ans = json.loads((OUT/f'answers-{step}.json').read_text()); qs = {q['id']: q for q in fr['questions']}
    res, rows = {}, []
    for k, a in sorted(ans.items()):
        a = {**a, 'model': k.split('|')[0]}
        q = qs[a['qid']]; ns = names(a['text'])
        cell = res.setdefault(a['model'], {'G1_named': 0, 'G1_in_radius': 0, 'G1_out_of_radius': 0, 'G1_not_found': 0, 'G1_unknown': 0,
                                           'G2_named': 0, 'G2_exists': 0, 'G2_lesser_known': 0, 'G2_not_found': 0, 'G2_unknown': 0, 'unparsed_answers': 0})
        if len(ns) != 5:
            cell['unparsed_answers'] += 1
        for n in ns:
            if q['task'] == 'G1':
                r = place(n, q['postcode']); cell['G1_named'] += 1
                cell[{'in_radius': 'G1_in_radius', 'exists_out_of_radius': 'G1_out_of_radius', 'not_found_hand_check': 'G1_not_found', 'unknown': 'G1_unknown'}[r['status']]] += 1
            else:
                r = gt.check_work(n, q['kind']); cell['G2_named'] += 1
                if r.get('exists') is True:
                    cell['G2_exists'] += 1; cell['G2_lesser_known'] += bool(r.get('lesser_known'))
                elif r.get('exists') is False:
                    cell['G2_not_found'] += 1
                else:
                    cell['G2_unknown'] += 1
            rows.append({'model': a['model'], 'qid': a['qid'], 'name': n, **r})
            print(a['model'], a['qid'], n, r, flush=True)
    (OUT/f'score-{step}.json').write_text(json.dumps({'at': now(), 'frozen_sha256': (OUT/'FROZEN-LADDER.sha256').read_text().strip(),
                                                       'per_model': res, 'rows': rows}, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'freeze':
        freeze()
    elif cmd == 'answer':
        answer(sys.argv[2], sys.argv[3:] or list(MODELS))
    elif cmd == 'score':
        score(sys.argv[2])
