"""Real evidence transfer rules: no fake radius or audience can enter a core plan."""
import copy
import json
import unittest
from unittest.mock import patch
import core_context
import sample_demo
import taste_city
import scenario_engine

PICKS=list(sample_demo.DEFAULT_PICKS)
ENV={'QLOO_API_KEY':'test-only-context-key'}

def graph():
    g=sample_demo.local_discovery({'picks':PICKS,'city':'London'})
    g['calls']=[{'id':'L09','url':'https://example.invalid/v2/insights?filter.location=POINT(-0.12%2051.5)&filter.location.radius=1000'}]
    g['mode']='live';g['recorded_at']='2026-10-29T17:00:00Z'
    g['local_area']={'label':'Fixture centre, London','source':'fixture','radius_m':1000,'popularity_cap':None}
    g['nearby_places']=[{'id':'actual-test-place','name':'Fixture local venue','distance_m':500,'call':'L09','why':'Fixture evidence','genre':'restaurant:cafe'}]
    return g

class ContextRules(unittest.TestCase):
    def request(self,**kw):
        return {'planning_token':core_context.issue(graph(),ENV,now=100),'picks':PICKS,'selected_place_ids':['actual-test-place'],**kw}
    def test_signed_roundtrip_and_shared_scenario_preserve_selected_local_evidence(self):
        context=core_context.for_request(self.request(),ENV,now=200)
        request={'flow':'brand','experiment':'popup','picks':PICKS,'size':'neighbourhood'}
        shaped=core_context.graph_for(context,request);result=scenario_engine.build(request,shaped)
        self.assertEqual(context['places'][0]['id'],'actual-test-place');self.assertEqual(shaped['planning_profile'],'brand:popup');self.assertIsNone(shaped['profile']);self.assertTrue(shaped['shared_local_graph']);self.assertEqual(result['qloo']['anchors'],graph()['anchors'])
        public=core_context.public(context);self.assertNotIn('graph',public);self.assertEqual(public['area']['radius_m'],1000)
    def test_forged_payload_and_wrong_server_key_fail(self):
        token=self.request()['planning_token'];encoded,sig=token.split('.')
        with self.assertRaises(core_context.InvalidLocalContext):core_context.read(encoded[:-1]+'A.'+sig,ENV,now=200)
        with self.assertRaises(core_context.InvalidLocalContext):core_context.read(token,{'QLOO_API_KEY':'wrong-key'},now=200)
    def test_expiry_and_future_issue_are_rejected(self):
        token=self.request()['planning_token']
        for now in [99,3700,9999]:
            with self.assertRaises(core_context.InvalidLocalContext):core_context.read(token,ENV,now)
    def test_selection_and_changed_audience_fail(self):
        for ids in [[],['outside'],['actual-test-place']*2,['a','b','c','d']]:
            with self.assertRaises(core_context.InvalidLocalContext):core_context.for_request(self.request(selected_place_ids=ids),ENV,now=200)
        with self.assertRaises(core_context.InvalidLocalContext):core_context.for_request(self.request(picks=['A','B','C']),ENV,now=200)
    def test_invalid_and_oversized_tokens_are_bounded(self):
        for token in [None,'bad','a'*40001,[],'.']:
            with self.assertRaises(core_context.InvalidLocalContext):core_context.read(token,ENV,now=200)
    def test_sample_cannot_claim_real_places_and_never_queries_provider(self):
        with patch.object(taste_city,'_live',side_effect=AssertionError('provider called')):
            context=core_context.for_request({'demo':True,'picks':PICKS,'selected_place_ids':['fictional:local:cafe']})
        self.assertEqual(context['mode'],'synthetic');self.assertIn('Fictional',context['notice']);self.assertTrue(context['places'][0]['id'].startswith('fictional:'))
        with self.assertRaises(core_context.InvalidLocalContext):core_context.for_request({'demo':True,'picks':PICKS,'selected_place_ids':['actual-test-place']})
