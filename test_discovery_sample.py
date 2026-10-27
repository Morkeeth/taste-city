"""Keep the public sample honest across the consumer result boundary."""
import unittest
from unittest.mock import patch
import sample_demo
import taste_city

class DiscoverySample(unittest.TestCase):
    def test_consumer_sample_has_every_outlet_without_provider_provenance(self):
        with patch.object(taste_city, '_live', side_effect=AssertionError('demo called provider')):
            result = sample_demo.discovery({'picks': list(sample_demo.DEFAULT_PICKS), 'city': 'London'})
        self.assertEqual(result['mode'], 'synthetic')
        self.assertEqual({r['id'] for r in result['outlets']}, {r[0] for r in taste_city.OUTLETS})
        self.assertEqual(result['calls'], [])
        self.assertTrue(all(r['entity']['id'].startswith('fictional:') for r in result['outlets']))
    def test_sample_does_not_claim_to_match_uncomputed_tastes_or_city(self):
        for body in ({'picks':['A','B','C'], 'city':'London'}, {'picks':list(sample_demo.DEFAULT_PICKS), 'city':'Paris'}):
            with self.assertRaises(ValueError):
                sample_demo.discovery(body)
