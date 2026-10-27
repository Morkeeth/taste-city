"""Tests for the live entry: Taste City and Taste Match. A fake Qloo on localhost and a fake model client.
No real Qloo call, no key, no network. Run: python3 -m unittest test_taste_match"""
import json, os, pathlib, random, threading, types, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import match_app, qloo_client, taste_match, village

HERE = pathlib.Path(__file__).resolve().parent


def entity(eid, name, etype="artist", aff=0.9, tags=("Indie",)):
    return {"entity_id": eid, "name": name, "types": [f"urn:entity:{etype}"], "query": {"affinity": aff}, "popularity": 0.4,
            "properties": {"image": {"url": ""}, "release_year": 2001},
            "tags": [{"id": f"urn:tag:genre:{etype}:{t.lower()}", "name": t, "type": "urn:tag:genre"} for t in tags]}


class FakeQloo(BaseHTTPRequestHandler):
    """Search returns one entity named after the query. Insights return 10 entities whose names depend on the seed,
    so each villager has their own list. A request with flaky=1 in the seed gets 429 twice, then 200."""
    seen, flaky_hits = [], {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        FakeQloo.seen.append((self.path, self.headers.get("X-Api-Key")))
        if u.path == "/search":
            name = q["query"][0]
            body = {"results": [entity(f"ID-{name}", name, q.get("types", ["urn:entity:artist"])[0].split(",")[0].split(":")[-1])]}
        elif u.path == "/v2/insights":
            seed = q.get("signal.interests.entities", ["none"])[0]
            ft = q["filter.type"][0]
            if "flaky" in seed:
                n = FakeQloo.flaky_hits[seed] = FakeQloo.flaky_hits.get(seed, 0) + 1
                if n <= 2:
                    self.send_response(429); self.send_header("Content-Length", "0"); self.end_headers(); return
            if ft == "urn:demographics":
                body = {"results": {"demographics": [{"query": {"age": {"24_and_younger": -0.2, "35_to_44": 0.4, "55_and_older": 0.1}, "gender": {"male": -0.12, "female": 0.12}}}]}}
            else:
                t = ft.split(":")[-1]; take = int(q.get("take", ["10"])[0])
                body = {"results": {"entities": [entity(f"{t}-{seed}-{r}", f"{t} {r} for {seed}", t, round(0.95 - r * 0.02, 2)) for r in range(1, take + 1)]}}
        else:
            body = {"error": "no such path"}
        b = json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)


class WithFakeQloo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeQloo)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        cls.old = {k: os.environ.get(k) for k in ("QLOO_BASE", "QLOO_API_KEY", "TASTE_KEYCHAIN")}
        os.environ["QLOO_BASE"] = cls.base
        os.environ.pop("QLOO_API_KEY", None); os.environ.pop("TASTE_KEYCHAIN", None)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()
        for k, v in cls.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def setUp(self):
        FakeQloo.seen.clear(); FakeQloo.flaky_hits.clear()


class Client(WithFakeQloo):
    def test_key_only_in_header_and_call_ids_count_up(self):
        q = qloo_client.Live("SECRET-KEY", base=self.base, max_calls=3, pause=0)
        c1 = q.get("one", "/search", {"query": "Mitski", "take": 1})
        c2 = q.get("two", "/v2/insights", {"filter.type": "urn:entity:movie", "signal.interests.entities": "ID-Mitski", "take": 3})
        self.assertEqual((c1["id"], c2["id"]), ("L01", "L02"))
        self.assertEqual(c1["status"], 200)
        self.assertNotIn("SECRET-KEY", json.dumps([c1, c2]))
        self.assertTrue(all(k == "SECRET-KEY" for _, k in FakeQloo.seen))

    def test_429_is_retried_under_the_same_call_id(self):
        q = qloo_client.Live("k", base=self.base, pause=0)
        c = q.get("flaky", "/v2/insights", {"filter.type": "urn:entity:movie", "signal.interests.entities": "flaky-seed", "take": 2})
        self.assertEqual(c["status"], 200)
        self.assertEqual(c["id"], "L01")
        self.assertEqual(len(FakeQloo.seen), 3)   # two 429s, then 200, one call ID

    def test_budget_cap_raises(self):
        q = qloo_client.Live("k", base=self.base, max_calls=1, pause=0)
        q.get("one", "/search", {"query": "x"})
        with self.assertRaises(qloo_client.BudgetSpent):
            q.get("two", "/search", {"query": "y"})

    def test_no_key_no_client(self):
        with self.assertRaises(ValueError):
            qloo_client.Live("", base=self.base)


