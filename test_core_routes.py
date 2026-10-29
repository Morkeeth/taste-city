"""Exercise the hosted handlers over HTTP, binding plans to prior local evidence."""
import json
import os
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import match_app
import core_context
from test_core_context import graph, ENV, PICKS

class CoreRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),match_app.H)
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.url=f'http://127.0.0.1:{cls.server.server_address[1]}'
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
    def body(self):
        return {'local_core':True,'planning_token':core_context.issue(graph(),ENV),'selected_place_ids':['actual-test-place'],'picks':PICKS,'flow':'brand','experiment':'popup','size':'neighbourhood','city':'London'}
    def post(self,path,body):
        req=urllib.request.Request(self.url+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req) as res:return res.status,json.load(res)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    def test_scenario_uses_signed_local_graph_without_citywide_provider_query(self):
        with patch.dict(os.environ,ENV),patch('taste_city.build',side_effect=AssertionError('unbounded requery')):
            status,result=self.post('/api/scenario',self.body())
        self.assertEqual(status,200);self.assertEqual(result['local_context']['places'][0]['id'],'actual-test-place');self.assertTrue(result['qloo']['shared_local_graph']);self.assertEqual(result['qloo_ms'],0)
    def test_changed_audience_or_outside_place_rejected_before_provider(self):
        for update in [{'picks':['A','B','C']},{'selected_place_ids':['outside']},{'planning_token':'forged'}]:
            with patch.dict(os.environ,ENV),patch('taste_city.build',side_effect=AssertionError('provider')):
                status,result=self.post('/api/scenario',self.body()|update)
            self.assertEqual(status,400)
    def test_agent_receives_exact_graph_and_selected_venue(self):
        fake={'mode':'live','next_action':'Check availability.','lead':{'id':'culture'},'steps':[]}
        with patch.dict(os.environ,ENV),patch('agent_planner.plan',return_value=fake.copy()) as run:
            status,result=self.post('/api/agent-plan',self.body())
        self.assertEqual(status,200);self.assertEqual(run.call_args.kwargs['first_graph']['planning_profile'],'brand:popup');self.assertIn('Fixture local venue',result['next_action']);self.assertEqual(result['local_context']['area']['radius_m'],1000)
    def test_brand_profile_cannot_run_with_forged_context(self):
        with patch.dict(os.environ,ENV),patch('brand_profile.build',side_effect=AssertionError('provider')):
            status,result=self.post('/api/brand-taste',self.body()|{'planning_token':'forged','url':'https://example.com'})
        self.assertEqual(status,400)
    def test_website_profile_uses_trusted_geometry_not_raw_address_query(self):
        with patch.dict(os.environ,ENV),patch('brand_profile.build',return_value={'mode':'live'}) as run:
            status,result=self.post('/api/brand-taste',self.body()|{'url':'https://example.com'})
        self.assertEqual(status,200)
        self.assertEqual(run.call_args.kwargs['local_filter'],{'filter.location':'POINT(-0.12 51.5)','filter.location.radius':1000})
        self.assertEqual(result['local_context']['places'][0]['id'],'actual-test-place')
    def test_fictional_core_plan_stays_synthetic(self):
        with patch('taste_city.build',side_effect=AssertionError('provider')):
            status,result=self.post('/api/scenario',self.body()|{'demo':True,'planning_token':None,'selected_place_ids':['fictional:local:cafe']})
        self.assertEqual(status,200);self.assertEqual(result['local_context']['mode'],'synthetic');self.assertEqual(result['qloo']['mode'],'synthetic')
