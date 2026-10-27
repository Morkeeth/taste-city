"""Hipster tests on synthetic data only: no Qloo response, no Wikipedia call. Run: python3 -m unittest test_hipster"""
import json, pathlib, re, socket, subprocess, threading, unittest, urllib.request, urllib.error
import agent_week, app, backtest, life, radar, story

HERE = pathlib.Path(__file__).resolve().parent
T = 30  # cutoff week used in the synthetic tests

def flat(v, n=50):
    return [v] * n

def riser(n=50):
    """Flat at 1000, a lift in the two weeks up to T, then 3000 after T: a breakout momentum can see."""
    w = flat(1000, n)
    w[T - 1] = w[T] = 1800
    for i in range(T + 1, n):
        w[i] = 3000
    return w

def spiker(n=50):
    """Bigger two-week jump than riser, then straight back to 1000: momentum likes it, it is not a breakout."""
    w = flat(1000, n)
    w[T - 1] = w[T] = 2500
    return w

def ent(i, tags, neighbours=()):
    return {"id": i, "name": i.title(), "wikidata": None, "popularity": 0.5, "tags": tags,
            "seen_in": [{"call": "c01", "anchor": "Anchor", "rank": 1}], "neighbours": list(neighbours)}

class Backtest(unittest.TestCase):
    def test_weekly_sums_and_gaps(self):
        daily = {f"202307{d:02d}": 1 for d in range(3, 17)}
        w = backtest.weekly(daily, last=backtest.dt.date(2023, 7, 23))
        self.assertEqual(w, [7, 7, None])

    def test_cutoff_arms(self):
        series = {"big": flat(9000), "rise": riser(), "spike": spiker(), "small": flat(100)}
        elig, hit, arms, q = backtest.cutoff(series, {}, T)
        self.assertNotIn("small", elig)  # under the 700 floor
        self.assertEqual(hit, {"rise"})
        self.assertEqual(arms["P"][0], "big")
        self.assertEqual(arms["M"][0], "spike")  # momentum is fooled by the spike; the test reports it, not hides it

    def test_neighbour_term_moves_q(self):
        series = {"a": riser(), "b": spiker(), "c": riser()}
        _, _, arms0, _ = backtest.cutoff(series, {}, T)
        _, _, arms1, _ = backtest.cutoff(series, {"a": ["c"], "c": ["a"]}, T)
        self.assertEqual(arms0["Q"][0], "b")
        self.assertIn(arms1["Q"][0], {"a", "c"})

    def test_block_ci_is_deterministic(self):
        xs = [0.1, 0.3] * 20
        self.assertEqual(backtest.block_ci(xs), backtest.block_ci(xs))
        lo, hi = backtest.block_ci(xs)
        self.assertLessEqual(lo, 0.2); self.assertGreaterEqual(hi, 0.2)

    def test_verdict_needs_lower_bound_above_zero(self):
        s = {"Q-P": {"ci": [0.01, 0.2]}, "Q-base": {"ci": [0.02, 0.3]}, "Q-M": {"ci": [-0.01, 0.02]}}
        self.assertEqual(backtest.verdict(s), {"K1_hipster_is_a_result": True, "K2_qloo_earns_its_place": False})
        s["Q-P"]["ci"][0] = 0.0
        self.assertFalse(backtest.verdict(s)["K1_hipster_is_a_result"])

    def test_code_matches_prereg(self):
        pre = (HERE / "PREREG.txt").read_text()
        self.assertIn(f"k = {backtest.K} ", pre)
        self.assertIn(f"past(i) >= {backtest.FLOOR} ", pre)
        self.assertIn(f">= {backtest.JUMP} x past(i)", pre)
        self.assertIn(f"{backtest.NEIGHBOUR_WEIGHT} x mean of m(j)", pre)
        self.assertEqual(backtest.TEST, ("2025-01-05", "2026-08-16"))
        self.assertEqual(backtest.DEV, ("2024-01-07", "2024-12-29"))

