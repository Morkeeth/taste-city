"""Fetch every named OpenStreetMap feature within 1.5 km of each hard point into overpass-names.json, for resolve.py.
One Overpass query per point, spaced 3 s, retried on 502. Verify the counts differ per point: a failed fetch must not
reuse the previous point's data. Data (c) OpenStreetMap contributors, ODbL.
Run after hard.py freeze: python3 overpass_fetch.py"""
import json, time, urllib.parse, urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent
UA = 'TasteCityResearch/0.1 (+https://github.com/Morkeeth/taste-city) overpass names'
SERVERS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']


def fetch(lat, lon):
    ql = f'[out:json][timeout:60];(nwr(around:1500,{lat},{lon})["name"];);out center tags;'
    for attempt in range(6):
        url = SERVERS[attempt % len(SERVERS)]
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({'data': ql}).encode(), headers={'User-Agent': UA})
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except Exception as e:
            print('retry', url, e); time.sleep(10 * (attempt + 1))
    raise RuntimeError('Overpass did not answer')


def main():
    fr = json.loads((OUT/'FROZEN-HARD.json').read_text())
    out = {}
    for q in fr['questions']:
        els = []
        for e in fetch(q['lat'], q['lon']).get('elements', []):
            lat = e.get('lat') or (e.get('center') or {}).get('lat'); lon = e.get('lon') or (e.get('center') or {}).get('lon')
            if lat is None:
                continue
            t = e.get('tags', {})
            els.append({'name': t.get('name'), 'alt': [t[k] for k in ('alt_name', 'old_name', 'name:en', 'official_name', 'short_name') if k in t],
                        'lat': lat, 'lon': lon, 'kind': t.get('amenity') or t.get('shop') or t.get('leisure') or t.get('tourism') or ''})
        out[q['id']] = els; print(q['id'], len(els)); time.sleep(3)
    (OUT/'overpass-names.json').write_text(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
