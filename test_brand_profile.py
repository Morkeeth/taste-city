import json
import pathlib
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import brand_profile


def entity(entity_id, name, kind, affinity=0.9):
    return {"entity_id": entity_id, "name": name, "types": [f"urn:entity:{kind}"], "query": {"affinity": affinity}}


class FakeQloo(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *args):
        pass

    def reply(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        FakeQloo.seen.append((parsed.path, query, self.headers.get("X-Api-Key")))
        if parsed.path == "/search":
            cue = query["query"]
            return self.reply({"results": [entity("seed-" + str(len(FakeQloo.seen)), cue, "brand")]})
        kind = query["filter.type"].split(":")[-1]
        if kind == "demographics":
            return self.reply({"results": {"demographics": [{"query": {"age": {"25_to_29": 0.44}, "gender": {"female": 0.12}}}]}})
        names = {"brand": "Aesop", "artist": "Kelela", "movie": "Moonlight", "place": "Barbican"}
        return self.reply({"results": {"entities": [entity("result-" + kind, names[kind], kind, 0.88)]}})


HTML = """<!doctype html><html><head><title>North Star Coffee | London</title>
<meta name="description" content="Small-batch coffee, night listening sessions and thoughtful design."></head>
<body><h1>Coffee after dark</h1><h2>Listening room</h2><p>Seasonal coffee and independent music in London.</p></body></html>"""


class BrandProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeQloo)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeQloo.seen.clear()
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp.cleanup()

    def test_confirmed_anchor_requery_excludes_rejected_matches_and_makes_only_five_calls(self):
        profile = brand_profile.build('https://example.com/', env={'QLOO_API_KEY':'fixture'}, base=self.base, cache_root=self.temp.name, fetcher=lambda url:(url,HTML))
        chosen = profile['anchors'][0]['id']
        FakeQloo.seen.clear()
        result = brand_profile.confirm_anchors(profile,[chosen],env={'QLOO_API_KEY':'fixture'},base=self.base)
        self.assertEqual(len(FakeQloo.seen),5)
        self.assertTrue(all(path == '/v2/insights' for path,_,_ in FakeQloo.seen))
        self.assertTrue(all(query['signal.interests.entities'] == chosen for _,query,_ in FakeQloo.seen))
        self.assertEqual([a['id'] for a in result['anchors']],[chosen])
        self.assertEqual(result['anchor_confirmation']['approved_ids'],[chosen])
        with self.assertRaises(ValueError):
            brand_profile.confirm_anchors(profile,['not-an-original-id'],env={'QLOO_API_KEY':'fixture'},base=self.base)

    def test_public_site_profile_maps_cues_and_derives_archetypes_from_qloo(self):
        fetcher = lambda url: (url, HTML)
        result = brand_profile.build(
            "https://northstar.example/", city="London", prefer_cache=False, fetcher=fetcher,
            env={"QLOO_API_KEY": "mock-key", "QLOO_BASE": self.base}, cache_root=self.temp.name,
        )
        self.assertEqual(result["page"]["title"], "North Star Coffee | London")
        self.assertEqual(len(result["anchors"]), 1)
        self.assertEqual(len(result["calls"]), 6)
        self.assertEqual({row["domain"] for row in result["outlets"]}, {"brands", "music", "film", "places", "demographics"})
        self.assertEqual(len(result["archetypes"]), 3)
        self.assertIn("Kelela", result["archetypes"][0]["name"])
        self.assertTrue(all(row["evidence"] for row in result["archetypes"]))
        self.assertTrue(all(header == "mock-key" for _, _, header in FakeQloo.seen))
        self.assertNotIn("mock-key", next(pathlib.Path(self.temp.name).glob("*.json")).read_text())

    def test_exact_url_cache_replays_without_site_or_qloo_calls(self):
        url = "https://northstar.example/"
        first = brand_profile.build(url, prefer_cache=False, fetcher=lambda value: (value, HTML), env={"QLOO_API_KEY": "mock-key", "QLOO_BASE": self.base}, cache_root=self.temp.name)
        calls = len(FakeQloo.seen)
        second = brand_profile.build(url, prefer_cache=True, fetcher=lambda value: self.fail("website fetched"), env={}, cache_root=self.temp.name)
        self.assertEqual(first["page"]["content_sha256"], second["page"]["content_sha256"])
        self.assertEqual(second["mode"], "recorded")
        self.assertEqual(len(FakeQloo.seen), calls)

    def test_private_and_credential_urls_are_rejected(self):
        with self.assertRaises(brand_profile.InvalidBrandURL):
            brand_profile.normalize_url("https://user:pass@example.com/")
        resolver = lambda host, port: [(None, None, None, None, ("127.0.0.1", 0))]
        with self.assertRaises(brand_profile.InvalidBrandURL):
            brand_profile._public_host("http://localhost/", resolver=resolver)

    def test_malformed_port_is_rejected_cleanly(self):
        with self.assertRaisesRegex(brand_profile.InvalidBrandURL, "valid public website port"):
            brand_profile.normalize_url("https://example.com:not-a-port")

    def test_generic_navigation_does_not_become_qloo_entity_seeds(self):
        page = brand_profile.page_profile('https://www.monmouthcoffee.co.uk/', '<title>Home - Monmouth Coffee Company</title><h1>About Us</h1><h2>New on the Counter</h2>')
        self.assertEqual(page['cues'], ['Monmouth Coffee Company'])

    def test_page_profile_uses_visible_public_content(self):
        profile = brand_profile.page_profile("https://northstar.example/", HTML + "<script>Secret Tracker</script>")
        self.assertIn("listening", profile["keywords"])
        self.assertNotIn("tracker", profile["keywords"])
        self.assertEqual(profile["cues"], ["North Star Coffee"])


if __name__ == "__main__":
    unittest.main()