class Radar(unittest.TestCase):
    def setUp(self):
        self.u = {"rise": ent("rise", ["techno"]), "spike": ent("spike", ["house"]), "jazz": ent("jazz", ["jazz"]),
                  "small": ent("small", ["techno"])}
        self.s = {"rise": riser(), "spike": spiker(), "jazz": riser(), "small": flat(100)}

    def test_membership_by_tag(self):
        self.assertEqual(sorted(radar.members(self.u, radar.BY_ID["monk"], self.s)), ["rise", "small", "spike"])

    def test_past_week_is_graded(self):
        r = radar.calls(self.u, self.s, radar.BY_ID["monk"], T)
        got = {p["name"]: p["called_it"] for p in r["picks"]}
        self.assertEqual(got, {"Spike": False, "Rise": True})
        self.assertEqual(r["eligible"], 2)

    def test_now_has_no_grade_and_ignores_future(self):
        last = len(self.s["rise"]) - 1
        r = radar.calls(self.u, self.s, radar.BY_ID["monk"], last)
        self.assertTrue(all("called_it" not in p for p in r["picks"]))
        s2 = {k: v[:T + 1] + [0 if k == "rise" else 99999] * (len(v) - T - 1) for k, v in self.s.items()}
        a = [p["name"] for p in radar.calls(self.u, self.s, radar.BY_ID["monk"], T)["picks"]]
        b = [p["name"] for p in radar.calls(self.u, s2, radar.BY_ID["monk"], T)["picks"]]
        self.assertEqual(a, b)  # the pick never reads a week after the cutoff
        self.assertEqual(a, ["Spike", "Rise"])

class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        u = {"rise": ent("rise", ["techno"]), "jazz": ent("jazz", ["jazz"])}
        n = backtest.week_index("2025-03-02") + 1
        s = {"rise": [1000] * (n - 1) + [5000], "jazz": [2000] * n}
        sock = socket.socket(); sock.bind(("127.0.0.1", 0)); cls.port = sock.getsockname()[1]; sock.close()
        cls.srv = app.serve(app.Data(u, s), cls.port)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def get(self, path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def head(self, path):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method="HEAD")
        try:
            with urllib.request.urlopen(request) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    def test_page_and_archetypes(self):
        code, body = self.get("/")
        self.assertEqual(code, 200); self.assertIn(b"Who moves into the village?", body)
        self.assertIn(b"Qloo powered", body)
        self.assertIn(b"Taste moves each resident", body)
        code, body = self.get("/api/archetypes")
        d = json.loads(body)
        self.assertEqual(len(d["archetypes"]), 6)
        self.assertEqual(d["weeks"][-1], "2025-03-02")

    def test_radar_now(self):
        code, body = self.get("/api/radar?a=monk")
        d = json.loads(body)
        self.assertEqual(code, 200); self.assertTrue(d["now"])
        self.assertEqual([p["name"] for p in d["picks"]], ["Rise"])

    def test_city_groups_by_qloo_call_and_hides_the_future(self):
        code, body = self.get("/api/city?a=monk&week=2025-03-02")
        d = json.loads(body)
        self.assertEqual(code, 200)
        self.assertEqual([(x["anchor"], [m["name"] for m in x["members"]]) for x in d["districts"]], [("Anchor", ["Rise"])])
        self.assertEqual(d["districts"][0]["members"][0]["views"], 5000)
        self.assertEqual(self.get("/api/city?a=nobody")[0], 404)

    def test_vendor_route_is_a_whitelist(self):
        self.assertEqual(self.get("/vendor/three.module.min.js")[0], 200)
        self.assertEqual(self.get("/vendor/../app.py")[0], 404)
        self.assertEqual(self.get("/vendor/THREE-LICENSE")[0], 404)
        self.assertEqual(self.head("/"), 200)
        self.assertEqual(self.head("/nope"), 404)

    def test_life_route(self):
        code, _ = self.get("/api/life?a=monk")
        self.assertEqual(code, 404)
        sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
        srv = app.serve(app.Data({}, {"x": [1]}, lives={"monk": {"id": "monk", "day": []}}), port)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/life?a=monk") as r:
                self.assertEqual(json.loads(r.read())["id"], "monk")
        finally:
            srv.shutdown(); srv.server_close()

    def test_bad_inputs_404(self):
        self.assertEqual(self.get("/api/radar?a=nobody")[0], 404)
        self.assertEqual(self.get("/api/radar?a=monk&week=2020-01-05")[0], 404)
        self.assertEqual(self.get("/api/radar?a=monk&week=junk")[0], 404)
        self.assertEqual(self.get("/nope")[0], 404)

