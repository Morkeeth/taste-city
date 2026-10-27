import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import demo_replay

class ReplayTests(unittest.TestCase):
    def test_clean_checkout_runs_fictional_example_without_provider_or_recording(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(demo_replay, 'ROOT', Path(directory)):
            body = dict(flow='brand', size='neighbourhood', experiment='popup', city='London', picks=demo_replay.DEFAULT_PICKS)
            with patch('taste_city._live', side_effect=AssertionError('provider called')):
                result = demo_replay.scenario(body)
            self.assertEqual(result['qloo']['mode'], 'synthetic')
            self.assertEqual(result['qloo']['calls'], [])
            self.assertIn('No Qloo request', result['qloo']['source_notice'])
            self.assertTrue(all(row['entity']['id'].startswith('fictional:') for row in result['qloo']['outlets']))

    @unittest.skipUnless((demo_replay.ROOT / "default-graph.json").exists(), "Local Qloo recording is not present in this checkout")
    def test_recorded_defaults_produce_brand_and_festival_results_without_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'default-graph.json').write_bytes((demo_replay.ROOT / 'default-graph.json').read_bytes())
            with patch.object(demo_replay, 'ROOT', root):
                for flow, size, experiments in [('brand','neighbourhood',['popup','flavour']), ('festival','local',['lineup','sponsor'])]:
                    for experiment in experiments:
                        with patch('taste_city._live', side_effect=AssertionError('provider called')):
                            result = demo_replay.scenario(dict(flow=flow,size=size,experiment=experiment,city='London',picks=demo_replay.DEFAULT_PICKS))
                        self.assertTrue(result['archetypes'])
                        self.assertTrue(result['qloo']['outlets'])
                        self.assertEqual(result['qloo']['mode'], 'recorded')
                        self.assertTrue(result['qloo']['demo_shared'])
                        self.assertEqual(result['qloo']['outlets'][0]['entity']['name'], 'Yves Tumor')

    def test_exact_profile_recording_accepts_same_picks_in_different_order(self):
        import taste_city
        from test_scenario_engine import graph
        g = graph()
        g.update(city='London', profile='festival:lineup', picks=['Studio Ghibli','Radiohead','Little Simz'])
        with tempfile.TemporaryDirectory() as directory, patch.object(demo_replay, 'ROOT', Path(directory)):
            path = taste_city.cache_path(sorted(g['picks']), 'London', Path(directory), profile=g['profile'])
            path.write_text(json.dumps(g))
            body = dict(flow='festival', size='local', experiment='lineup', city='London', picks=list(reversed(g['picks'])))
            with patch('taste_city._live', side_effect=AssertionError('provider called')):
                result = demo_replay.scenario(body)
            self.assertFalse(result['qloo']['demo_shared'])
            self.assertEqual(result['qloo']['mode'], 'recorded')
            g['profile'] = 'festival:sponsor'
            path.write_text(json.dumps(g))
            with self.assertRaisesRegex(ValueError, 'does not match'):
                demo_replay.scenario(body)

    def test_unrecorded_tastes_are_not_silently_replaced(self):
        with self.assertRaises(ValueError):
            demo_replay.scenario(dict(flow='brand',size='neighbourhood',experiment='popup',city='London',picks=['A','B','C']))

    def test_missing_website_recording_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(demo_replay, 'ROOT', Path(directory)):
            with self.assertRaisesRegex(ValueError, 'not recorded yet'):
                demo_replay.website({'url':'https://www.patagonia.com/','city':'London'})

    def test_deploy_stops_when_production_key_is_absent(self):
        source = Path(__file__).parent / 'deploy.sh'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'deploy.sh').write_bytes(source.read_bytes())
            (root / '.vercel').mkdir()
            (root / '.vercel/project.json').write_text(json.dumps({
                'projectName':'taste-city',
                'projectId':'prj_9TBxqKheaq77YSKxlI9ssKpFWwUq',
                'orgId':'team_pyn313moYAPrdTjKeJJeCkoL',
            }))
            stub = root / 'vercel'
            stub.write_text('#!/bin/sh\nif [ "$1" = env ]; then echo "OTHER_KEY Encrypted Production"; exit 0; fi\necho unexpected-deploy >&2; exit 99\n')
            stub.chmod(0o755)
            result = subprocess.run(['sh', str(root / 'deploy.sh')], env={**os.environ,'PATH':str(root)+os.pathsep+os.environ['PATH']}, capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('QLOO_API_KEY is missing',result.stderr)
            self.assertNotIn('unexpected-deploy', result.stderr)
