"""Tests for the full city: four streets, the plaza's extra dimensions, the Wikipedia rows, and the eight questions.
A fake Qloo and a fake Wikipedia on localhost. No real call, no key, no network. Run: python3 -m unittest test_city"""
import json, os, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, unquote

import city, city_ask, match_app, qloo_client, village, wiki

SHARED = 3   # the first three of every list are the same for everyone, so tastes overlap


def ent(eid, name, t, aff=0.9):
    return {"entity_id": eid, "name": name, "types": [f"urn:entity:{t}"], "query": {"affinity": aff}, "popularity": 0.4,
            "properties": {"image": {"url": ""}}, "tags": [{"id": f"urn:tag:genre:{t}:indie", "name": "Indie", "type": "urn:tag:genre"}]}


class Fake(BaseHTTPRequestHandler):
    """Qloo: search finds anything except names with 'Nowhere' and carries a Wikidata id; insights return 10 per type,
    the first three shared by every seed; a seed with 'Mitski' adds one item only it and its fans share.
    Wikipedia: every Q id has an article; views are the Q number's length times 1000 per day."""
    seen = []

    def log_message(self, *a):
        pass

    def send(self, body, code=200):
        b = json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        Fake.seen.append((u.path, dict(q), self.headers.get("X-Api-Key")))
        if u.path == "/search":
            name = q["query"]
            if "Nowhere" in name:
                return self.send({"results": []})
            e = ent(f"ID-{name}", name, "artist")
            e["properties"]["external"] = {"wikidata": {"id": f"q{abs(hash(name)) % 90000 + 10000}"}}
            return self.send({"results": [e]})
        if u.path == "/v2/insights":
            seed, ft = q["signal.interests.entities"], q["filter.type"]
            if ft == "urn:demographics":
                band = ["24_and_younger", "35_to_44", "55_and_older"][len(seed) % 3]
                return self.send({"results": {"demographics": [{"query": {"age": {band: 0.4, "30_to_34": 0.1}, "gender": {"female": 0.1}}}]}})
            t = ft.split(":")[-1]
            out = [ent(f"{t}-shared-{r}", f"{t} for everyone {r}", t) for r in range(1, SHARED + 1)]
            out += [ent(f"{t}-{seed}-{r}", f"{t} {r} for {seed}", t) for r in range(SHARED + 1, 11)]
            if "Mitski" in seed or "Mitski" in q.get("filter.location.query", ""):
                out[-1] = ent(f"{t}-mitski", f"{t} Mitski fans love", t)
            return self.send({"results": {"entities": out}})
        if u.path == "/w/api.php":
            return self.send({"entities": {i: {"sitelinks": {"enwiki": {"title": f"Article {i}"}}} for i in q["ids"].split("|")}})
        if u.path.startswith("/pageviews/"):
            title = unquote(u.path.split("/")[2])
            return self.send({"items": [{"views": len(title) * 1000} for _ in range(30)]})
        self.send({"error": "no such path"}, 404)


