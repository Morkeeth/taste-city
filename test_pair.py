"""The share loop: link ids, the made and finished counts, a wrong id is a 404, and the pages are served.
No key, no network: the Matchmaker is replaced by a scripted one that records how it was called."""
import json, os, pathlib, re, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import match_app, pair, taste_match

HERE = pathlib.Path(__file__).resolve().parent

def scripted(calls):
    def match(a, b, city, names=("A", "B")):
        calls.append((a, b, city, names))
        return {"city": city, "model": "scripted", "problems": [],
                "answer": {"headline": "You meet in slow songs", "meet": [
                    {"what": "listen", "name": "Song One", "call": "Q07", "why": "both lists"},
                    {"what": "go", "name": "Cafe Two", "call": "Q16", "why": "both lists"}],
                    "a_shows_b": {"name": "Film A", "call": "Q08", "why": "x"}, "b_shows_a": {"name": "Film B", "call": "Q09", "why": "y"},
                    "difference": "d", "ask_each_other": "Which is better?"},
                "calls": [{"id": "Q07", "purpose": "both artist", "status": 200, "url": "/v2/insights", "names": ["Song One"]}]}
    return match

class Ids(unittest.TestCase):
    def test_id_is_six_readable_characters(self):
        for _ in range(200):
            i = pair.new_id()
            self.assertRegex(i, r"^[2-9a-hjkmnp-z]{6}$")
            self.assertTrue(pair.ID.match(i))

    def test_id_never_repeats_one_already_taken(self):
        taken = {pair.new_id() for _ in range(50)}
        self.assertNotIn(pair.new_id(taken), taken)

    def test_ids_that_do_not_match_the_shape_are_not_looked_up(self):
        s = pair.Store(pathlib.Path(tempfile.mkdtemp()) / "p.json")
        for bad in ("", "abc", "ABCDEF", "../../x", "abcdefg", "o0l1io"):
            with self.assertRaises(pair.NotFound):
                s.get(bad)

class StoreCounts(unittest.TestCase):
    def setUp(self):
        self.s, self.calls = pair.Store(pathlib.Path(tempfile.mkdtemp()) / "p.json"), []

    def test_create_counts_one_sent_and_keeps_the_answers(self):
        i = self.s.create("Oscar", ["Mitski", "Fleabag", "Dishoom"], "London")
        self.assertEqual(self.s.counts(), {"made": 1, "finished": 0})
        self.assertEqual(self.s.get(i)["a"], ["Mitski", "Fleabag", "Dishoom"])

    def test_finish_runs_the_matchmaker_once_and_counts_once(self):
        i = self.s.create("Oscar", ["Mitski"], "London")
        p = self.s.finish(i, "Sam", ["ABBA"], scripted(self.calls))
        self.assertEqual(p["result"]["answer"]["headline"], "You meet in slow songs")
        self.assertEqual(self.calls, [(["Mitski"], ["ABBA"], "London", ("Oscar", "Sam"))])
        self.s.finish(i, "Sam", ["ABBA"], scripted(self.calls))   # a second tap, or the friend reloading
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.s.counts(), {"made": 1, "finished": 1})

    def test_a_failed_match_is_not_counted_as_finished(self):
        i = self.s.create("Oscar", ["Mitski"])
        p = self.s.finish(i, "Sam", ["ABBA"], lambda *a, **k: {"error": "Qloo found none of one person's loves."})
        self.assertIn("Qloo found none", p["failed"])
        self.assertEqual(self.s.counts()["finished"], 0)
        self.assertIsNone(self.s.get(i).get("result"))

    def test_finishing_a_wrong_id_is_not_found(self):
        with self.assertRaises(pair.NotFound):
            self.s.finish("zzzzzz", "Sam", ["ABBA"], scripted(self.calls))
        self.assertEqual(self.calls, [])

class StorePlace(unittest.TestCase):
    def test_local_store_is_under_cache_which_git_ignores(self):
        p = pair.store_path({})
        self.assertEqual(p.parent.name, "cache")
        self.assertIn("cache/", (HERE / ".gitignore").read_text().split("\n"))

    def test_on_vercel_the_store_is_tmp_and_an_explicit_path_wins(self):
        self.assertEqual(str(pair.store_path({"VERCEL": "1"})), "/tmp/pairs.json")
        self.assertEqual(str(pair.store_path({"VERCEL": "1", "PAIR_STORE": "/data/p.json"})), "/data/p.json")

