"""The share loop. One person answers three taste questions and gets a short link; a friend opens it, answers the
same three, and the Matchmaker (taste_match.match, unchanged) finds where the two meet. Both see the stored result.
The store is one JSON file: the pairs, plus how many links were made (counted when the link is made, before it is sent) and how many were finished.
Locally it is cache/pairs.json (ignored by git, like every Qloo-derived file). On Vercel it is /tmp/pairs.json, which
lives only as long as one warm function instance: a cold start forgets every link. For links that survive, add an
Upstash Redis database to the Vercel project (Storage tab); it sets KV_REST_API_URL and KV_REST_API_TOKEN, and then
the pairs and counts live there (Redis below). PAIR_STORE names another file path."""
import fcntl, json, os, pathlib, re, secrets, time, urllib.request

QUESTIONS = ("A band or artist you would put on tonight", "A show or film you would happily watch again",
             "A place you love going: a restaurant, bar, cafe or shop")
ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"   # no 0, 1, i, l, o: easy to read out loud
ID = re.compile(rf"^[{ALPHABET}]{{6}}$")

class NotFound(KeyError):
    pass

def store_path(env=os.environ):
    if env.get("PAIR_STORE"):
        return pathlib.Path(env["PAIR_STORE"])
    if env.get("VERCEL"):
        return pathlib.Path("/tmp/pairs.json")
    return pathlib.Path(__file__).resolve().parent / "cache" / "pairs.json"

def open_store(env=os.environ):
    if env.get("KV_REST_API_URL") and env.get("KV_REST_API_TOKEN"):
        return Redis(env["KV_REST_API_URL"], env["KV_REST_API_TOKEN"])
    return Store(store_path(env))

def new_id(taken=()):
    while True:
        i = "".join(secrets.choice(ALPHABET) for _ in range(6))
        if i not in taken:
            return i

def answers(xs):
    """Three answers, trimmed. Blank ones are dropped; at least one is needed."""
    if not isinstance(xs, list):
        return []
    return [str(x).strip()[:80] for x in xs[:3] if str(x).strip()]

class Store:
    def __init__(self, path=None):
        self.path = pathlib.Path(path) if path else store_path()

    def _edit(self, fn):
        """Read, change and write the file under an exclusive lock, so two finishes never lose a count."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path.with_suffix(".lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = self.read()
            out = fn(data)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False))
            tmp.replace(self.path)
            return out

    def read(self):
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {"pairs": {}, "made": 0, "finished": 0}

    def counts(self):
        d = self.read()
        return {"made": d["made"], "finished": d["finished"]}

    def create(self, name, loves, city="London"):
        def fn(d):
            i = new_id(d["pairs"])
            d["pairs"][i] = {"an": name.strip()[:30], "a": loves, "city": (city or "London").strip()[:40], "created": int(time.time())}
            d["made"] += 1
            return i
        return self._edit(fn)

    def get(self, i):
        p = self.read()["pairs"].get(i) if ID.match(i or "") else None
        if p is None:
            raise NotFound(i)
        return p

    def finish(self, i, name, loves, matcher):
        """Run the Matchmaker for a pair once. A second finish returns the first result and is not counted again."""
        p = self.get(i)
        if p.get("result"):
            return p
        result = matcher(p["a"], loves, p["city"], names=(p["an"] or "A", name.strip()[:30] or "B"))
        if result.get("error") or not result.get("answer") or result.get("problems"):
            return p | {"result": None, "failed": result.get("error") or "; ".join(result.get("problems") or []) or "No answer"}
        def fn(d):
            q = d["pairs"][i]
            if not q.get("result"):
                q.update(bn=name.strip()[:30], b=loves, result=result, finished=int(time.time()))
                d["finished"] += 1
            return q
        return self._edit(fn)

class Redis:
    """The same store on Upstash Redis over its REST API: one key per pair, two counters. The token goes in the
    Authorization header only. SET NX on done:<id> makes a finish count once, however many instances race."""
    def __init__(self, url, token):
        self.url, self.token = url.rstrip("/"), token

    def cmd(self, *args):
        req = urllib.request.Request(self.url, data=json.dumps([str(a) for a in args]).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())["result"]

    def counts(self):
        return {k: int(self.cmd("GET", k) or 0) for k in ("made", "finished")}

    def create(self, name, loves, city="London"):
        p = {"an": name.strip()[:30], "a": loves, "city": (city or "London").strip()[:40], "created": int(time.time())}
        while True:
            i = new_id()
            if self.cmd("SET", f"pair:{i}", json.dumps(p, ensure_ascii=False), "NX"):
                self.cmd("INCR", "made")
                return i

    def get(self, i):
        raw = self.cmd("GET", f"pair:{i}") if ID.match(i or "") else None
        if raw is None:
            raise NotFound(i)
        return json.loads(raw)

    def finish(self, i, name, loves, matcher):
        p = self.get(i)
        if p.get("result"):
            return p
        result = matcher(p["a"], loves, p["city"], names=(p["an"] or "A", name.strip()[:30] or "B"))
        if result.get("error") or not result.get("answer") or result.get("problems"):
            return p | {"result": None, "failed": result.get("error") or "; ".join(result.get("problems") or []) or "No answer"}
        if not self.cmd("SET", f"done:{i}", "1", "NX"):   # someone else finished first: show theirs
            return self.get(i)
        p.update(bn=name.strip()[:30], b=loves, result=result, finished=int(time.time()))
        self.cmd("SET", f"pair:{i}", json.dumps(p, ensure_ascii=False))
        self.cmd("INCR", "finished")
        return p

def public(i, p):
    """What a page may see of a pair: the two sides and the result, never anything else in the store."""
    return {"id": i, "an": p["an"], "a": p["a"], "city": p["city"], "bn": p.get("bn"), "b": p.get("b"),
            "result": p.get("result"), "questions": QUESTIONS}
