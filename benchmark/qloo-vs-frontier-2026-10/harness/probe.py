"""Phase A knowledge probe (29 Oct): do frontier models know Qloo's long tail, and do they invent?
Places: 20 lesser-known London places from live call 11 (Qloo popularity <= 0.6) + 5 invented decoys (not in OSM London,
checked 29 Oct). Task: give the postcode district or UNKNOWN. Truth: postcode district in Qloo's address.
Artists: 20 lesser-known artists from live call 10 (popularity <= 0.5) + 5 invented decoys (no MusicBrainz match, checked
29 Oct). Task: REAL with one genre word, or UNKNOWN. A decoy called REAL, or a place decoy given a district, is an invention.
One call per model per list. Run: python3 probe.py freeze | run [models] | score"""
import concurrent.futures as cf, json, random, re, sys, threading
from pathlib import Path
import ladder, models

OUT = Path(__file__).resolve().parent
FAKE_P = ["The Halcyon Listening Room", "Marlowe & Finch Coffee House", "Grey Heron Records", "Kestrel Lane Cinema Club", "Saltbox Vinyl Bar"]
FAKE_A = ["Velvet Marrow", "Kalto Ramires", "Juniper Static", "Oona & The Glass Tides", "Mireille Okafor-Lund"]


def freeze():
    f = OUT/'FROZEN-PROBE.json'
    if f.exists():
        raise SystemExit('already frozen')
    places = []
    for e in json.loads((OUT/'live/11.json').read_text())['response']['results']['entities']:
        m = re.search(r'\b([A-Z]{1,2}\d{1,2}[A-Z]?)\s?\d[A-Z]{2}\b', (e.get('properties') or {}).get('address') or '')
        if m and len(places) < 20:
            places.append({'name': e['name'], 'truth': m.group(1), 'popularity': round(e['popularity'], 3), 'real': True})
    artists = [{'name': e['name'], 'popularity': round(e['popularity'], 3), 'real': True,
                'qloo_tags': [t['name'] for t in (e.get('tags') or []) if t.get('name')][:3]}
               for e in json.loads((OUT/'live/10.json').read_text())['response']['results']['entities'][:20]]
    places += [{'name': n, 'truth': None, 'real': False} for n in FAKE_P]
    artists += [{'name': n, 'real': False} for n in FAKE_A]
    rng = random.Random(29102026); rng.shuffle(places); rng.shuffle(artists)
    pl = '\n'.join(f'{i+1}. {p["name"]}' for i, p in enumerate(places))
    al = '\n'.join(f'{i+1}. {a["name"]}' for i, a in enumerate(artists))
    frozen = {'at': ladder.now(), 'places': places, 'artists': artists,
              'prompt_places': 'Do not use tools or read files. For each London place below, give its London postcode district '
                               '(for example SE15 or WC2N) if you know it, or UNKNOWN if you do not recognise the place. Do not guess. '
                               'Return ONLY a JSON object mapping the list number to the district or "UNKNOWN".\n\n' + pl,
              'prompt_artists': 'Do not use tools or read files. For each musician or band below, answer REAL plus one genre word if '
                                'you recognise them, or UNKNOWN if you do not. Do not guess. Return ONLY a JSON object mapping the list '
                                'number to a string like "REAL: shoegaze" or "UNKNOWN".\n\n' + al}
    body = json.dumps(frozen, indent=1, ensure_ascii=False)
    f.write_text(body); (OUT/'FROZEN-PROBE.sha256').write_text(ladder.sha(body)+'\n'); print('frozen', ladder.sha(body))


def run(who):
    body = (OUT/'FROZEN-PROBE.json').read_text(); assert ladder.sha(body) == (OUT/'FROZEN-PROBE.sha256').read_text().strip()
    fr, path, lock = json.loads(body), OUT/'probe-answers.json', threading.Lock()
    data = json.loads(path.read_text()) if path.exists() else {}
    jobs = [(m, k) for m in who for k in ('places', 'artists') if f'{m}|{k}' not in data]

    def one(job):
        m, k = job
        try:
            text, meta = models.ask(m, fr['prompt_' + k], f'probe {k}')
        except Exception as e:
            print('FAIL', m, k, str(e)[:150], flush=True); return
        with lock:
            data[f'{m}|{k}'] = {'text': text, 'meta': meta}; path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
        print('probed', m, k, flush=True)
    with cf.ThreadPoolExecutor(6) as ex:
        list(ex.map(one, jobs))


def parse(text):
    try:
        return {str(k): str(v) for k, v in json.loads(text[text.index('{'):text.rindex('}')+1]).items()}
    except Exception:
        return None


def score():
    fr = json.loads((OUT/'FROZEN-PROBE.json').read_text()); ans = json.loads((OUT/'probe-answers.json').read_text())
    res = {}
    for key, a in sorted(ans.items()):
        m, k = key.split('|'); got = parse(a['text']); c = res.setdefault(m, {})
        if got is None:
            c[k] = {'unparsed': True}; continue
        items = fr[k]; s = {'real_n': 0, 'real_known_correct': 0, 'real_known_wrong': 0, 'real_unknown': 0,
                             'decoy_n': 0, 'decoy_invented': 0, 'decoy_unknown': 0, 'wrong_examples': [], 'invented_examples': []}
        for i, it in enumerate(items, 1):
            v = got.get(str(i), 'UNKNOWN').strip()
            unk = v.upper().startswith('UNKNOWN') or not v
            if it['real']:
                s['real_n'] += 1
                if unk:
                    s['real_unknown'] += 1
                elif k == 'places':
                    ok = re.sub(r'\s.*', '', v.upper()) == it['truth']
                    s['real_known_correct' if ok else 'real_known_wrong'] += 1
                    if not ok: s['wrong_examples'].append(f"{it['name']}: said {v}, Qloo {it['truth']}")
                else:
                    s['real_known_correct'] += 1     # recognised; genre recorded, not auto-scored
            else:
                s['decoy_n'] += 1
                if unk: s['decoy_unknown'] += 1
                else: s['decoy_invented'] += 1; s['invented_examples'].append(f"{it['name']}: {v}")
        c[k] = s
    (OUT/'probe-score.json').write_text(json.dumps(res, indent=1, ensure_ascii=False))
    for m, c in res.items():
        p, a = c.get('places', {}), c.get('artists', {})
        print(f"{m:9} places: correct {p.get('real_known_correct')}/{p.get('real_n')} wrong {p.get('real_known_wrong')} unknown {p.get('real_unknown')} | decoys invented {p.get('decoy_invented')}/{p.get('decoy_n')}"
              f" || artists: recognised {a.get('real_known_correct')}/{a.get('real_n')} | decoys invented {a.get('decoy_invented')}/{a.get('decoy_n')}")


if __name__ == '__main__':
    {'freeze': lambda: freeze(), 'run': lambda: run(sys.argv[2:] or models.ALL), 'score': lambda: score()}[sys.argv[1]]()
