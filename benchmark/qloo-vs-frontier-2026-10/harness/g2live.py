"""G2 live (29 Oct): lesser-known artists, films and books. Does Qloo's popularity cap help frontier models name REAL
lesser-known works? 6 questions = 2 audiences x (artists, films, books). Step 0 control; step 1 + Qloo results with
filter.popularity.max 0.5 (5 new live calls; audience A artists reuse live call 10 from today).
Ground truth, all outside Qloo: artists -> MusicBrainz exact-name match; films -> Wikidata (described as a film);
books -> Open Library title search. Fame -> English Wikipedia pageviews in the frozen 60-day window (no article counts as
lesser-known). Score per answer: real AND lesser-known (< 30,000 views). 1 request per second per service, cached.
Run: python3 g2live.py context | freeze | answer STEP | score"""
import concurrent.futures as cf, json, re, sys, threading, urllib.parse
from pathlib import Path
import ladder, models, qloo_live as Q, hardb

OUT = Path(__file__).resolve().parent
gt = ladder.gt
AUD = {'A': ('Björk, Radiohead and Little Simz', Q.SEEDS), 'B': ('Ezra Collective, Nubya Garcia and Moses Boyd', hardb.SEEDS_B)}
KINDS = {'artist': 'urn:entity:artist', 'film': 'urn:entity:movie', 'book': 'urn:entity:book'}
F, CTXF = OUT/'FROZEN-G2LIVE.json', OUT/'g2live-qloo-context.json'
WORD = {'artist': 'musicians or bands', 'film': 'films', 'book': 'books'}


def context():
    ctx = json.loads(CTXF.read_text()) if CTXF.exists() else {}
    for a, (_, seeds) in AUD.items():
        for k, urn in KINDS.items():
            key = f'{a}_{k}'
            if key in ctx:
                continue
            if key == 'A_artist':
                ents = json.loads((OUT/'live/10.json').read_text())['response']['results']['entities']; src = 'live call 10 (already made today)'
            else:
                st, b = Q.call('/v2/insights', {'filter.type': urn, 'signal.interests.entities': Q.seed_ids(seeds),
                                                'filter.popularity.max': 0.5, 'take': 25}, f'G2 live {key} pop<=0.5')
                ents = Q.entities(b); src = f'live call {Q.used()}'
            ctx[key] = {'source': src, 'items': [{'name': e['name'], 'popularity': round(e.get('popularity', 0), 3)} for e in ents[:25]]}
            CTXF.write_text(json.dumps(ctx, indent=1, ensure_ascii=False)); print(key, len(ents), 'qloo used', Q.used(), flush=True)


def freeze():
    if F.exists():
        raise SystemExit('already frozen')
    ctx = json.loads(CTXF.read_text()); qs = []
    for a, (names, _) in AUD.items():
        for k in KINDS:
            qs.append({'id': f'g2_{a}_{k}', 'aud': a, 'kind': k,
                       'seed': f'Audience: people whose taste is anchored by {names}.\n\n',
                       'question': f'Which 5 lesser-known {WORD[k]}, not household names, would this audience love?',
                       'ctx': '\n'.join(f"- {i['name']}" for i in ctx[f'{a}_{k}']['items'])})
    base = 'You are advising a small cultural events team. Do not use tools or read files.\n\n'
    frozen = {'at': ladder.now(), 'questions': qs,
              'steps': {'0_control': base + '{seed}' + ladder.FMT + 'Question: {question}',
                        '1_qloo_popcap': base + '{seed}' + 'Qloo results for this audience, filtered to lesser-known entries '
                                         '(Qloo popularity at most 0.5):\n{ctx}\n\n' + ladder.FMT + 'Question: {question}'},
              'lesser_known_views_60d': gt.LESSER_KNOWN}
    body = json.dumps(frozen, indent=1, ensure_ascii=False)
    F.write_text(body); (OUT/'FROZEN-G2LIVE.sha256').write_text(ladder.sha(body)+'\n'); print('frozen', ladder.sha(body))


