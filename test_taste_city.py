"""The three-card Qloo path with a mocked network and temporary recorded cache."""
import json
import os
import pathlib
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import match_app
import taste_city


def entity(entity_id, name, kind, genre=""):
    row = {
        "entity_id": entity_id,
        "name": name,
        "types": [f"urn:entity:{kind}"],
        "query": {"affinity": 0.91},
    }
    if genre:
        row["properties"] = {"primary_genre": {"id": f"urn:tag:genre:place:{genre}"}}
    return row


class FakeQloo(BaseHTTPRequestHandler):
    seen = []
    food_entities = [
        entity("result-place-museum", "A Museum With A Cafe", "place", "museum"),
        entity("result-place-restaurant", "Actual Restaurant", "place", "restaurant"),
    ]

    def log_message(self, *args):
        pass

    def reply(self, body, code=200):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        FakeQloo.seen.append((parsed.path, query, self.headers.get("X-Api-Key")))
        if parsed.path == "/search":
            asked = query["query"]
            return self.reply({"results": [entity(f"seed-{asked.lower().replace(' ', '-')}", asked, "artist")]})
        if parsed.path == "/v2/insights":
            kind = query["filter.type"].split(":")[-1]
            if kind == "demographics":
                return self.reply({"results": {"demographics": [{"query": {
                    "age": {"25_to_29": 0.42, "45_to_54": -0.08},
                    "gender": {"female": 0.18, "male": -0.18},
                }}]}})
            if kind == "place":
                return self.reply({"results": {"entities": FakeQloo.food_entities}})
            return self.reply({"results": {"entities": [
                entity(f"result-{kind}-1", f"Qloo {kind} result 1", kind),
                entity(f"result-{kind}-2", f"Qloo {kind} result 2", kind),
            ]}})
        return self.reply({"error": "not found"}, 404)


