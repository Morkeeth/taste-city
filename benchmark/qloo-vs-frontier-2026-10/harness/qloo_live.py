"""Live Qloo client for the 29 Oct research lane. Oscar's verdict qloo-live-calls-29oct = ALLOW 40 (13:35:52).
Hard cap: refuses call 41. Every call (status, params, time) is appended to live-calls.jsonl; responses go to live/<n>.json.
The key is read from the QLOO_API_KEY environment variable and never printed or written. 429 -> exponential back-off, still one call.
Responses contain Qloo entity IDs: keep outside public repos."""
import json, os, time, urllib.parse, urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent
LOG, RAW = OUT/'live-calls.jsonl', OUT/'live'
CAP = 40
SEEDS = {'Björk': None, 'Radiohead': None, 'Little Simz': None}   # Qloo IDs are resolved by name at run time (resolve_seeds)


def _cfg():
    return os.environ['QLOO_API_KEY'], os.environ.get('QLOO_API_URL', 'https://hackathon.api.qloo.com')


def resolve_seeds(names):
    """Name -> Qloo entity ID via /search (one call per name, counted). Not stored in git."""
    out = {}
    for n in names:
        st, b = call('/search', {'query': n, 'types': 'urn:entity:artist', 'take': 1}, f'resolve {n}')
        out[n] = ((b or {}).get('results') or [{}])[0].get('entity_id')
    return out


def used():
    return sum(1 for _ in LOG.open()) if LOG.exists() else 0


def call(path, params, purpose):
    n = used() + 1
    if n > CAP:
        raise RuntimeError(f'Qloo cap {CAP} reached; ask the orchestrator to raise it')
    key, base = _cfg()
    url = base.rstrip('/') + path + '?' + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={'X-Api-Key': key, 'Accept': 'application/json'})
    status, body = None, None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                status, body = r.status, json.loads(r.read().decode())
            break
        except urllib.error.HTTPError as e:
            status = e.code
            try:
                body = json.loads(e.read().decode())
            except Exception:
                body = {'error': str(e)}
            if e.code == 429:
                time.sleep(2 ** attempt * 3); continue
            break
    RAW.mkdir(exist_ok=True)
    (RAW/f'{n:02d}.json').write_text(json.dumps({'n': n, 'purpose': purpose, 'path': path, 'params': params, 'status': status,
                                                 'response': body}, ensure_ascii=False))
    with LOG.open('a') as f:
        f.write(json.dumps({'n': n, 'at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'purpose': purpose, 'path': path,
                            'params': params, 'status': status}, ensure_ascii=False) + '\n')
    return status, body


def entities(body):
    return (((body or {}).get('results') or {}).get('entities') or []) if isinstance(body, dict) else []


def seed_ids(seeds):
    """Comma-joined Qloo IDs for a {name: id-or-None} map, resolving any missing ID by name."""
    if not all(seeds.values()):
        seeds.update(resolve_seeds([n for n, i in seeds.items() if not i]))
    return ','.join(seeds.values())