class FakeUpstash(BaseHTTPRequestHandler):
    """Upstash's REST shape: POST a JSON command array, get {"result": ...}. Only GET, SET [NX] and INCR."""
    data, auth = {}, []
    def log_message(self, *a):
        pass
    def do_POST(self):
        FakeUpstash.auth.append(self.headers.get("Authorization"))
        c = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        op, d = c[0], FakeUpstash.data
        if op == "GET":
            r = d.get(c[1])
        elif op == "SET":
            r = None if "NX" in c[3:] and c[1] in d else "OK"
            if r:
                d[c[1]] = c[2]
        elif op == "INCR":
            d[c[1]] = str(int(d.get(c[1], 0)) + 1); r = int(d[c[1]])
        b = json.dumps({"result": r}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

class RedisStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstash)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.env = {"KV_REST_API_URL": f"http://127.0.0.1:{cls.srv.server_address[1]}", "KV_REST_API_TOKEN": "t-fake"}

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def test_with_the_upstash_variables_set_the_store_is_redis_and_the_loop_counts_once(self):
        s, calls = pair.open_store(self.env), []
        self.assertIsInstance(s, pair.Redis)
        i = s.create("Oscar", ["Mitski"], "London")
        self.assertRegex(i, r"^[2-9a-hjkmnp-z]{6}$")
        s.finish(i, "Sam", ["ABBA"], scripted(calls))
        s.finish(i, "Sam", ["ABBA"], scripted(calls))
        self.assertEqual(len(calls), 1)
        self.assertEqual(s.get(i)["result"]["answer"]["headline"], "You meet in slow songs")
        self.assertEqual(s.counts(), {"made": 1, "finished": 1})
        with self.assertRaises(pair.NotFound):
            s.get("zzzzzz")
        self.assertEqual(set(FakeUpstash.auth), {"Bearer t-fake"})   # the token travels in the header only

    def test_without_them_the_store_is_the_file(self):
        self.assertIsInstance(pair.open_store({"PAIR_STORE": "/tmp/x.json"}), pair.Store)

class Http(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        os.environ["PAIR_STORE"] = os.path.join(cls.dir, "pairs.json")
        cls.real, cls.calls = taste_match.match, []
        taste_match.match = scripted(cls.calls)
        cls.app = ThreadingHTTPServer(("127.0.0.1", 0), match_app.H)
        threading.Thread(target=cls.app.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.app.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.app.shutdown(); cls.app.server_close()
        taste_match.match = cls.real
        del os.environ["PAIR_STORE"]

    def call(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method="POST" if data else "GET", headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req) as r:
                raw = r.read()
                return r.status, json.loads(raw) if path.startswith("/api") else raw
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_the_whole_loop_counts_one_sent_and_one_finished(self):
        before = self.call("/api/pair?counts=1")[1]
        st, made = self.call("/api/pair", {"an": "Oscar", "a": ["Mitski", "Fleabag", ""], "city": "London"})
        self.assertEqual(st, 200)
        self.assertRegex(made["path"], r"^/pair/[2-9a-hjkmnp-z]{6}$")
        st, p = self.call("/api/pair?id=" + made["id"])
        self.assertEqual((st, p["an"], p["a"], p["result"]), (200, "Oscar", ["Mitski", "Fleabag"], None))
        st, done = self.call("/api/pair", {"id": made["id"], "bn": "Sam", "b": ["ABBA", "The Bear", "Dishoom"]})
        self.assertEqual(st, 200)
        self.assertEqual(done["result"]["answer"]["meet"][1]["name"], "Cafe Two")
        st, again = self.call("/api/pair?id=" + made["id"])   # Oscar opens the same link and sees the same result
        self.assertEqual(again["result"], done["result"])
        after = self.call("/api/pair?counts=1")[1]
        self.assertEqual((after["made"] - before["made"], after["finished"] - before["finished"]), (1, 1))

    def test_a_wrong_id_is_a_404_on_read_and_on_finish(self):
        self.assertEqual(self.call("/api/pair?id=zzzzzz")[0], 404)
        self.assertEqual(self.call("/api/pair?id=")[0], 404)
        st, body = self.call("/api/pair", {"id": "zzzzzz", "bn": "Sam", "b": ["ABBA"]})
        self.assertEqual(st, 404)
        self.assertIn("send it again", body["error"])

    def test_no_answers_is_a_plain_400(self):
        self.assertEqual(self.call("/api/pair", {"an": "Oscar", "a": ["", " "]})[0], 400)
        made = self.call("/api/pair", {"an": "Oscar", "a": ["Mitski"]})[1]
        self.assertEqual(self.call("/api/pair", {"id": made["id"], "b": []})[0], 400)

    def test_the_pair_pages_are_served_and_the_root_is_still_the_village(self):
        for path in ("/pair", "/pair/abcdef"):
            st, body = self.call(path)
            self.assertEqual(st, 200, path)
            self.assertIn(b"Where do your tastes meet?", body)
        self.assertIn(b"<title>Taste City</title>", self.call("/")[1])

class Page(unittest.TestCase):
    page = (HERE / "pair.html").read_text()

    def test_page_asks_the_same_three_questions_as_the_server(self):
        for q in pair.QUESTIONS:
            self.assertIn(q, self.page)

    def test_page_never_loads_the_village_and_links_to_it_in_one_tap(self):
        self.assertNotIn("/api/village", self.page)
        self.assertIn('href="/?loves=', self.page)
        self.assertIn('href="/"', self.page)

    def test_vercel_rewrites_pair_links_and_runs_the_function_for_a_minute(self):
        v = json.loads((HERE / "vercel.json").read_text())
        rw = {r["source"]: r["destination"] for r in v["rewrites"]}
        self.assertEqual((rw["/pair"], rw["/pair/:id"], rw["/"]), ("/pair.html", "/pair.html", "/village.html"))
        self.assertEqual(v["functions"]["api/pair.py"]["maxDuration"], 60)

if __name__ == "__main__":
    unittest.main()
