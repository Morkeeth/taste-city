"""Exercise the actual Qloo wire parameters, radius rejection and exact fallback."""
import json
import tempfile
import unittest
from unittest.mock import patch
import taste_city
import local_places
import test_taste_city as fixture
FakeQloo, entity = fixture.FakeQloo, fixture.entity

AREA = {'lat': 51.5, 'lon': -0.12, 'label': 'Test address, London', 'source': 'fixture geocoder'}

def place(eid, lon=-0.12, popularity=0.2):
    return entity(eid, eid, 'place', 'restaurant:cafe') | {'location': {'lat':51.5,'lon':lon}, 'popularity':popularity}

class LocalDiscovery(unittest.TestCase):
    setUpClass = fixture.TasteCity.__dict__['setUpClass']
    tearDownClass = fixture.TasteCity.__dict__['tearDownClass']
    setUp = fixture.TasteCity.setUp
    tearDown = fixture.TasteCity.tearDown

class LocalWire(LocalDiscovery):
    def run_local(self, **kwargs):
        with patch('taste_city.resolve_area',return_value=AREA):
            return taste_city.build(['Björk','Radiohead','Little Simz'],city='Test address, London',env={'QLOO_API_KEY':'mock-key','QLOO_BASE':self.base},cache_root=self.cache,local=True,**kwargs)
    def test_real_wire_bounds_and_provenance(self):
        with patch.object(FakeQloo,'food_entities',[place('near'),place('outside',-0.16),place('missing') | {'location':{}}]):
            result=self.run_local(radius=500)
        query=next(q for path,q,key in FakeQloo.seen if q.get('filter.type')=='urn:entity:place')
        self.assertEqual(query['filter.location'],'POINT(-0.12 51.5)');self.assertEqual(query['filter.location.radius'],'500');self.assertEqual(query['filter.popularity.max'],'0.5');self.assertNotIn('filter.location.query',query)
        self.assertEqual([p['id'] for p in result['nearby_places']],['near']);self.assertEqual(result['nearby_places'][0]['distance_m'],0);self.assertEqual(result['local_area']['radius_m'],500)
        food=next(x for x in result['outlets'] if x['domain']=='food');self.assertEqual(food['entity']['id'],'near');self.assertEqual(food['entity']['distance_m'],0)
    def test_out_of_radius_never_returned(self):
        with patch.object(FakeQloo,'food_entities',[place('outside',-0.16)]),self.assertRaises(taste_city.QlooUnavailable):self.run_local(radius=500)
    def test_popularity_optout_and_cache_separation(self):
        with patch.object(FakeQloo,'food_entities',[place('near')]):self.run_local(radius=500,discovery=True)
        with patch.object(FakeQloo,'food_entities',[place('all-popularity')]):result=self.run_local(radius=1500,discovery=False)
        query=[q for path,q,key in FakeQloo.seen if q.get('filter.type')=='urn:entity:place'][-1];self.assertNotIn('filter.popularity.max',query);self.assertEqual(result['nearby_places'][0]['id'],'all-popularity');self.assertEqual(len(list(self.cache.glob('*.json'))),2)
    def test_bad_radius_fails_before_network(self):
        for radius in [499,1501,True,None,'nan',500.5]:
            with self.assertRaises(ValueError):self.run_local(radius=radius)
        self.assertEqual(FakeQloo.seen,[])
    def test_unresolved_address_fails_without_qloo(self):
        with patch('taste_city.resolve_area',side_effect=local_places.LocationInvalid('unresolved')),self.assertRaises(ValueError):
            taste_city.build(['Björk','Radiohead','Little Simz'],city='missing',env={'QLOO_API_KEY':'mock-key','QLOO_BASE':self.base},cache_root=self.cache,local=True)
        self.assertEqual(FakeQloo.seen,[])
    def test_same_location_record_only(self):
        with patch.object(FakeQloo,'food_entities',[place('near')]):self.run_local(radius=500)
        result=taste_city.build(['Björk','Radiohead','Little Simz'],city='Test address, London',env={'QLOO_TASTE_OFFLINE':'1'},cache_root=self.cache,local=True,radius=500)
        self.assertEqual(result['mode'],'recorded');self.assertEqual(result['local_area']['radius_m'],500)
        with self.assertRaises(taste_city.QlooUnavailable):taste_city.build(['Björk','Radiohead','Little Simz'],city='Different address',env={'QLOO_TASTE_OFFLINE':'1'},cache_root=self.cache,local=True,radius=500)

    def test_geocoder_outage_uses_only_exact_record(self):
        with patch.object(FakeQloo,'food_entities',[place('near')]):self.run_local(radius=500)
        with patch('taste_city.resolve_area',side_effect=local_places.LocationUnavailable('service down')):
            result=taste_city.build(['Björk','Radiohead','Little Simz'],city='Test address, London',env={'QLOO_API_KEY':'mock-key'},cache_root=self.cache,local=True,radius=500)
        self.assertEqual(result['mode'],'recorded')
    def test_popularity_is_checked_on_actual_entities(self):
        with patch.object(FakeQloo,'food_entities',[place('popular',popularity=0.8),place('unknown') | {'popularity':None},place('near')]):result=self.run_local(radius=500)
        self.assertEqual([x['id'] for x in result['nearby_places']],['near'])

class Geometry(unittest.TestCase):
    def test_distance_rejects_missing_invalid_and_out_of_bounds(self):
        self.assertEqual(local_places.distance_metres(AREA,place('same')),0)
        for loc in [{},{'lat':'nan','lon':0},{'lat':91,'lon':0}]:self.assertIsNone(local_places.distance_metres(AREA,{'location':loc}))
    def test_real_geocoder_wire_and_missing_result(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return b'[{"lat":"51.5","lon":"-0.12","display_name":"Matched postcode"}]'
        with patch('urllib.request.urlopen',return_value=Response()) as call:
            self.assertEqual(local_places.resolve_area('SW1A 1AA, London')['label'],'Matched postcode');self.assertIn('q=SW1A+1AA%2C+London',call.call_args[0][0].full_url)
        with patch('urllib.request.urlopen',side_effect=TimeoutError),self.assertRaises(local_places.LocationUnavailable):local_places.resolve_area('some address')
