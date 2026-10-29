"""HARD G1 ladder (29 Oct): smaller cities, 500 m radius, niche categories. 9 answerers.
Step 0 control: seed audience + question. Step 1 one change: + Qloo places within 500 m (filter.location, radius 500,
audience signal), fetched live BEFORE freezing (one call per point, counted in live-calls.jsonl).
Scored by OpenStreetMap Nominatim: found within the bounded box, then distance <= 0.5 km; misses go to hand-check.
Run: python3 hard.py context | freeze | answer STEP [models] | score STEP"""
import concurrent.futures as cf, json, sys, threading, urllib.parse
from pathlib import Path
import ladder, models, qloo_live as Q

OUT = Path(__file__).resolve().parent
PTS = json.loads((OUT/'hard-points.json').read_text())
R_KM = 0.5
BASE = 'You are advising a small cultural events team. Do not use tools or read files.\n\n'
SEED = 'Audience: people whose taste is anchored by Björk, Radiohead and Little Simz.\n\n'


def question(city, p):
    return (f'Which 5 real places within 500 metres of {p["address"]} ({city}) would this audience go to: independent record shops, '
            f'listening bars, independent cinemas, small music venues or cafes?')


def context():
    f = OUT/'hard-qloo-context.json'
    ctx = json.loads(f.read_text()) if f.exists() else {}
    sig = Q.seed_ids(Q.SEEDS)
    for city, p in PTS.items():
        if city in ctx:
            continue
        st, b = Q.call('/v2/insights', {'filter.type': 'urn:entity:place', 'filter.location': f'POINT({p["lon"]} {p["lat"]})',
                                        'filter.location.radius': 500, 'signal.interests.entities': sig, 'take': 25}, f'B hard G1 context {city}')
        rows = []
        for e in Q.entities(b):
            loc = e.get('location') or {}
            if loc.get('lat') is None:
                continue
            d = ladder.km((p['lat'], p['lon']), (loc['lat'], loc['lon']))
            if d <= R_KM:
                tags = [t['name'] for t in (e.get('tags') or []) if t.get('name')][:3]
                addr = ((e.get('properties') or {}).get('address') or '')[:60]
                rows.append({'name': e['name'], 'km': round(d, 2), 'addr': addr, 'tags': tags, 'popularity': round(e.get('popularity', 0), 3)})
        ctx[city] = {'status': st, 'returned': len(Q.entities(b)), 'within_500m': rows}
        f.write_text(json.dumps(ctx, indent=1, ensure_ascii=False))
        print(city, st, len(Q.entities(b)), 'within 500 m:', len(rows), 'qloo calls used', Q.used(), flush=True)


def freeze():
    f = OUT/'FROZEN-HARD.json'
    if f.exists():
        raise SystemExit('already frozen')
    ctx = json.loads((OUT/'hard-qloo-context.json').read_text())
    qs, ctxt = [], {}
    for city, p in PTS.items():
        qid = 'h_' + city.lower().replace(' ', '')
        qs.append({'id': qid, 'city': city, 'lat': p['lat'], 'lon': p['lon'], 'question': question(city, p)})
        ctxt[qid] = '\n'.join(f"- {r['name']} ({r['addr']}; {r['km']} km; tags: {', '.join(r['tags'])})" for r in ctx[city]['within_500m']) or '- (Qloo returned no place within 500 m)'
    frozen = {'at': ladder.now(), 'radius_km': R_KM, 'questions': qs, 'answerers': models.ALL,
              'steps': {'0_control': BASE + SEED + ladder.FMT + 'Question: {question}',
                        '1_qloo_location': BASE + SEED + 'Qloo places within 500 m of that address, ranked for this audience '
                                           '(taste signal, not demand):\n{ctx}\n\n' + ladder.FMT + 'Question: {question}'},
              'ctx': ctxt, 'qloo_context_file_sha256': ladder.sha((OUT/'hard-qloo-context.json').read_bytes())}
    body = json.dumps(frozen, indent=1, ensure_ascii=False)
    f.write_text(body); (OUT/'FROZEN-HARD.sha256').write_text(ladder.sha(body)+'\n'); print('frozen', ladder.sha(body))