def answer(step):
    body = F.read_text(); assert ladder.sha(body) == (OUT/'FROZEN-G2LIVE.sha256').read_text().strip()
    fr, path, lock = json.loads(body), OUT/f'answers-g2live-{step}.json', threading.Lock()
    data = json.loads(path.read_text()) if path.exists() else {}
    jobs = [(m, q) for m in models.ALL for q in fr['questions'] if f'{m}|{q["id"]}' not in data]

    def one(job):
        m, q = job
        p = fr['steps'][step].replace('{seed}', q['seed']).replace('{ctx}', q['ctx']).replace('{question}', q['question'])
        try:
            text, meta = models.ask(m, p, f'g2live {step} {q["id"]}')
        except Exception as e:
            print('FAIL', m, q['id'], str(e)[:150], flush=True); return
        with lock:
            data[f'{m}|{q["id"]}'] = {'qid': q['id'], 'text': text, 'meta': meta}; path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
        print('answered', step, m, q['id'], flush=True)
    with cf.ThreadPoolExecutor(9) as ex:
        list(ex.map(one, jobs))


def views_for_title(title):
    if not title:
        return None
    t = urllib.parse.quote(title.replace(' ', '_'), safe='')
    pv = gt.get(f'https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{t}/daily/20260830/20261028', pace=1.0)
    return sum(i['views'] for i in pv['items']) if 'items' in pv else 0


def exists(name, kind):
    if kind == 'artist':
        q = urllib.parse.urlencode({'query': f'artist:"{name}"', 'fmt': 'json', 'limit': 3})
        r = gt.get(f'https://musicbrainz.org/ws/2/artist?{q}', pace=1.1)
        if r.get('unanswered'):
            return None, None
        hit = [a for a in r.get('artists', []) if a.get('score', 0) >= 95 and a['name'].casefold() == name.casefold()]
        return bool(hit), name
    if kind == 'book':
        q = urllib.parse.urlencode({'title': name, 'limit': 3, 'fields': 'title,author_name'})
        r = gt.get(f'https://openlibrary.org/search.json?{q}', pace=1.1)
        if r.get('unanswered'):
            return None, None
        norm = lambda s: re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()
        return any(norm(d.get('title')) == norm(name) for d in r.get('docs', [])), name
    w = gt.check_work(name, 'film')
    return w.get('exists'), w.get('enwiki')


def score():
    fr = json.loads(F.read_text()); qs = {q['id']: q for q in fr['questions']}; res = {}
    rows = []
    for step in ('0_control', '1_qloo_popcap'):
        for k, a in json.loads((OUT/f'answers-g2live-{step}.json').read_text()).items():
            m = k.split('|')[0]; q = qs[a['qid']]
            c = res.setdefault(step, {}).setdefault(m, {'named': 0, 'real': 0, 'real_lesser_known': 0, 'not_found': 0, 'unknown': 0})
            for n in ladder.names(a['text']):
                ex, title = exists(n, q['kind']); c['named'] += 1
                if ex is None:
                    c['unknown'] += 1; continue
                if not ex:
                    c['not_found'] += 1; rows.append({'step': step, 'model': m, 'qid': q['id'], 'name': n, 'found': False}); continue
                c['real'] += 1
                v = views_for_title(title if q['kind'] == 'film' else n)
                lk = v is None or v < gt.LESSER_KNOWN
                c['real_lesser_known'] += lk
                rows.append({'step': step, 'model': m, 'qid': q['id'], 'name': n, 'found': True, 'views_60d': v})
    (OUT/'g2live-score.json').write_text(json.dumps({'per_step': res, 'rows': rows}, indent=1, ensure_ascii=False))
    for m in models.ALL:
        a, b = res['0_control'].get(m, {}), res['1_qloo_popcap'].get(m, {})
        print(f"{m:9} step0 real+lesser {a.get('real_lesser_known')}/{a.get('named')} (not found {a.get('not_found')}) -> "
              f"step1 {b.get('real_lesser_known')}/{b.get('named')} (not found {b.get('not_found')})")


if __name__ == '__main__':
    {'context': context, 'freeze': freeze, 'answer': lambda: answer(sys.argv[2]), 'score': score}[sys.argv[1]]()