class LiveCommand(unittest.TestCase):
    """live_hipster.py against a fake Qloo on localhost. No real call."""
    def test_plan_fits_cap_and_key_stays_out(self):
        import os, sys
        from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
        seen = []
        class Fake(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                seen.append((self.path, self.headers.get("X-Api-Key")))
                b = json.dumps({"success": True, "results": {"entities": [{"entity_id": "E1", "name": "x"}]}}).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            import live_hipster
            client = live_hipster.live.Live("SECRET", base=f"http://127.0.0.1:{srv.server_address[1]}", pause=0)
            calls = live_hipster.run(client)
        finally:
            srv.shutdown(); srv.server_close()
        self.assertEqual(len(calls), live_hipster.PLANNED_CALLS)
        self.assertLessEqual(live_hipster.PLANNED_CALLS, live_hipster.live.MAX_CALLS)
        self.assertTrue(seen[0][0].startswith("/v2/trending?"))
        self.assertTrue(all(k == "SECRET" for _, k in seen))
        self.assertNotIn("SECRET", json.dumps(calls))

    def test_no_key_no_call(self):
        env = {k: v for k, v in __import__("os").environ.items() if k != "QLOO_API_KEY"}
        r = subprocess.run(["python3", str(HERE / "live_hipster.py")], env=env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("No call made", r.stderr)

def place(name, genre, cats=(), aff=0.9, akas=()):
    return {"name": name, "query": {"affinity": aff},
            "properties": {"primary_genre": {"id": f"urn:tag:genre:place:{genre}", "akas": [{"value": a} for a in akas]}},
            "tags": [{"id": f"urn:tag:category:place:{c}", "name": c, "type": "urn:tag:category:place"} for c in cats]}

class Life(unittest.TestCase):
    def test_primary_genre_wins_over_tags(self):
        self.assertEqual(life.slot_of(place("Pub", "pub", ["Event venue"])), "evening")
        self.assertEqual(life.slot_of(place("Shop", "record_store")), "day")
        self.assertEqual(life.slot_of(place("Club", "night_club")), "late")

    def test_translations_and_offices_never_count(self):
        self.assertIsNone(life.slot_of(place("Office", "government_office", akas=["bar", "Restaurant"])))
        self.assertIsNone(life.slot_of(place("Palace", "palace", ["Tourist attraction"])))

    def test_day_takes_best_per_slot_and_keeps_call_ids(self):
        call = {"id": "L01", "body": {"results": {"entities": [place("A", "pub", aff=0.7), place("B", "bar", aff=0.9), place("C", "embassy")]}}}
        empty = lambda i: {"id": i, "body": {"results": {"entities": []}}}
        demo = {"id": "L05", "body": {"results": {"demographics": [{"query": {"age": {"25_to_29": 0.4, "55_and_older": -0.2}, "gender": {"male": -0.3, "female": 0.3}}}]}}}
        d = {"city": "London", "fetched": "2026-10-19", "calls": [call, empty("L02"), empty("L03"), empty("L04"), demo],
             "archetypes": {"monk": {"anchors": [{"id": "x", "name": "X"}], "calls": {"place": "L01", "movie": "L02", "tv_show": "L03", "brand": "L04", "demographics": "L05"}}}}
        p = life.profile(d, "monk")
        self.assertEqual([(s["time"], s["name"], s["call"]) for s in p["day"]], [("19:00", "B", "L01")])
        self.assertEqual(p["dropped"], ["C"])
        self.assertEqual(p["crowd"], {"age": "25 to 29", "age_index": 0.4, "lean": "female", "lean_index": 0.3, "call": "L05"})

class Story(unittest.TestCase):
    @staticmethod
    def place(name, genre, affinity, ambience=()):
        return {"name": name, "properties": {"primary_genre": {"id": "urn:tag:genre:place:" + genre}}, "query": {"affinity": affinity},
                "tags": [{"id": "urn:tag:ambience:qloo:" + a.lower(), "name": a} for a in ambience]}

    def test_week_slot_takes_best_of_its_kind_and_never_repeats(self):
        P = [(self.place("Bar A", "pub", 0.7), "L1"), (self.place("Cafe", "restaurant", 0.9), "L2"), (self.place("Bar B", "bar", 0.8), "L3")]
        used = set()
        self.assertEqual(story.pick(P, story.EVENING, used)[0]["name"], "Bar B")
        self.assertEqual(story.pick(P, story.EVENING, used)[0]["name"], "Bar A")
        self.assertEqual(story.pick(P, story.EVENING, used), (None, None))
        self.assertEqual(story.pick(P, story.FOOD, used)[1], "L2")

    def test_ambience_reads_only_ambience_tags(self):
        e = self.place("Pub", "pub", 0.5, ("Historic",)); e["tags"].append({"id": "urn:tag:genre:place:pub", "name": "Lively"})
        self.assertEqual(story.ambience(e), {"Historic"})

    def test_one_week_rule_can_hold_fail_or_abstain(self):
        T2 = T + story.GAP
        held = riser(); self.assertGreaterEqual(held[T2], story.RISE * 1000)
        self.assertTrue(story.one_week_rule({0: held}, [0], T))
        self.assertFalse(story.one_week_rule({0: spiker()}, [0], T))
        self.assertIsNone(story.one_week_rule({0: flat(100)}, [0], T))

    def test_rival_is_the_most_different_week(self):
        wk = lambda *names: [{"name": n} for n in names]
        S = {"a": {"week": wk("x", "y", "z"), "tension": None, "age": "30"}, "b": {"week": wk("x", "y", "q"), "tension": None, "age": "30"},
             "c": {"week": wk("p", "q", "r"), "tension": None, "age": "30"}}
        self.assertEqual(story.rival(S, "a"), "c")
        self.assertEqual(story.distance(S["a"], S["a"]), 0)


def agent_log():
    return [{"id": "A01", "path": "/v2/insights", "params": {"filter.type": "urn:entity:place"}, "status": 200,
             "body": {"results": {"entities": [{"name": "Bar One"}, {"name": "Club Two"}]}}},
            {"id": "A02", "path": "/v2/insights", "params": {"filter.type": "urn:entity:movie"}, "status": 200,
             "body": {"results": {"entities": [{"name": "Film Three"}, {"name": "Anchor Act"}]}}}]

def agent_rows():
    names = {"Thu": ("Bar One", "A01"), "Fri": ("Club Two", "A01"), "Wed": ("Film Three", "A02")}
    return [{"day": d, "what": w, "name": names.get(d, (None, "A01"))[0], "call": names.get(d, (None, "A01"))[1]}
            for d, w in agent_week.DAYS]

class Agent(unittest.TestCase):
    def test_good_week_passes_and_gaps_are_allowed(self):
        self.assertEqual(agent_week.validate(agent_rows(), agent_log()), [])

    def test_row_with_no_call_id_fails(self):
        w = agent_rows(); w[3]["call"] = None
        self.assertEqual(agent_week.validate(w, agent_log()), ["Thu: no call ID"])

    def test_call_from_outside_the_run_fails(self):
        w = agent_rows(); w[3]["call"] = "L11"
        self.assertEqual(agent_week.validate(w, agent_log()), ["Thu: call L11 was not made in this run"])

    def test_name_the_call_never_returned_fails(self):
        w = agent_rows(); w[3]["name"] = "Bar From Memory"
        self.assertEqual(agent_week.validate(w, agent_log()), ["Thu: Bar From Memory is not in call A01"])

    def test_known_artist_and_day_order_fail(self):
        w = agent_rows(); w[2]["name"] = "Anchor Act"; w[0], w[1] = w[1], w[0]
        bad = agent_week.validate(w, agent_log(), anchors=("Anchor Act",))
        self.assertIn("days are not Mon to Sun in order", bad)
        self.assertIn("Wed: Anchor Act is one of the three artists they already love", bad)

    def test_places_kind_becomes_a_qloo_genre_tag_and_junk_is_dropped(self):
        sent = []
        def get(path, params):
            sent.append(params); return {"id": "A01", "path": path, "params": params, "status": 200, "body": {"results": {"entities": []}}}
        for kind in ("wine_bar", "bar;drop", None):
            agent_week.run_tool(get, "places", {"seeds": ["x"], "take": 99, "kind": kind})
        self.assertEqual([p.get("filter.tags") for p in sent], ["urn:tag:genre:place:wine_bar", None, None])
        self.assertEqual({p["take"] for p in sent}, {25})

    def test_loop_rejects_a_bad_finish_then_keeps_the_fixed_one_and_sums_cost(self):
        bad = agent_rows(); bad[3]["name"] = "Bar From Memory"
        script = [({"action": "places", "args": {"seeds": ["x"]}}, 0.1), ({"action": "insights", "args": {"type": "movie", "seeds": ["x"]}}, 0.1),
                  ({"action": "finish", "args": {"week": bad}}, 0.1), ({"action": "finish", "args": {"week": agent_rows()}}, 0.1)]
        prompts, log = [], agent_log()
        def fake_qloo(key, out):
            def get(path, params):
                out.append(log[len(out)]); return out[-1]
            return get
        def fake_model(system, prompt):
            prompts.append(prompt); return script[len(prompts) - 1]
        d = {"archetypes": {"poet": {"anchors": [{"name": "Anchor Act"}]}}}
        old = agent_week.qloo, agent_week.ask_model
        agent_week.qloo, agent_week.ask_model = fake_qloo, fake_model
        try:
            w = agent_week.plan("poet", "k", d)
        finally:
            agent_week.qloo, agent_week.ask_model = old
        self.assertEqual(w["problems"], [])
        self.assertEqual(w["week"], agent_rows())
        self.assertIn("Bar From Memory is not in call A01", prompts[-1])
        self.assertEqual((w["cost"]["turns"], w["cost"]["qloo_calls"], w["cost"]["usd"]), (4, 2, 0.4))

class Hygiene(unittest.TestCase):
    def test_no_stamps_or_seals(self):
        page = (HERE / "hipster.html").read_text().lower()
        for bad in ("stamp", "class: \"badge", ".badge"):
            self.assertNotIn(bad, page)

    def test_page_never_uses_inner_html(self):
        self.assertNotIn("innerHTML", (HERE / "hipster.html").read_text())

    def test_app_has_no_network_client(self):
        src = (HERE / "app.py").read_text() + (HERE / "radar.py").read_text() + (HERE / "life.py").read_text()
        for bad in ("urllib.request", "http.client", "requests", "socket"):
            self.assertNotIn(bad, src)

    def test_sprites_are_12_wide(self):
        page = (HERE / "hipster.html").read_text()
        block = page[page.index("const BODY"):page.index("const NS")]
        rows = re.findall(r'"([.a-z]{6,})"', block)
        self.assertGreater(len(rows), 30)
        self.assertEqual({len(r) for r in rows}, {12})

    def test_no_qloo_data_in_git(self):
        files = subprocess.run(["git", "ls-files"], cwd=HERE, capture_output=True, text=True).stdout.split()
        self.assertTrue(files)
        for f in files:
            text = (HERE / f).read_text(errors="replace")
            self.assertIsNone(re.search(r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}", text), f)
            self.assertNotIn("images." + "qloo.com", text, f)
        lines = (HERE / ".gitignore").read_text().split("\n")
        self.assertIn("cache/", lines)
        r = subprocess.run(["git", "check-ignore", "-q", "cache/views.json"], cwd=HERE)
        self.assertEqual(r.returncode, 0)

if __name__ == "__main__":
    unittest.main()
