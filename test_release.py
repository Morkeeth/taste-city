"""Hosting contracts for routes and writable serverless caches."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

class ReleaseTests(unittest.TestCase):
    def test_brand_route_resolves_to_existing_function(self):
        root = Path(__file__).parent
        config = json.loads((root / 'vercel.json').read_text())
        route = next(r for r in config['rewrites'] if r['source'] == '/api/brand-taste')
        self.assertTrue((root / (route['destination'].lstrip('/') + '.py')).is_file())
        agent = next(r for r in config['rewrites'] if r['source'] == '/api/agent-plan')
        self.assertTrue((root / (agent['destination'].lstrip('/') + '.py')).is_file())

    def test_serverless_cache_can_record_without_application_writes(self):
        code = '''
import tempfile
from pathlib import Path
import taste_city, brand_profile
for module in (taste_city, brand_profile):
    assert module.CACHE.is_relative_to(Path('/tmp')), module.CACHE
    with tempfile.TemporaryDirectory(dir=module.CACHE.parent) as directory:
        target = Path(directory) / 'result.json'
        module._record(target, {'outlets': [{'name': 'synthetic'}]})
        assert target.is_file()
'''
        subprocess.run([sys.executable, '-c', code], env={**os.environ, 'VERCEL': '1'}, check=True)

    def test_static_build_contains_only_browser_assets(self):
        import build_static
        build_static.build()
        root = Path(__file__).parent
        config = json.loads((root / 'vercel.json').read_text())
        output = root / config['outputDirectory']
        self.assertEqual((output / 'village.html').read_bytes(), (root / 'village.html').read_bytes())
        self.assertTrue((output / 'vendor/three.module.min.js').is_file())
        self.assertFalse(list(output.rglob('*.py')))
        self.assertFalse((output / 'cache').exists())
