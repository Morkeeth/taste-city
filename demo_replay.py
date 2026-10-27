"""Replay private recordings or a fictional public sample; never call Qloo in demo mode."""
import json
from pathlib import Path
import scenario_engine
import taste_city

ROOT = Path(__file__).parent / 'demo-recordings'
DEFAULT_PICKS = ['Björk', 'Radiohead', 'Little Simz']

def scenario(body):
    request = scenario_engine.clean_request(body)
    exact = taste_city.cache_path(sorted(request['picks']), request['city'], ROOT, profile=f"{request['flow']}:{request['experiment']}")
    if exact.exists():
        graph = json.loads(exact.read_text())
        if (sorted(graph.get('picks', [])) != sorted(request['picks']) or graph.get('city') != request['city'] or graph.get('profile') != f"{request['flow']}:{request['experiment']}"):
            raise ValueError('The saved recording does not match this audience and idea.')
        graph['mode'] = 'recorded'
        result = scenario_engine.build(body, graph)
        result['qloo']['demo_shared'] = False
        return result
    if sorted(request['picks']) != sorted(DEFAULT_PICKS) or request['city'] != 'London':
        raise ValueError('Choose the default London tastes to see the recorded demo.')
    path = ROOT / (request['flow'] + '-' + request['experiment'] + '.json')
    path = path if path.exists() else ROOT / 'default-graph.json'
    if not path.exists():
        import sample_demo
        return sample_demo.scenario(body)
    graph = json.loads(path.read_text())
    graph['mode'] = 'recorded'
    result = scenario_engine.build(body, graph)
    result['qloo']['demo_shared'] = graph.get('demo_shared', False)
    result['total_ms'] = 0
    return result

def website(body):
    path = ROOT / 'website.json'
    if not path.exists():
        raise ValueError('The website demo is not recorded yet; try the coffee shop comparison.')
    result = json.loads(path.read_text())
    if body.get('url', '').rstrip('/') != result['page']['url'].rstrip('/') or body.get('city', 'London') != result['city']:
        raise ValueError('Use the default website and London to see the recorded demo.')
    return {**result, 'mode': 'recorded', 'total_ms': 0}
