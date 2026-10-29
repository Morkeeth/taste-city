"""Second pass for the HARD G1 scores: every named place is matched against all OpenStreetMap features with a name within
1.5 km of the question point (one Overpass query per point, overpass-names.json). Fuzzy name match (accents, case,
punctuation, leading articles, containment, token overlap); the nearest match decides the distance. A name counts as in
range if Nominatim OR Overpass puts it within 0.5 km. A name in neither is reported as "not in OSM within 1.5 km", which
is absence of a record, not proof of invention. For step 1, such names are also checked against the Qloo list given in
the prompt (Qloo's own address and coordinates).
Run: python3 resolve.py"""
import json, re, unicodedata
from pathlib import Path
import ladder

OUT = Path(__file__).resolve().parent
OV = json.loads((OUT/'overpass-names.json').read_text())
FR = json.loads((OUT/'FROZEN-HARD.json').read_text())
QS = {q['id']: q for q in FR['questions']}
CTX = json.loads((OUT/'hard-qloo-context.json').read_text())
ART = r'^(the|le|la|les|l|el|los|las|de|het|der|die|o|a|os|as)\s+'


def norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'[^a-z0-9 ]+', ' ', s); s = re.sub(r'\s+', ' ', s).strip()
    return re.sub(ART, '', s)


def match(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    if a == b or (min(len(a), len(b)) >= 5 and (a in b or b in a)):
        return True
    ta, tb = set(a.split()), set(b.split())
    return len(ta & tb) / max(1, len(ta | tb)) >= 0.6


def nearest(name, qid):
    q = QS[qid]; best = None
    for e in OV[qid]:
        if any(match(name, n) for n in [e['name']] + e['alt']):
            d = ladder.km((q['lat'], q['lon']), (e['lat'], e['lon']))
            if best is None or d < best[0]:
                best = (d, e['name'])
    return best


def qloo_entry(name, qid):
    city = QS[qid]['city']
    for r in CTX[city]['within_500m']:
        if match(name, r['name']):
            return r
    return None


summary = {}
for step in ('0_control', '1_qloo_location'):
    sc = json.loads((OUT/f'score-hard-{step}.json').read_text())
    res = {}
    for r in sc['rows']:
        m = r['model']; c = res.setdefault(m, {'named': 0, 'in_500m': 0, 'out_of_range': 0, 'not_in_osm_1500m': 0,
                                                'not_in_osm_but_in_qloo_list': 0, 'not_in_osm_examples': []})
        c['named'] += 1
        ov = nearest(r['name'], r['qid'])
        nom_in = r.get('status') == 'in_radius'
        if nom_in or (ov and ov[0] <= 0.5):
            r['final'] = 'in_500m'; c['in_500m'] += 1
        elif ov or r.get('status') == 'exists_out_of_radius':
            r['final'] = 'out_of_range'; c['out_of_range'] += 1
        else:
            qe = qloo_entry(r['name'], r['qid']) if step == '1_qloo_location' else None
            if qe:
                r['final'] = 'qloo_listed_not_in_osm'; c['not_in_osm_but_in_qloo_list'] += 1
            else:
                r['final'] = 'not_in_osm_1500m'; c['not_in_osm_1500m'] += 1
                if len(c['not_in_osm_examples']) < 8:
                    c['not_in_osm_examples'].append(f"{r['qid']}: {r['name']}")
        r['overpass'] = {'km': round(ov[0], 2), 'osm_name': ov[1]} if ov else None
    (OUT/f'resolved-hard-{step}.json').write_text(json.dumps({'per_model': res, 'rows': sc['rows']}, indent=1, ensure_ascii=False))
    summary[step] = res

print('model     | step 0: in 500 m / named, out, not in OSM | step 1: in 500 m / named, out, Qloo-listed not in OSM, not in OSM')
for m in sorted(summary['0_control']):
    a, b = summary['0_control'][m], summary['1_qloo_location'].get(m, {})
    print(f"{m:9} | {a['in_500m']:2}/{a['named']:2}  {a['out_of_range']:2}  {a['not_in_osm_1500m']:2} | "
          f"{b.get('in_500m', 0):2}/{b.get('named', 0):2}  {b.get('out_of_range', 0):2}  {b.get('not_in_osm_but_in_qloo_list', 0):2}  {b.get('not_in_osm_1500m', 0):2}")
(OUT/'resolved-hard-summary.json').write_text(json.dumps(summary, indent=1, ensure_ascii=False))
