"""Combine audience A (10 questions, resolved-hard-*.json) and audience B (5 questions, answers-hardb-*.json) into one
per-model result: share of named places verified within 500 m, per-question better/same/worse, two-sided sign test.
A place counts when Nominatim (hard.place) or the Overpass match (resolve.nearest) puts it within 0.5 km.
Run after hard.py score, resolve.py and the hardb answers: python3 combined.py"""
import collections, json, math
from pathlib import Path
import hard, ladder, models, resolve as R

OUT = Path(__file__).resolve().parent


def main():
    per = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    for s in ('0_control', '1_qloo_location'):
        for r in json.loads((OUT/f'resolved-hard-{s}.json').read_text())['rows']:
            c = per[(r['model'], r['qid'])][s]; c[1] += 1; c[0] += r['final'] == 'in_500m'
    fb = json.loads((OUT/'FROZEN-HARD-B.json').read_text()); qs = {q['id']: q for q in fb['questions']}
    for s in ('0_control', '1_qloo_location'):
        for k, a in json.loads((OUT/f'answers-hardb-{s}.json').read_text()).items():
            m = k.split('|')[0]; q = qs[a['qid']]
            for n in ladder.names(a['text']):
                r = hard.place(n, q); ov = R.nearest(n, 'h_' + q['city'].lower())
                c = per[(m, a['qid'])][s]; c[1] += 1; c[0] += (r['status'] == 'in_radius' or (ov is not None and ov[0] <= 0.5))
    out = {}
    for m in sorted({k[0] for k in per}):
        a = b = na = nb = w = t = l = nq = 0
        for (mm, q), v in per.items():
            if mm != m:
                continue
            nq += 1
            x, y = v['0_control'], v['1_qloo_location']; a += x[0]; na += x[1]; b += y[0]; nb += y[1]
            sx = x[0]/x[1] if x[1] else 0; sy = y[0]/y[1] if y[1] else 0
            w += sy > sx; t += sy == sx; l += sy < sx
        n = w + l
        p = min(1, 2*sum(math.comb(n, k) for k in range(max(w, l), n+1))/2**n) if n else 1
        out[m] = {'questions': nq, 'step0': [a, na], 'step1': [b, nb], 'better_same_worse': [w, t, l], 'sign_p_two_sided': round(p, 4),
                  'route': 'venice' if m in models.VENICE else 'openrouter' if m in models.API else 'cursor' if m == 'composer' else 'subscription'}
        print(f"{m:9} {a:2}/{na:2} {100*a/max(na,1):3.0f}% -> {b:2}/{nb:2} {100*b/max(nb,1):3.0f}%  {w}/{t}/{l}  p={p:.4f}  q={nq}")
    (OUT/'hard-combined-result.json').write_text(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