class Keys(WithFakeQloo):
    def test_missing_key_is_named_and_nothing_else_is_printed(self):
        with self.assertRaises(taste_match.MissingKey) as cm:
            taste_match.secret("NOT_SET_ANYWHERE", "no-such-service")
        self.assertIn("NOT_SET_ANYWHERE", str(cm.exception))
        self.assertNotIn("security", str(cm.exception))

    def test_env_wins(self):
        os.environ["TM_TEST_KEY"] = "from-env"
        try:
            self.assertEqual(taste_match.secret("TM_TEST_KEY", "no-such-service"), "from-env")
        finally:
            del os.environ["TM_TEST_KEY"]

    def test_server_names_the_missing_keys(self):
        self.assertEqual(match_app.missing_keys({}), ["QLOO_API_KEY", "ANTHROPIC_API_KEY"])
        self.assertEqual(match_app.missing_keys({"QLOO_API_KEY": "x"}), ["ANTHROPIC_API_KEY"])


def villager(name, love_id, pool_ids, rank_from=1):
    return {"name": name, "love": name, "found": {"id": love_id, "name": name},
            "pool": [{"id": p, "name": p, "type": ["movie", "book", "artist"][i % 3], "rank": rank_from + i, "image": None, "affinity": 0.8, "call": "L0X"}
                     for i, p in enumerate(pool_ids)]}


class Rounds(unittest.TestCase):
    def test_every_gift_has_exactly_one_owner_and_is_never_their_own_love(self):
        vs = [villager("A", "a", ["shared", "a1", "a2", "a3", "a"]),
              villager("B", "b", ["shared", "b1", "b2", "b3"]),
              villager("C", "c", ["shared", "c1", "c2", "c3"])]
        gifts = village.rounds(vs, random.Random(1))
        self.assertTrue(gifts)
        self.assertLessEqual(len(gifts), village.ROUNDS)
        ids = [g["id"] for g in gifts]
        self.assertNotIn("shared", ids)        # two villagers' lists returned it, no single right answer
        self.assertNotIn("a", ids)             # the villager's own love is not a gift
        for g in gifts:
            holders = [v["name"] for v in vs if g["id"] in {p["id"] for p in v["pool"]}]
            self.assertEqual(holders, [vs[g["owner"]]["name"]], g)

    def test_gifts_are_spread_over_villagers(self):
        vs = [villager(n, n.lower(), [f"{n}{i}" for i in range(8)]) for n in ("A", "B", "C", "D", "E")]
        gifts = village.rounds(vs, random.Random(2))
        self.assertEqual(len(gifts), 10)
        owners = sorted(g["owner"] for g in gifts)
        self.assertEqual(owners, [0, 0, 1, 1, 2, 2, 3, 3, 4, 4])


class AgeBand(unittest.TestCase):
    def test_strongest_band_and_gender_lean(self):
        demo = {"id": "L05", "response": {"results": {"demographics": [{"query": {"age": {"25_to_29": -0.1, "45_to_54": 0.3}, "gender": {"male": 0.2, "female": -0.2}}}]}}}
        who = village.age_band(demo)
        self.assertEqual((who["age"], who["gender_lean"], who["call"]), ("45_to_54", "male", "L05"))

    def test_small_gender_skew_reads_even(self):
        demo = {"id": "L06", "response": {"results": {"demographics": [{"query": {"age": {"30_to_34": 0.1}, "gender": {"male": 0.03, "female": -0.03}}}]}}}
        self.assertEqual(village.age_band(demo)["gender_lean"], "even")

    def test_missing_demographics_do_not_crash(self):
        self.assertEqual(village.age_band({"id": "L07", "response": {}})["age"], None)


class VillageBuild(WithFakeQloo):
    def test_five_villagers_thirty_five_calls_ten_gifts_each_citing_a_call(self):
        r = village.village(["Mitski", "Metallica", "Fleabag", "Dune", "Nike"], key="k-test", seed=3)
        self.assertNotIn("error", r)
        self.assertEqual(len(r["villagers"]), 5)
        self.assertEqual(len(r["calls"]), 35)
        self.assertEqual(len(r["gifts"]), 10)
        ids = {c["id"] for c in r["calls"]}
        for g in r["gifts"]:
            self.assertIn(g["call"], ids)
            self.assertIn(g["owner"], range(5))
        for v in r["villagers"]:
            self.assertNotIn("pool", v)
            self.assertEqual(v["who"]["age"], "35_to_44")
        self.assertNotIn("k-test", json.dumps(r))
        self.assertTrue(all(k == "k-test" for _, k in FakeQloo.seen))

    def test_move_in_adds_a_sixth_villager_and_seven_more_calls(self):
        r = village.village(["Mitski", "Metallica", "Fleabag", "Dune", "Nike"], me="Radiohead", key="k", seed=3)
        self.assertEqual([v["name"] for v in r["villagers"]][-1], "You")
        self.assertEqual(len(r["calls"]), 42)