class WithFake(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        cls.old = {k: os.environ.get(k) for k in ("QLOO_BASE", "WIKI_BASE", "QLOO_API_KEY", "TASTE_KEYCHAIN")}
        os.environ["QLOO_BASE"] = os.environ["WIKI_BASE"] = base
        os.environ.pop("QLOO_API_KEY", None); os.environ.pop("TASTE_KEYCHAIN", None)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()
        for k, v in cls.old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    def setUp(self):
        Fake.seen.clear()


def build_city(key="k-city"):
    """What the page does: the plaza village, the plaza's extras, then four streets. Returns (city, all calls)."""
    v = village.village(["Mitski", "Metallica", "Fleabag", "Dune", "Nike"], key=key, seed=3)
    plaza = [dict(x, pool=list(p), street=None) for x, p in zip(v["villagers"], v["pools"])]
    ex = city.plaza([{"name": x["name"], "love": x["love"], "id": x["found"]["id"], "wikidata": x["found"]["wikidata"]} for x in plaza], key=key)
    for x, e in zip(plaza, ex["extras"]):
        x["pool"] += e["pool"]; x["wiki"] = e["wiki"]
    calls = v["calls"] + ex["calls"]
    people = plaza
    for n in range(1, len(city.STREETS) + 1):
        s = city.street(n, [x["love"] for x in people], key=key)
        people += s["villagers"]; calls += s["calls"]
    return {"villagers": people}, calls


class Streets(WithFake):
    def test_a_street_is_five_villagers_forty_calls_eight_dimensions_and_a_public_row_each(self):
        s = city.street(1, key="k-street")
        self.assertEqual(s["name"], "Mill Lane")
        self.assertEqual(len(s["villagers"]), 5)
        self.assertEqual(len(s["calls"]), 40)
        self.assertTrue(all(c["id"].startswith("S1.L") for c in s["calls"]))
        for v in s["villagers"]:
            self.assertEqual({g["type"] for g in v["pool"]}, set(city.CITY_TYPES))
            self.assertIn(v["who"]["age"], city_ask.AGES)
            self.assertRegex(v["wiki"]["wikidata"], r"^Q\d+$")
            self.assertIsInstance(v["wiki"]["views_30d"], int)
            self.assertIn("/pageviews/", v["wiki"]["url"])
            self.assertIn("CC0", v["wiki"]["licence"])
        self.assertNotIn("k-street", json.dumps(s))
        places = [q for p, q, _ in Fake.seen if q.get("filter.type") == "urn:entity:place"]
        self.assertEqual(len(places), 5)
        self.assertTrue(all(q["filter.location.query"] == "London" for q in places))

    def test_no_street_can_spend_more_than_its_cap(self):
        calls = village.Calls("k", prefix="S9.", cap=city.STREET_CAP)
        for _ in range(city.STREET_CAP):
            calls.get("x", "/search", {"query": "x"})
        with self.assertRaises(qloo_client.BudgetSpent):
            calls.get("x", "/search", {"query": "x"})

    def test_a_love_already_in_the_city_is_swapped_for_a_spare(self):
        s = city.street(1, ["mitski", "Adele"], key="k")
        loves = [v["love"] for v in s["villagers"]]
        self.assertNotIn("Mitski", loves); self.assertNotIn("Adele", loves)
        self.assertEqual(loves[0], city.SPARES[0])

    def test_streets_never_share_a_love_or_a_name_with_each_other_or_the_plaza(self):
        loves = [l.lower() for _, ls, _ in city.STREETS for l in ls]
        names = [n for _, _, ns in city.STREETS for n in ns] + village.NAMES
        self.assertEqual(len(loves), len(set(loves)))
        self.assertEqual(len(names), len(set(names)))
        self.assertFalse(set(loves) & {s.lower() for s in village.SEEDS})

    def test_unknown_street_is_refused(self):
        self.assertIn("error", city.street(9, key="k"))


class PlazaExtras(WithFake):
    def test_plaza_villagers_get_places_podcasts_games_and_a_row(self):
        r = city.plaza([{"name": "Mabel", "love": "Mitski", "id": "ID-Mitski", "wikidata": "Q123"}], key="k")
        self.assertEqual(sorted(c["id"] for c in r["calls"]), ["P.L01", "P.L02", "P.L03"])
        self.assertEqual({g["type"] for g in r["extras"][0]["pool"]}, set(city.EXTRA_TYPES))
        self.assertEqual(r["extras"][0]["wiki"]["title"], "Article Q123")


class FullCity(WithFake):
    def test_twenty_five_villagers_every_one_bound_to_calls_and_a_row(self):
        c, calls = build_city()
        vs = c["villagers"]
        self.assertEqual(len(vs), 25)
        self.assertEqual(len(calls), 35 + 15 + 4 * 40)
        ids = {x["id"] for x in calls}
        self.assertEqual(len(ids), len(calls), "call ids must be unique city-wide")
        for v in vs:
            self.assertIn(v["found"]["call"], ids)
            self.assertIn(v["who"]["call"], ids)
            self.assertTrue(v["pool"] and all(g["call"] in ids for g in v["pool"]))
            self.assertEqual(len({g["type"] for g in v["pool"]}), 8 if v["street"] is None else 6)
            self.assertIsInstance(v["wiki"]["views_30d"], int)
        self.assertEqual(len({v["name"] for v in vs}), 25)


class Ask(WithFake):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.city, _ = build_city()

    def test_every_question_answers_and_cites_only_what_the_city_holds(self):
        for q in city_ask.QUESTIONS:
            a = city_ask.ask(self.city, q, "Mitski", key="k")
            self.assertEqual(a["problems"], [], q)
            self.assertTrue(a["answer"], q)
            self.assertTrue(a["cites"], q)
            self.assertEqual(a["villagers"], 25)

    def test_watch_finds_the_film_everyone_shares(self):
        a = city_ask.ask(self.city, "watch")
        self.assertTrue(a["answer"].startswith("movie for everyone 1. It is in 25 of 25"), a["answer"])
        self.assertIn("and 19 more", a["answer"])
        self.assertEqual(len(a["cites"]), 25)

    def test_eat_is_places_in_london_only(self):
        a = city_ask.ask(self.city, "eat")
        self.assertTrue(all(c["type"] == "place" for c in a["cites"]))

    def test_closest_pair_is_two_plaza_villagers_who_have_eight_dimensions_each(self):
        a = city_ask.ask(self.city, "closest")
        self.assertIn("24 things in common", a["answer"])
        self.assertEqual(a["answer"].count("the plaza"), 2)

    def test_who_loves_makes_three_calls_and_finds_the_mitski_villager(self):
        Fake.seen.clear()
        a = city_ask.ask(self.city, "who_loves", "Mitski", key="k")
        self.assertEqual(len(a["calls"]), 3)
        self.assertEqual(len(Fake.seen), 3)
        mitski = next(v["name"] for v in self.city["villagers"] if v["love"] == "Mitski")
        self.assertTrue(a["answer"].startswith(f"{mitski}, who loves Mitski."), a["answer"])

    def test_loudest_cites_the_two_public_rows(self):
        a = city_ask.ask(self.city, "loudest")
        self.assertEqual(len(a["rows"]), 2)
        self.assertTrue(all("/pageviews/" in r["url"] for r in a["rows"]))
        self.assertIn("not fans", a["answer"])

    def test_crowd_cites_demographics_calls(self):
        a = city_ask.ask(self.city, "crowd")
        self.assertTrue(all(c["type"] == "demographics" for c in a["cites"]))
        self.assertIn("under 25", a["answer"]); self.assertIn("55 and older", a["answer"])

    def test_check_rejects_a_cite_the_call_never_returned(self):
        a = city_ask.ask(self.city, "watch")
        a["cites"][0] = dict(a["cites"][0], item="A film nobody returned")
        self.assertEqual(len(city_ask.check(a, self.city)), 1)

    def test_check_rejects_a_stranger_and_a_foreign_row(self):
        a = {"names": ["Nobody"], "cites": [], "rows": [{"title": "X", "url": "https://example.org/x"}]}
        self.assertEqual(len(city_ask.check(a, self.city)), 2)

    def test_an_empty_city_answers_plainly(self):
        for q in ("closest", "outlier", "eat", "crowd", "loudest"):
            a = city_ask.ask({"villagers": []}, q)
            self.assertEqual(a["cites"], [], q)
            self.assertTrue(a["answer"], q)

    def test_outlier_owns_up_when_a_list_is_missing(self):
        c = {"villagers": [dict(v, pool=[g for g in v["pool"] if not (v["name"] == "Ada" and g["type"] == "artist")]) for v in self.city["villagers"]]}
        a = city_ask.ask(c, "outlier")
        self.assertTrue(a["answer"].startswith("Ada,"), a["answer"])
        self.assertIn("Qloo returned no artist list for Ada", a["answer"])

    def test_unknown_question_is_refused(self):
        self.assertIn("error", city_ask.ask(self.city, "anything"))


class WikiJoin(unittest.TestCase):
    def test_qid_reads_qloo_external_and_refuses_junk(self):
        self.assertEqual(wiki.qid({"properties": {"external": {"wikidata": {"id": "q44190"}}}}), "Q44190")
        self.assertEqual(wiki.qid({"properties": {"external": {"wikidata": [{"id": "Q1"}]}}}), "Q1")
        self.assertIsNone(wiki.qid({"properties": {"external": {"wikidata": {"id": "x1"}}}}))
        self.assertIsNone(wiki.qid({}))

    def test_window_is_thirty_complete_days(self):
        import datetime
        self.assertEqual(wiki.window(datetime.date(2026, 10, 22)), ("20260922", "20261021"))


class Routes(WithFake):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from http.server import ThreadingHTTPServer as S
        cls.app = S(("127.0.0.1", 0), match_app.H)
        threading.Thread(target=cls.app.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.app.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.app.shutdown(); cls.app.server_close(); super().tearDownClass()

    def call(self, path, body=None):
        req = urllib.request.Request(self.url + path, data=None if body is None else json.dumps(body).encode(), method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_street_without_a_key_names_the_key(self):
        st, d = self.call("/api/street?n=1")
        self.assertEqual(st, 503); self.assertIn("QLOO_API_KEY", d["error"])

    def test_street_and_ask_through_the_server(self):
        os.environ["QLOO_API_KEY"] = "k-route"
        try:
            st, s = self.call("/api/street?n=2&taken=Ted%20Lasso")
            self.assertEqual(st, 200); self.assertEqual(s["name"], "Station Road")
            self.assertNotIn("Ted Lasso", [v["love"] for v in s["villagers"]])
            st, a = self.call("/api/ask", {"q": "watch", "city": {"villagers": s["villagers"]}})
            self.assertEqual(st, 200); self.assertEqual(a["problems"], [])
            self.assertEqual(self.call("/api/street?n=x")[0], 400)
            self.assertEqual(self.call("/api/ask", {"q": "nope"})[0], 400)
        finally:
            del os.environ["QLOO_API_KEY"]

    def test_the_page_grows_the_city_and_asks_it(self):
        page = (match_app.HERE / "village.html").read_text()
        for needle in ('fetch(`/api/street?n=${n}', '"/api/street", { method: "POST"', '"/api/ask"', "openCity", "openPerson", "Ask the city", "ROADS"):
            self.assertIn(needle, page)

    def test_vercel_runs_the_new_functions(self):
        v = json.loads((match_app.HERE / "vercel.json").read_text())
        self.assertIn("api/street.py", v["functions"]); self.assertIn("api/ask.py", v["functions"])


if __name__ == "__main__":
    unittest.main()
