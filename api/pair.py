"""The share loop over HTTP. Vercel runs this file as a Python function; match_app.py runs the same handler locally.
POST /api/pair {"an", "a": [3 answers], "city"}            -> {"id", "path"}; counts one link made
GET  /api/pair?id=xxxxxx                                   -> the pair (404 for an id that is not in the store)
POST /api/pair {"id", "bn", "b": [3 answers]}             -> runs the Matchmaker once, stores it; counts one finish
GET  /api/pair?counts=1                                    -> {"made", "finished"}"""
import json, os, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pair, taste_match
from api.match import handler as Base

class handler(Base):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        s = pair.open_store()
        if q.get("counts"):
            return self.reply(200, s.counts())
        i = (q.get("id") or [""])[0]
        try:
            return self.reply(200, pair.public(i, s.get(i)))
        except pair.NotFound:
            return self.reply(404, {"error": "No pair with that link. Ask your friend to send it again."})

    def do_POST(self):
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 4000)
            req = json.loads(self.rfile.read(n) or b"{}")
            s = pair.open_store()
            if req.get("id") is None:
                a = pair.answers(req.get("a"))
                if not a:
                    return self.reply(400, {"error": "Answer at least one question first."})
                i = s.create(str(req.get("an") or ""), a, str(req.get("city") or "London"))
                return self.reply(200, {"id": i, "path": f"/pair/{i}"})
            i, b = str(req["id"]), pair.answers(req.get("b"))
            if not b:
                return self.reply(400, {"error": "Answer at least one question first."})
            p = s.finish(i, str(req.get("bn") or ""), b, taste_match.match)
            if p.get("failed"):
                return self.reply(502, {"error": p["failed"]})
            return self.reply(200, pair.public(i, p))
        except pair.NotFound:
            return self.reply(404, {"error": "No pair with that link. Ask your friend to send it again."})
        except taste_match.MissingKey as e:   # the message names the variable, never a value
            return self.reply(503, {"error": str(e)})
        except Exception as e:
            return self.reply(500, {"error": f"{type(e).__name__}: the match failed, try again."})
