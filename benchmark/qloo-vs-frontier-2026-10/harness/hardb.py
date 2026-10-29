"""HARD G1, second audience (29 Oct): is the Qloo location gain one-audience luck?
Audience B: Ezra Collective, Nubya Garcia, Moses Boyd (UK jazz). Qloo IDs: in the 29 Oct run they came from a recorded
15 Oct file (no lookup calls); for a rerun, resolve them by name with qloo_live.resolve_seeds. 5 of the 10 hard points (Leeds, Lyon, Ghent, Porto, Valencia), same 500 m task, same two steps,
same 9 answerers, same scoring (hard.place, then resolve.py's Overpass match). 5 live Qloo calls.
Run: python3 hardb.py context | freeze | answer STEP | score"""
import concurrent.futures as cf, json, sys, threading
from pathlib import Path
import hard, ladder, models, qloo_live as Q, resolve as R

OUT = Path(__file__).resolve().parent
SEEDS_B = {'Ezra Collective': None, 'Nubya Garcia': None, 'Moses Boyd': None}   # resolved by name at run time
CITIES = ['Leeds', 'Lyon', 'Ghent', 'Porto', 'Valencia']
SEED = 'Audience: people whose taste is anchored by Ezra Collective, Nubya Garcia and Moses Boyd.\n\n'
F, CTXF = OUT/'FROZEN-HARD-B.json', OUT/'hardb-qloo-context.json'


def context():
    ctx = json.loads(CTXF.read_text()) if CTXF.exists() else {}
    for city in CITIES:
        if city in ctx:
            continue
        p = hard.PTS[city]
        st, b = Q.call('/v2/insights', {'filter.type': 'urn:entity:place', 'filter.location': f'POINT({p["lon"]} {p["lat"]})',
                                        'filter.location.radius': 500, 'signal.interests.entities': Q.seed_ids(SEEDS_B),
                                        'take': 25}, f'B hard G1 audience-B context {city}')
        rows = []
        for e in Q.entities(b):
            loc = e.get('location') or {}
            if loc.get('lat') is None:
                continue
            d = ladder.km((p['lat'], p['lon']), (loc['lat'], loc['lon']))
            if d <= hard.R_KM:
                rows.append({'name': e['name'], 'km': round(d, 2), 'addr': ((e.get('properties') or {}).get('address') or '')[:60],
                             'tags': [t['name'] for t in (e.get('tags') or []) if t.get('name')][:3]})
        ctx[city] = {'status': st, 'returned': len(Q.entities(b)), 'within_500m': rows}
        CTXF.write_text(json.dumps(ctx, indent=1, ensure_ascii=False))
        print(city, st, len(rows), 'qloo calls used', Q.used(), flush=True)


def freeze():
    if F.exists():
        raise SystemExit('already frozen')
    ctx = json.loads(CTXF.read_text()); qs, ct = [], {}
    for city in CITIES:
        p = hard.PTS[city]; qid = 'hb_' + city.lower()
        qs.append({'id': qid, 'city': city, 'lat': p['lat'], 'lon': p['lon'], 'question': hard.question(city, p)})
        ct[qid] = '\n'.join(f"- {r['name']} ({r['addr']}; {r['km']} km; tags: {', '.join(r['tags'])})" for r in ctx[city]['within_500m']) or '- (none)'
    frozen = {'at': ladder.now(), 'audience': list(SEEDS_B), 'questions': qs, 'ctx': ct,
              'steps': {'0_control': hard.BASE + SEED + ladder.FMT + 'Question: {question}',
                        '1_qloo_location': hard.BASE + SEED + 'Qloo places within 500 m of that address, ranked for this audience '
                                           '(taste signal, not demand):\n{ctx}\n\n' + ladder.FMT + 'Question: {question}'}}
    body = json.dumps(frozen, indent=1, ensure_ascii=False)
    F.write_text(body); (OUT/'FROZEN-HARD-B.sha256').write_text(ladder.sha(body)+'\n'); print('frozen', ladder.sha(body))


def answer(step):
    body = F.read_text(); assert ladder.sha(body) == (OUT/'FROZEN-HARD-B.sha256').read_text().strip()
    fr, path, lock = json.loads(body), OUT/f'answers-hardb-{step}.json', threading.Lock()
    data = json.loads(path.read_text()) if path.exists() else {}
    jobs = [(m, q) for m in models.ALL for q in fr['questions'] if f'{m}|{q["id"]}' not in data]

    def one(job):
        m, q = job
        try:
            text, meta = models.ask(m, fr['steps'][step].replace('{ctx}', fr['ctx'][q['id']]).replace('{question}', q['question']), f'hardb {step} {q["id"]}')
        except Exception as e:
            print('FAIL', m, q['id'], str(e)[:150], flush=True); return
        with lock:
            data[f'{m}|{q["id"]}'] = {'qid': q['id'], 'text': text, 'meta': meta}; path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
        print('answered', step, m, q['id'], flush=True)
    with cf.ThreadPoolExecutor(9) as ex:
        list(ex.map(one, jobs))


def score():
    import math, collections
    fr = json.loads(F.read_text()); qs = {q['id']: q for q in fr['questions']}
    per = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    for step in ('0_control', '1_qloo_location'):
        for k, a in json.loads((OUT/f'answers-hardb-{step}.json').read_text()).items():
            m = k.split('|')[0]; q = qs[a['qid']]
            for n in ladder.names(a['text']):
                r = hard.place(n, q); ov = R.nearest(n, 'h_' + q['city'].lower())
                ok = r['status'] == 'in_radius' or (ov is not None and ov[0] <= 0.5)
                c = per[(m, a['qid'])][step]; c[1] += 1; c[0] += ok
    out = {}
    for m in models.ALL:
        a = b = na = nb = w = t = l = 0
        for (mm, q), v in per.items():
            if mm != m:
                continue
            x, y = v['0_control'], v['1_qloo_location']; a += x[0]; na += x[1]; b += y[0]; nb += y[1]
            sx = x[0]/x[1] if x[1] else 0; sy = y[0]/y[1] if y[1] else 0
            w, t, l = w + (sy > sx), t + (sy == sx), l + (sy < sx)
        out[m] = {'step0': [a, na], 'step1': [b, nb], 'better_same_worse': [w, t, l]}
        print(f"{m:9} {a}/{na} {100*a/max(na,1):3.0f}%  ->  {b}/{nb} {100*b/max(nb,1):3.0f}%   {w}/{t}/{l}")
    (OUT/'hardb-result.json').write_text(json.dumps(out, indent=1))


if __name__ == '__main__':
    {'context': context, 'freeze': freeze, 'answer': lambda: answer(sys.argv[2]), 'score': score}[sys.argv[1]]()
