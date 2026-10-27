"""Small capped Qloo HTTP client used by the public Taste City source.

The API key is sent only in the X-Api-Key header. It is never added to a URL,
response record, or log line.
"""
import json
import os
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://hackathon.api.qloo.com"
MAX_CALLS = 20
RETRIES = 5


class BudgetSpent(Exception):
    pass


class Live:
    def __init__(self, key, base=None, max_calls=MAX_CALLS, pause=0.5, max_http_reads=None):
        if not key:
            raise ValueError("no key")
        self.key = key
        self.base = (base or os.environ.get("QLOO_BASE") or BASE).rstrip("/")
        self.max_calls = max_calls
        self.pause = pause
        self.n = 0
        self.http_reads = 0
        self.max_http_reads = max_http_reads
        self.lock = threading.Lock()

    def get(self, purpose, path, params):
        with self.lock:
            if self.n >= self.max_calls:
                raise BudgetSpent(f"live call cap {self.max_calls} reached")
            self.n += 1
            call_id = f"L{self.n:02d}"
        url = self.base + path + "?" + urllib.parse.urlencode(params, safe=":,")
        req = urllib.request.Request(
            url,
            headers={"X-Api-Key": self.key, "User-Agent": "taste-village/0.1"},
        )
        for attempt in range(RETRIES + 1):   # the hackathon key is rate limited: back off on 429, same call ID
            with self.lock:
                if self.max_http_reads is not None and self.http_reads >= self.max_http_reads:
                    raise BudgetSpent(f"HTTP read cap {self.max_http_reads} reached")
                self.http_reads += 1
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    status = response.status
                    body = json.loads(response.read() or b"{}")
            except urllib.error.HTTPError as error:
                status = error.code
                body = {"http_error": error.code, "body": error.read().decode("utf-8", "replace")[:500]}
            except (urllib.error.URLError, TimeoutError, ValueError) as error:
                status = 0
                body = {"error": type(error).__name__}
            if status != 429:
                break
            time.sleep(0.5 * 2 ** attempt + random.random() * 0.3)
        time.sleep(self.pause)
        return {
            "id": call_id,
            "purpose": purpose,
            "url": url,
            "status": status,
            "response": body,
            "live": True,
        }