class Validate(unittest.TestCase):
    calls = [{"id": "L01", "response": {"results": {"entities": [{"name": "Little Simz"}, {"name": "Sampha"}]}}},
             {"id": "L02", "response": {"results": {"entities": [{"name": "Beef"}]}}}]
    good = {"meet": [{"what": "listen", "name": "Little Simz", "call": "L01", "why": "w"}, {"what": "watch", "name": "Beef", "call": "L02", "why": "w"}],
            "a_shows_b": {"name": "Sampha", "call": "L01", "why": "w"}, "b_shows_a": {"name": "Beef", "call": "L02", "why": "w"}}

    def test_good_answer_passes(self):
        self.assertEqual(taste_match.validate(self.good, self.calls), [])

    def test_name_the_call_never_returned_is_rejected(self):
        bad = json.loads(json.dumps(self.good)); bad["meet"][0]["name"] = "Radiohead"
        self.assertEqual(taste_match.validate(bad, self.calls), ["meet 1: Radiohead is not in call L01"])

    def test_call_never_made_is_rejected(self):
        bad = json.loads(json.dumps(self.good)); bad["a_shows_b"]["call"] = "L99"
        self.assertEqual(taste_match.validate(bad, self.calls), ["a_shows_b: call L99 was not made"])

    def test_meet_needs_two_to_four_rows(self):
        bad = json.loads(json.dumps(self.good)); bad["meet"] = bad["meet"][:1]
        self.assertIn("meet needs 2 to 4 rows", taste_match.validate(bad, self.calls))


class FanOut(WithFakeQloo):
    def test_six_searches_twelve_insights_and_bridge_flags(self):
        run = taste_match.Run(qloo_client.Live("k", base=self.base, max_calls=24, pause=0), "London")
        A, B, briefs, seen = taste_match.fan_out(run, ["Mitski", "The Bear", "Ghibli"], ["Kendrick", "Top Boy", "Dishoom"])
        self.assertEqual(len(run.calls), 18)
        self.assertEqual([x["name"] for x in A], ["Mitski", "The Bear", "Ghibli"])
        self.assertEqual(len(briefs), 12)
        both = [b for b in briefs if b["purpose"].startswith("both")]
        self.assertEqual(len(both), 4)
        self.assertTrue(all("in_A_list" in r and "in_B_list" in r for b in both for r in b["results"]))
        place = next(c for c in run.calls if c["purpose"] == "A only place")
        self.assertIn("filter.location.query=London", place["url"])

    def test_a_love_qloo_cannot_find_is_marked_not_found(self):
        run = taste_match.Run(qloo_client.Live("k", base=self.base, max_calls=24, pause=0), "London")
        row = run.resolve("Mitski")
        self.assertEqual(row["name"], "Mitski")
        self.assertEqual(row["call"], "L01")


def block(**kw):
    return types.SimpleNamespace(**kw)


class FakeModel:
    """Scripted turns. Each turn is a list of tool_use blocks the model 'emits'."""
    def __init__(self, turns):
        self.turns, self.received = list(turns), []
        self.messages = types.SimpleNamespace(create=self.create)

    def create(self, **kw):
        self.received.append(list(kw["messages"]))   # a snapshot: agent() keeps appending to the same list
        content = [block(type="tool_use", name=n, input=i, id=f"t{len(self.received)}{k}") for k, (n, i) in enumerate(self.turns.pop(0))]
        return types.SimpleNamespace(content=content, usage=types.SimpleNamespace(input_tokens=100, output_tokens=10))


