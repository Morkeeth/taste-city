"""Taste Panel tests. Fake Qloo only: no network, model, or real key."""
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import city_ask
import match_app
import panel
from test_city import WithFake


class PanelBuild(WithFake):
    def test_requires_three_to_ten_distinct_regulars(self):
        self.assertEqual(panel.regulars("Mitski\nMitski\n"), ["Mitski"])
        for text in ("Mitski\nAdele", "\n".join(f"Love {i}" for i in range(11))):
            with self.assertRaises(ValueError):
                panel.build(text, key="k")

    def test_three_regulars_become_a_cited_panel_of_twenty_five(self):
        out = panel.build("Mitski\nMetallica\nFleabag", key="k-panel")
        self.assertEqual(out["regulars"], ["Mitski", "Metallica", "Fleabag"])
        self.assertEqual(len(out["villagers"]), 25)
        self.assertEqual(len(out["calls"]), 200)
        self.assertEqual(len({c["id"] for c in out["calls"]}), 200)
        self.assertTrue(all(v["source"] in out["regulars"] for v in out["villagers"]))
        self.assertTrue(all(v["pool"] and v["found"]["call"] for v in out["villagers"]))
        self.assertNotIn("k-panel", json.dumps(out))

    def test_panel_questions_are_counts_and_name_their_calls(self):
        out = panel.build("Mitski\nMetallica\nFleabag", key="k-panel")
        city = {"villagers": out["villagers"]}
        love = city_ask.ask(city, "would_love", "Mitski", key="k-question")
        self.assertRegex(love["answer"], r"^\d+ of 25 panel members")
        self.assertEqual(love["problems"], [])
        self.assertTrue(love["calls"])
        turnout = city_ask.ask(city, "turnout")
        self.assertIn("25 panel members", turnout["answer"])
        self.assertEqual(len(turnout["cites"]), 25)
        self.assertEqual(turnout["problems"], [])

    def test_booker_templates_map_to_cited_panel_questions(self):
        out = panel.build("Mitski\nMetallica\nFleabag", key="k-panel")
        city = {"villagers": out["villagers"]}

        book = panel.answer_template(city, "book_act", "Mitski", key="k-question")
        self.assertRegex(book["answer"], r"^\d+ of 25 panel members")
        self.assertTrue(book["calls"])

        night = panel.answer_template(city, "which_night")
        self.assertIn("25 panel members", night["answer"])
        self.assertEqual(len(night["cites"]), 25)

        pair = panel.answer_template(city, "pair_with")
        self.assertIn("Qloo lists", pair["answer"])
        self.assertTrue(pair["cites"])
        self.assertEqual(pair["problems"], [])

        with self.assertRaises(ValueError):
            panel.answer_template(city, "invented")


class PanelRoutes(WithFake):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = ThreadingHTTPServer(("127.0.0.1", 0), match_app.H)
        threading.Thread(target=cls.app.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.app.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.app.shutdown(); cls.app.server_close(); super().tearDownClass()

    def call(self, path, body=None):
        req = urllib.request.Request(self.url + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"},
                                     method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.status, response.read(), response.headers.get_content_type()
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers.get_content_type()

    def test_panel_page_and_build_endpoint(self):
        status, page, content_type = self.call("/panel")
        self.assertEqual((status, content_type), (200, "text/html"))
        text = page.decode()
        for phrase in ("Who are your regulars?", "Use an example crowd", "Save this panel",
                       "Book this act", "Which night", "What to pair it with",
                       "Export partner brief", "taste-panel-v2"):
            self.assertIn(phrase, text)
        os.environ["QLOO_API_KEY"] = "k-route"
        try:
            status, body, _ = self.call("/api/panel", {"regulars": "Mitski\nMetallica\nFleabag"})
            self.assertEqual(status, 200)
            self.assertEqual(len(json.loads(body)["villagers"]), 25)
        finally:
            os.environ.pop("QLOO_API_KEY", None)

        vercel = json.loads((match_app.HERE / "vercel.json").read_text())
        self.assertIn("api/panel.py", vercel["functions"])

    def test_bad_panel_input_is_a_400(self):
        os.environ["QLOO_API_KEY"] = "k-route"
        try:
            status, body, _ = self.call("/api/panel", {"regulars": "Mitski\nAdele"})
            self.assertEqual(status, 400)
            self.assertIn("3 to 10", json.loads(body)["error"])
        finally:
            os.environ.pop("QLOO_API_KEY", None)


if __name__ == "__main__":
    unittest.main()