class TasteCity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qloo = ThreadingHTTPServer(("127.0.0.1", 0), FakeQloo)
        threading.Thread(target=cls.qloo.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.qloo.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.qloo.shutdown()
        cls.qloo.server_close()

    def setUp(self):
        FakeQloo.seen.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.cache = pathlib.Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_live_path_resolves_three_cards_fills_five_outlets_and_records(self):
        result = taste_city.build(
            ["Björk", "Radiohead", "Little Simz"],
            env={
                "QLOO_API_KEY": "mock-key",
                "QLOO_BASE": self.base,
                "QLOO_TASTE_DIAGNOSTICS": str(self.cache / "diagnostics" / "food.json"),
            },
            cache_root=self.cache,
        )
        self.assertEqual(result["mode"], "live")
        self.assertEqual(len(result["anchors"]), 3)
        self.assertEqual(len(result["outlets"]), 5)
        self.assertEqual(len(result["calls"]), 8)
        self.assertEqual(len(FakeQloo.seen), 8)
        self.assertTrue(all(header == "mock-key" for _, _, header in FakeQloo.seen))
        self.assertTrue(all(row["entity"]["id"].startswith("result-") for row in result["outlets"]))
        food = next(row for row in result["outlets"] if row["domain"] == "food")
        self.assertEqual(food["entity"]["name"], "Actual Restaurant")
        self.assertEqual(food["entity"]["genre"], "restaurant")
        food_query = next(query for path, query, _ in FakeQloo.seen if path == "/v2/insights" and query.get("filter.type") == "urn:entity:place")
        self.assertEqual(food_query["filter.tags"], "urn:tag:genre:place:restaurant")
        self.assertEqual(food_query["filter.location.query"], "London")
        files = list(self.cache.glob("*.json"))
        self.assertEqual(len(files), 1)
        self.assertNotIn("mock-key", files[0].read_text())
        diagnostic = json.loads((self.cache / "diagnostics" / "food.json").read_text())
        self.assertEqual([row["primary_genre"]["id"] for row in diagnostic["candidates"]], [
            "urn:tag:genre:place:museum", "urn:tag:genre:place:restaurant",
        ])
        self.assertNotIn("mock-key", json.dumps(diagnostic))

    def test_each_scenario_uses_its_own_domains_location_and_demographics(self):
        picks = ["Björk", "Radiohead", "Little Simz"]
        popup = taste_city.build(
            picks, city="London", profile="brand:popup",
            env={"QLOO_API_KEY": "mock-key", "QLOO_BASE": self.base}, cache_root=self.cache,
        )
        popup_queries = [query for path, query, _ in FakeQloo.seen if path == "/v2/insights"]
        FakeQloo.seen.clear()
        merch = taste_city.build(
            picks, city="London", profile="brand:merch",
            env={"QLOO_API_KEY": "mock-key", "QLOO_BASE": self.base}, cache_root=self.cache,
        )
        merch_queries = [query for path, query, _ in FakeQloo.seen if path == "/v2/insights"]
        self.assertEqual(popup["profile"], "brand:popup")
        self.assertEqual(merch["profile"], "brand:merch")
        self.assertNotEqual(
            [query["filter.type"] for query in popup_queries],
            [query["filter.type"] for query in merch_queries],
        )
        self.assertTrue(any(query.get("filter.location.query") == "London" for query in popup_queries))
        self.assertTrue(any(query["filter.type"] == "urn:demographics" for query in popup_queries))
        self.assertTrue(any(query["filter.type"] == "urn:demographics" for query in merch_queries))
        self.assertEqual(len(popup["calls"]), 7)
        self.assertEqual(len(merch["calls"]), 7)

    def test_brand_and_festival_profiles_return_different_entity_sets(self):
        picks = ["Björk", "Radiohead", "Little Simz"]
        brand = taste_city.build(
            picks, profile="brand:popup", env={"QLOO_API_KEY": "mock-key", "QLOO_BASE": self.base}, cache_root=self.cache,
        )
        festival = taste_city.build(
            picks, profile="festival:lineup", env={"QLOO_API_KEY": "mock-key", "QLOO_BASE": self.base}, cache_root=self.cache,
        )
        brand_entities = {row["entity"]["id"] for row in brand["outlets"] if row["entity"].get("id")}
        festival_entities = {row["entity"]["id"] for row in festival["outlets"] if row["entity"].get("id")}
        self.assertNotEqual(brand_entities, festival_entities)
        self.assertIn("result-place-restaurant", brand_entities)
        self.assertIn("result-destination-1", festival_entities)

    def test_food_type_uses_primary_genre_not_secondary_name_or_tag(self):
        museum = entity("museum", "Restaurant Museum", "place", "museum")
        museum["tags"] = [{"id": "urn:tag:genre:place:restaurant", "name": "Restaurant"}]
        self.assertFalse(taste_city.is_food_place(museum))
        self.assertTrue(taste_city.is_food_place(entity("food", "Dinner", "place", "french_restaurant")))
        self.assertEqual(
            taste_city.place_genre(entity("cafe", "Cafe", "place", "restaurant:cafe")),
            "restaurant:cafe",
        )
        self.assertTrue(taste_city.is_food_place(entity("cafe", "Cafe", "place", "restaurant:cafe")))

    def test_synthetic_candidate_shape_selects_only_primary_genre_cafe(self):
        fixture = json.loads((pathlib.Path(__file__).parent / "tests" / "fixtures" / "synthetic-food-candidates.json").read_text())
        chosen = next(row for row in fixture["candidates"] if taste_city.is_food_place(row))
        self.assertEqual(chosen["name"], "Fictional Corner Cafe")
        self.assertEqual(taste_city.place_genre(chosen), "restaurant:cafe")

    def test_live_path_fails_when_take_five_has_no_restaurant_typed_result(self):
        original = FakeQloo.food_entities
        FakeQloo.food_entities = [entity("museum", "Wellcome Collection", "place", "museum")]
        try:
            with self.assertRaisesRegex(taste_city.QlooUnavailable, "no restaurant-typed"):
                taste_city.build(
                    ["Björk", "Radiohead", "Little Simz"],
                    env={"QLOO_API_KEY": "mock-key", "QLOO_BASE": self.base},
                    cache_root=self.cache,
                )
        finally:
            FakeQloo.food_entities = original

    def test_old_record_without_verified_food_genre_is_rejected(self):
        path = taste_city.cache_path(["Björk", "Radiohead", "Little Simz"], root=self.cache)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "result": {"outlets": [
            {"domain": "food", "entity": {"name": "Wellcome Collection", "type": "place"}}
        ]}}))
        with self.assertRaises(taste_city.QlooUnavailable):
            taste_city.build(["Björk", "Radiohead", "Little Simz"], env={"QLOO_TASTE_OFFLINE": "1"}, cache_root=self.cache)

    def test_exact_choice_record_is_used_when_offline(self):
        picks = ["Björk", "Radiohead", "Little Simz"]
        taste_city.build(picks, env={"QLOO_API_KEY": "mock-key", "QLOO_BASE": self.base}, cache_root=self.cache)
        calls = len(FakeQloo.seen)
        result = taste_city.build(picks, env={"QLOO_TASTE_OFFLINE": "1"}, cache_root=self.cache)
        self.assertEqual(result["mode"], "recorded")
        self.assertEqual(len(FakeQloo.seen), calls)
        self.assertEqual(result["picks"], picks)

    def test_failed_network_falls_back_to_the_record(self):
        picks = ["Björk", "Radiohead", "Little Simz"]
        taste_city.build(picks, env={"QLOO_API_KEY": "mock-key", "QLOO_BASE": self.base}, cache_root=self.cache)
        result = taste_city.build(
            picks,
            env={"QLOO_API_KEY": "mock-key", "QLOO_BASE": "http://127.0.0.1:1"},
            cache_root=self.cache,
        )
        self.assertEqual(result["mode"], "recorded")

    def test_missing_process_environment_key_fails_plainly_without_a_record(self):
        with self.assertRaisesRegex(taste_city.MissingKey, "QLOO_API_KEY"):
            taste_city.build(["One", "Two", "Three"], env={}, cache_root=self.cache)

    def test_requires_exactly_three_different_cards(self):
        for picks in (["One", "Two"], ["One", "One", "Two"], ["One", "Two", "Three", "Four"]):
            with self.assertRaises(taste_city.InvalidTaste):
                taste_city.build(picks, env={}, cache_root=self.cache)

    def test_live_module_has_no_keychain_path(self):
        source = pathlib.Path(taste_city.__file__).read_text()
        self.assertNotIn("find-generic-password", source)
        self.assertNotIn("TASTE_KEYCHAIN", source)


class TasteRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qloo = ThreadingHTTPServer(("127.0.0.1", 0), FakeQloo)
        threading.Thread(target=cls.qloo.serve_forever, daemon=True).start()
        cls.app = ThreadingHTTPServer(("127.0.0.1", 0), match_app.H)
        threading.Thread(target=cls.app.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.app.server_address[1]}"
        cls.temp = tempfile.TemporaryDirectory()
        cls.old = {key: os.environ.get(key) for key in ("QLOO_API_KEY", "QLOO_BASE", "QLOO_TASTE_CACHE")}
        os.environ["QLOO_API_KEY"] = "route-key"
        os.environ["QLOO_BASE"] = f"http://127.0.0.1:{cls.qloo.server_address[1]}"
        os.environ["QLOO_TASTE_CACHE"] = cls.temp.name

    @classmethod
    def tearDownClass(cls):
        cls.app.shutdown(); cls.app.server_close()
        cls.qloo.shutdown(); cls.qloo.server_close()
        cls.temp.cleanup()
        for key, value in cls.old.items():
            os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)

    def post(self, body):
        request = urllib.request.Request(
            self.url + "/api/taste",
            method="POST",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_route_runs_the_mocked_live_path(self):
        area = {'lat':51.5,'lon':-0.12,'label':'Fixture address, London','source':'fixture'}
        food = [dict(row, location={'lat':51.5,'lon':-0.12}, popularity=0.2) for row in FakeQloo.food_entities]
        with patch('taste_city.resolve_area', return_value=area), patch.object(FakeQloo, 'food_entities', food):
            status, result = self.post({"picks": ["Björk", "Radiohead", "Little Simz"], "city": "London"})
        self.assertEqual(status, 200)
        self.assertEqual(result["mode"], "live")
        self.assertEqual(len(result["outlets"]), 5)

    def test_route_rejects_two_cards(self):
        status, result = self.post({"picks": ["Björk", "Radiohead"]})
        self.assertEqual(status, 400)
        self.assertIn("exactly three", result["error"])

    def test_vercel_includes_the_taste_function(self):
        config = json.loads((pathlib.Path(match_app.__file__).parent / "vercel.json").read_text())
        self.assertIn("api/taste.py", config["functions"])


if __name__ == "__main__":
    unittest.main()