class AgentLoop(WithFakeQloo):
    def run_with(self):
        run = taste_match.Run(qloo_client.Live("k", base=self.base, max_calls=24, pause=0), "London")
        A, B, briefs, _ = taste_match.fan_out(run, ["Mitski"], ["Kendrick"])
        return run, A, B, briefs

    def answer(self, listen, watch, call_l="L03", call_w="L05"):
        return {"headline": "h", "meet": [{"what": "listen", "name": listen, "call": call_l, "why": "w"}, {"what": "watch", "name": watch, "call": call_w, "why": "w"}],
                "a_shows_b": {"name": listen, "call": call_l, "why": "w"}, "b_shows_a": {"name": watch, "call": call_w, "why": "w"}, "difference": "d", "ask_each_other": "q"}

    def test_bad_finish_is_sent_back_then_the_fixed_one_is_kept(self):
        run, A, B, briefs = self.run_with()
        names = {c["id"]: [e["name"] for e in taste_match.entities(c)] for c in run.calls}
        good = self.answer(names["L03"][0], names["L05"][0])
        model = FakeModel([[("finish", self.answer("Radiohead", names["L05"][0]))], [("finish", good)]])
        ans, problems, usage, turns = taste_match.agent(run, A, B, briefs, model, ("Ana", "Ben"))
        self.assertEqual((ans, problems, turns), (good, [], 2))
        self.assertEqual(usage, {"input": 200, "output": 20})
        second = model.received[1][-1]["content"][0]
        self.assertTrue(second["is_error"])
        self.assertIn("Radiohead is not in call L03", second["content"])
        self.assertIn('"A_name": "Ana"', model.received[0][0]["content"])

    def test_qloo_more_makes_a_real_call_and_the_extra_cap_holds(self):
        run, A, B, briefs = self.run_with()
        more = ("qloo_more", {"type": "place", "seeds": ["ID-Mitski"], "place_kind": "bar"})
        names = {c["id"]: [e["name"] for e in taste_match.entities(c)] for c in run.calls}
        good = self.answer(names["L03"][0], names["L05"][0])
        model = FakeModel([[more], [more, more, more], [("finish", good)]])
        ans, problems, usage, turns = taste_match.agent(run, A, B, briefs, model, ("A", "B"))
        self.assertEqual(problems, [])
        self.assertEqual(len(run.calls), 14 + taste_match.EXTRA)
        bar = run.calls[14]
        self.assertEqual(bar["purpose"], "agent place bar")
        self.assertIn("filter.tags=urn:tag:genre:place:bar", bar["url"])
        refused = [r for r in model.received[2][-1]["content"] if r.get("is_error")]
        self.assertEqual(len(refused), 1)

    def test_agent_that_never_finishes_reports_it(self):
        run, A, B, briefs = self.run_with()
        model = FakeModel([[]] * taste_match.TURNS)
        ans, problems, usage, turns = taste_match.agent(run, A, B, briefs, model)
        self.assertEqual((ans, problems, turns), (None, ["agent never finished"], taste_match.TURNS))


class FrontDoor(WithFakeQloo):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = ThreadingHTTPServer(("127.0.0.1", 0), match_app.H)
        threading.Thread(target=cls.app.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.app.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.app.shutdown(); cls.app.server_close()
        super().tearDownClass()

    def get(self, path, method="GET", data=None):
        req = urllib.request.Request(self.url + path, method=method, data=data, headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_root_is_the_village_and_the_match_page_is_at_match(self):
        st, body = self.get("/")
        self.assertEqual(st, 200); self.assertIn(b"<title>Taste City</title>", body)
        st, body = self.get("/match")
        self.assertEqual(st, 200); self.assertIn(b"<title>Taste Match</title>", body)
        st, body = self.get("/village")
        self.assertEqual(st, 200); self.assertIn(b"<title>Taste City</title>", body)
        self.assertEqual(self.get("/nothing")[0], 404)

    def test_vercel_serves_the_same_front_door_and_no_index_html_shadows_it(self):
        v = json.loads((HERE / "vercel.json").read_text())
        rw = {r["source"]: r["destination"] for r in v["rewrites"]}
        self.assertEqual(rw["/"], "/village.html")
        self.assertEqual(rw["/match"], "/match.html")
        self.assertFalse((HERE / "index.html").exists(), "Vercel serves a file before a rewrite, so index.html would hide the village")

    def test_village_page_has_the_matchmaker_and_the_progress_count(self):
        page = (HERE / "village.html").read_text()
        for needle in ('id="hud"', "villagers won", "Matchmaker", 'fetch("/api/match"', "openMatch", 'id="loadn"'):
            self.assertIn(needle, page)
        self.assertNotIn('href="/"', page.replace('href=""', ""))   # the village is the root now; links go to /match

    def test_village_api_without_a_key_fails_plainly_and_names_the_key(self):
        st, body = self.get("/api/village")
        self.assertEqual(st, 503)
        self.assertIn("QLOO_API_KEY", json.loads(body)["error"])

    def test_empty_match_request_is_a_plain_400(self):
        st, body = self.get("/api/match", "POST", b"{}")
        self.assertEqual(st, 400)
        self.assertIn("at least one thing", json.loads(body)["error"])

    def test_village_api_builds_from_the_fake(self):
        os.environ["QLOO_API_KEY"] = "k-env"
        try:
            st, body = self.get("/api/village?loves=Mitski|Metallica|Fleabag")
        finally:
            del os.environ["QLOO_API_KEY"]
        self.assertEqual(st, 200)
        d = json.loads(body)
        self.assertEqual(len(d["villagers"]), 5)   # three named, two from the seed list
        self.assertEqual(len(d["calls"]), 35)


if __name__ == "__main__":
    unittest.main()
