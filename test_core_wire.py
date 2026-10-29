import unittest
from unittest.mock import patch
import test_taste_city as fixture
import test_local_places as local_fixture
import taste_city

class CoreWire(unittest.TestCase):
    setUpClass=fixture.TasteCity.__dict__['setUpClass']
    tearDownClass=fixture.TasteCity.__dict__['tearDownClass']
    setUp=fixture.TasteCity.setUp
    tearDown=fixture.TasteCity.tearDown
    def test_local_core_queries_places_not_only_restaurants_and_checks_coordinates(self):
        cafe=local_fixture.place('cafe')
        gallery=local_fixture.place('gallery')
        gallery['properties']['primary_genre']['id']='urn:tag:genre:place:art_gallery'
        outside=local_fixture.place('outside',lon=-0.16)
        with patch('taste_city.resolve_area',return_value=local_fixture.AREA),patch.object(fixture.FakeQloo,'food_entities',[gallery,outside,cafe]):
            result=taste_city.build(['Björk','Radiohead','Little Simz'],city='Fixture address',env={'QLOO_API_KEY':'mock','QLOO_BASE':self.base},cache_root=self.cache,local=True,radius=500,discovery=False,core=True)
        queries=[q for path,q,key in fixture.FakeQloo.seen if q.get('filter.type')=='urn:entity:place']
        self.assertEqual(len(queries),2);self.assertEqual(queries[-1]['filter.location'],'POINT(-0.12 51.5)');self.assertEqual(queries[-1]['filter.location.radius'],'500');self.assertNotIn('filter.tags',queries[-1]);self.assertEqual(result['http_reads'],9);self.assertEqual([p['id'] for p in result['nearby_places']],['gallery','cafe'])