def load():
    body = (OUT/'FROZEN-HARD.json').read_text()
    assert ladder.sha(body) == (OUT/'FROZEN-HARD.sha256').read_text().strip(), 'frozen inputs changed'
    return json.loads(body)


def answer(step, who):
    fr, path, lock = load(), OUT/f'answers-hard-{step}.json', threading.Lock()
    data = json.loads(path.read_text()) if path.exists() else {}
    jobs = [(m, q) for m in who for q in fr['questions'] if f'{m}|{q["id"]}' not in data]

    def one(job):
        m, q = job
        prompt = fr['steps'][step].replace('{ctx}', fr['ctx'][q['id']]).replace('{question}', q['question'])
        try:
            text, meta = models.ask(m, prompt, f'hard {step} {q["id"]}')
        except Exception as e:
            print('FAIL', m, q['id'], str(e)[:150], flush=True); return
        with lock:
            data[f'{m}|{q["id"]}'] = {'qid': q['id'], 'text': text, 'meta': meta}
            path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
        print('answered', step, m, q['id'], flush=True)
    with cf.ThreadPoolExecutor(6) as ex:
        list(ex.map(one, jobs))


def place(name, q):
    lat, lon, d = q['lat'], q['lon'], 0.012
    p = urllib.parse.urlencode({'q': name, 'format': 'jsonv2', 'limit': 5, 'bounded': 1, 'viewbox': f'{lon-d*1.5},{lat+d},{lon+d*1.5},{lat-d}'})
    res = ladder.gt.get(f'https://nominatim.openstreetmap.org/search?{p}')
    if isinstance(res, dict) and res.get('unanswered'):
        return {'status': 'unknown'}
    best = min(((ladder.km((lat, lon), (float(r['lat']), float(r['lon']))), r['display_name'][:80]) for r in res), default=None) if isinstance(res, list) else None
    if best and best[0] <= R_KM:
        return {'status': 'in_radius', 'km': round(best[0], 2), 'osm': best[1]}
    p2 = urllib.parse.urlencode({'q': f'{name}, {q["city"].split()[0]}', 'format': 'jsonv2', 'limit': 1})
    res2 = ladder.gt.get(f'https://nominatim.openstreetmap.org/search?{p2}')
    if best or (isinstance(res2, list) and res2):
        far = best[0] if best else ladder.km((lat, lon), (float(res2[0]['lat']), float(res2[0]['lon'])))
        return {'status': 'exists_out_of_radius', 'km': round(far, 2), 'osm': (best[1] if best else res2[0]['display_name'][:80])}
    return {'status': 'not_found_hand_check'}


def score(step):
    fr = load(); ans = json.loads((OUT/f'answers-hard-{step}.json').read_text()); qs = {q['id']: q for q in fr['questions']}
    res, rows = {}, []
    for k, a in sorted(ans.items()):
        m = k.split('|')[0]; q = qs[a['qid']]; ns = ladder.names(a['text'])
        c = res.setdefault(m, {'answers': 0, 'named': 0, 'in_radius': 0, 'out_of_radius': 0, 'not_found': 0, 'unknown': 0, 'unparsed': 0})
        c['answers'] += 1; c['unparsed'] += len(ns) != 5
        for n in ns:
            r = place(n, q); c['named'] += 1
            c[{'in_radius': 'in_radius', 'exists_out_of_radius': 'out_of_radius', 'not_found_hand_check': 'not_found', 'unknown': 'unknown'}[r['status']]] += 1
            rows.append({'model': m, 'qid': a['qid'], 'name': n, **r})
    (OUT/f'score-hard-{step}.json').write_text(json.dumps({'at': ladder.now(), 'per_model': res, 'rows': rows}, indent=1, ensure_ascii=False))
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'context': context()
    elif cmd == 'freeze': freeze()
    elif cmd == 'answer': answer(sys.argv[2], sys.argv[3:] or models.ALL)
    elif cmd == 'score': score(sys.argv[2])
