"""Oscar-only recording action. Makes live Qloo and public website requests."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import brand_profile
import taste_city
from scenario_engine import FLOW_CONFIG


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record-live', action='store_true', help='Authorize live recording with your Qloo key')
    args = parser.parse_args()
    if not args.record_live:
        parser.error('Recording is outward; explicitly pass --record-live to run it.')
    if not os.environ.get('QLOO_API_KEY') or os.environ.get('QLOO_TASTE_OFFLINE') == '1':
        parser.error('Set QLOO_API_KEY and disable QLOO_TASTE_OFFLINE before recording.')
    destination = Path(__file__).parent / 'demo-recordings'
    # Gather everything first; a failed request does not replace the existing set.
    recordings = {}
    with tempfile.TemporaryDirectory() as cache:
        for flow, config in FLOW_CONFIG.items():
            for experiment in config['experiments']:
                name = f'{flow}-{experiment}'
                result = taste_city.build(['Björk', 'Radiohead', 'Little Simz'], 'London', cache_root=cache, prefer_cache=False, profile=f'{flow}:{experiment}')
                recordings[name] = {**result, 'mode': 'recorded'}
        recordings['website'] = {**brand_profile.build('https://www.patagonia.com/', 'London', cache_root=cache, prefer_cache=False), 'mode': 'recorded'}
    destination.mkdir(exist_ok=True)
    for name, result in recordings.items():
        (destination / f'{name}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('Real demo recordings saved locally. Keep them out of git and deploy from this folder.')

if __name__ == '__main__':
    main()
