"""The agent must choose a real follow-up from the observation and respect the HTTP cap."""
import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import agent_planner
from qloo_client import BudgetSpent, Live


BODY = {'flow': 'brand', 'experiment': 'popup', 'size': 'neighbourhood',
        'city': 'London', 'picks': ['Björk', 'Radiohead', 'Little Simz']}


def graph(music_score=.85, film_score=.72):
    return {'mode': 'live', 'profile': 'brand:popup', 'http_reads': 7,
            'calls': [{'id': f'L{i:02d}', 'status': 200} for i in range(1, 8)],
            'outlets': [
                {'domain': 'music', 'call': 'L04', 'entity': {'name': 'Returned musician', 'id': 'qloo-music-id', 'affinity': music_score}},
                {'domain': 'film', 'call': 'L05', 'entity': {'name': 'Returned film', 'id': 'qloo-film-id', 'affinity': film_score}},
            ]}


class Followup:
    def __init__(self):
        self.queries = []
        self.http_reads = 1

    def get(self, purpose, path, params):
        self.queries.append((purpose, path, params))
        return {'purpose': purpose, 'status': 200, 'url': '/v2/insights?private=no',
                'response': {'results': {'entities': [{'name': 'Returned bridge', 'entity_id': 'qloo-bridge-id',
                                                       'types': ['urn:entity:movie'], 'query': {'affinity': .74}}]}}}


class AgentPlannerTests(unittest.TestCase):
    def test_next_qloo_query_changes_with_the_live_lead(self):
        for source, seed, target in [(graph(), 'qloo-music-id', 'urn:entity:movie'),
                                     (graph(.65, .9), 'qloo-film-id', 'urn:entity:artist')]:
            tool = Followup()
            result = agent_planner.plan(BODY, first_graph=source, followup_client=tool)
            self.assertEqual(result['mode'], 'live')
            self.assertEqual(result['model_calls'], 0)
            self.assertEqual(result['actual_http_reads'], 8)
            self.assertEqual(result['bridge']['call'], 'A08')
            self.assertEqual(tool.queries[0][2]['signal.interests.entities'], seed)
            self.assertEqual(tool.queries[0][2]['filter.type'], target)

    def test_trace_shows_the_entity_ids_actually_sent(self):
        tool = Followup()
        result = agent_planner.plan(BODY, first_graph=graph(), followup_client=tool)
        sent = tool.queries[0][2]
        observe, choose, verify = result['steps']
        self.assertEqual(observe['entity_id'], 'qloo-music-id')
        self.assertEqual(result['lead']['id'], sent['signal.interests.entities'])
        self.assertEqual(choose['query']['signal.interests.entities'], sent['signal.interests.entities'])
        self.assertEqual(choose['query']['filter.type'], sent['filter.type'])
        self.assertEqual(verify['entity_id'], 'qloo-bridge-id')
        self.assertEqual(result['bridge']['id'], 'qloo-bridge-id')
        self.assertEqual(len(result['reject_if']), 3)
        self.assertIn('Returned bridge', result['reject_if'][0])

    def test_two_coffee_briefs_take_different_next_queries(self):
        coffee = {'flow': 'brand', 'experiment': 'popup', 'size': 'neighbourhood', 'city': 'London'}
        jazz = dict(coffee, picks=['Nina Simone', 'Miles Davis', 'Erykah Badu'])
        cinema = dict(coffee, picks=['Wes Anderson', 'Sofia Coppola', 'Wong Kar-wai'])
        music_led = graph(.88, .61)
        film_led = graph(.58, .93)
        film_led['outlets'][1]['entity']['id'] = 'qloo-other-film-id'
        sent = []
        for brief, source in [(jazz, music_led), (cinema, film_led)]:
            tool = Followup()
            result = agent_planner.plan(brief, first_graph=source, followup_client=tool)
            self.assertEqual(result['picks'], brief['picks'])
            sent.append(tool.queries[0][2])
        self.assertEqual(sent[0]['signal.interests.entities'], 'qloo-music-id')
        self.assertEqual(sent[0]['filter.type'], 'urn:entity:movie')
        self.assertEqual(sent[1]['signal.interests.entities'], 'qloo-other-film-id')
        self.assertEqual(sent[1]['filter.type'], 'urn:entity:artist')
        self.assertNotEqual(sent[0], sent[1])

    def test_fictional_graph_cannot_be_an_agent_result(self):
        bad = graph(); bad['mode'] = 'synthetic'
        with self.assertRaisesRegex(agent_planner.AgentUnavailable, 'live Qloo graph'):
            agent_planner.plan(BODY, first_graph=bad, followup_client=Followup())

    def test_actual_http_reads_are_capped_even_during_retries(self):
        tool = Live('test-only-key', base='http://127.0.0.1:1', max_calls=1, pause=0, max_http_reads=2)
        def rate_limit(*args, **kwargs):
            raise HTTPError('http://127.0.0.1:1/v2/insights', 429, 'rate limited', {}, io.BytesIO(b'{}'))
        with (patch('qloo_client.urllib.request.urlopen', side_effect=rate_limit) as opened,
              patch('qloo_client.time.sleep')):
            with self.assertRaises(BudgetSpent):
                tool.get('probe', '/v2/insights', {'take': 1})
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(tool.http_reads, 2)


if __name__ == '__main__':
    unittest.main()
