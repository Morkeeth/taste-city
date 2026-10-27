"""Build a Qloo-backed taste profile from a public brand website.

The website reader accepts public HTTP(S) URLs only, rejects local/private
addresses, limits downloads, and strips markup. Qloo results are cached outside
git by exact URL. Affinity supports cultural fit, never demand or purchase intent.
"""
from __future__ import annotations

import collections
import datetime
import hashlib
import html.parser
import ipaddress
import json
import os
import pathlib
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

from qloo_client import Live
from taste_city import QlooUnavailable, _call_row, _demographic_entity, _require_ok
from taste_match import MissingKey, short

HERE = pathlib.Path(__file__).resolve().parent
CACHE = (pathlib.Path("/tmp") if os.environ.get("VERCEL") else HERE / "cache") / "brand-profiles"
MAX_BYTES = 750_000
MAX_CALLS = 8
SEARCH_TYPES = ("brand", "place", "artist", "book", "movie")
OUTLETS = (("brands", "brand"), ("music", "artist"), ("film", "movie"), ("places", "place"), ("demographics", "demographics"))
STOP = {
    "about", "after", "again", "also", "been", "brand", "from", "have", "into", "more", "most", "that", "their",
    "there", "these", "they", "this", "with", "your", "what", "when", "where", "which", "will", "home", "menu",
    "privacy", "terms", "contact", "cookies", "copyright", "shop", "store", "learn", "read", "view", "find",
}


class InvalidBrandURL(ValueError):
    pass


class SiteUnavailable(RuntimeError):
    pass


class _PageParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.headings = []
        self.text = []
        self._tag = ""
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        self._tag = tag
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        if tag == "meta":
            data = {key.casefold(): value for key, value in attrs if key and value}
            if data.get("name", "").casefold() == "description" or data.get("property", "").casefold() in ("og:description", "twitter:description"):
                self.description = self.description or data.get("content", "").strip()

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1
        self._tag = ""

    def handle_data(self, data):
        value = " ".join(data.split())
        if not value or self._skip:
            return
        if self._tag == "title":
            self.title = self.title or value
        elif self._tag in ("h1", "h2", "h3") and len(self.headings) < 12:
            self.headings.append(value)
        self.text.append(value)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def normalize_url(value):
    raw = str(value or "").strip()
    if not raw:
        raise InvalidBrandURL("Enter a public brand website URL.")
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise InvalidBrandURL("Use a public http or https URL without credentials.")
    try:
        parsed_port = parsed.port
    except ValueError as error:
        raise InvalidBrandURL("Use a valid public website port.") from error
    port = f":{parsed_port}" if parsed_port else ""
    path = parsed.path or "/"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.hostname.casefold() + port, path, parsed.query, ""))


def _public_host(url, resolver=socket.getaddrinfo):
    host = urllib.parse.urlsplit(url).hostname
    try:
        rows = resolver(host, None)
    except socket.gaierror as error:
        raise SiteUnavailable("The brand website hostname did not resolve.") from error
    addresses = {row[4][0] for row in rows}
    if not addresses:
        raise SiteUnavailable("The brand website hostname did not resolve.")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise InvalidBrandURL("The brand website must use a public internet address.")


def fetch_public_html(value, resolver=socket.getaddrinfo, opener=None):
    url = normalize_url(value)
    opener = opener or urllib.request.build_opener(_NoRedirect())
    for _ in range(4):
        _public_host(url, resolver)
        request = urllib.request.Request(url, headers={"User-Agent": "TasteCityBrandProfile/0.1", "Accept": "text/html,application/xhtml+xml"})
        try:
            response = opener.open(request, timeout=12)
        except urllib.error.HTTPError as error:
            if error.code in (301, 302, 303, 307, 308) and error.headers.get("Location"):
                url = normalize_url(urllib.parse.urljoin(url, error.headers["Location"]))
                continue
            raise SiteUnavailable(f"The brand website returned HTTP {error.code}.") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise SiteUnavailable("The brand website could not be read.") from error
        content_type = response.headers.get_content_type()
        if content_type not in ("text/html", "application/xhtml+xml"):
            raise SiteUnavailable("The URL did not return a web page.")
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise SiteUnavailable("The brand page is too large to profile safely.")
        charset = response.headers.get_content_charset() or "utf-8"
        return url, data.decode(charset, "replace")
    raise SiteUnavailable("The brand website redirected too many times.")


def page_profile(url, html):
    parser = _PageParser()
    parser.feed(html)
    host = urllib.parse.urlsplit(url).hostname or "Brand"
    title = (parser.title or host.split(".")[0]).strip()[:120]
    description = parser.description.strip()[:360]
    visible = " ".join(parser.text)
    words = re.findall(r"[A-Za-z][A-Za-z'-]{3,}", " ".join([title, description, *parser.headings, visible[:12_000]]).casefold())
    counts = collections.Counter(word for word in words if word not in STOP)
    keywords = [word for word, _ in counts.most_common(12)]
    # Headings/keywords are descriptive context, not entity names. The real
    # Monmouth run mapped "About Us" to an unrelated movie. Resolve the named
    # site only; inspect its returned entity before using its relationships.
    named_source = title.split("|")[0].split("–")[0].strip()
    named_source = re.sub(r"^home\s*[-:]\s*", "", named_source, flags=re.I)
    cues = [named_source[:80]] if named_source else []
    return {
        "url": url,
        "title": title,
        "description": description,
        "headings": parser.headings[:6],
        "keywords": keywords,
        "cues": cues,
        "excerpt": visible[:500],
        "content_sha256": hashlib.sha256(html.encode()).hexdigest(),
    }


def cache_path(url, root=None):
    digest = hashlib.sha256(normalize_url(url).encode()).hexdigest()[:20]
    return pathlib.Path(root or os.environ.get("QLOO_BRAND_CACHE") or CACHE) / f"{digest}.json"


def _record(path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"version": 1, "result": result}, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def _fallback(path):
    if not path.exists():
        return None
    result = json.loads(path.read_text()).get("result")
    return ({**result, "mode": "recorded"} if isinstance(result, dict) and result.get("outlets") and result.get("page") else None)


def _archetypes(outlets):
    entities = {row["domain"]: row for row in outlets}
    demo = entities.get("demographics", {}).get("entity", {})
    pairs = (("music", "film"), ("brands", "places"), ("demographics", "music"))
    result = []
    for left_domain, right_domain in pairs:
        rows = [entities[domain] for domain in (left_domain, right_domain) if domain in entities]
        evidence = [{"domain": row["domain"], "name": row["entity"]["name"], "affinity": row["entity"].get("affinity"), "call": row["call"]} for row in rows]
        named = next((row["entity"]["name"] for row in rows if row["domain"] != "demographics"), "culture")
        audience = demo.get("name") or "Qloo audience"
        values = [row["entity"].get("affinity") for row in rows if row["domain"] != "demographics" and row["entity"].get("affinity") is not None]
        strength = round(sum(values) / len(values) * 100) if values else None
        reaction = "Strong match" if strength is not None and strength >= 85 else "Worth a tasting test"
        result.append({
            "name": f"{named} crossovers" if left_domain != "demographics" else f"{audience} tasters",
            "derived_from": [left_domain, right_domain],
            "graph_strength": strength,
            "reaction": reaction,
            "evidence": evidence,
        })
    return result


def _live(page, city, key, base=None):
    qloo = Live(key, base=base, max_calls=MAX_CALLS, pause=0)
    calls, anchors = [], []
    types = ",".join(f"urn:entity:{kind}" for kind in SEARCH_TYPES)
    for cue in page["cues"][:3]:
        call = qloo.get(f"resolve website cue: {cue}", "/search", {"query": cue, "types": types, "take": 3})
        calls.append(call)
        found = _require_ok(call)
        chosen = next((short(entity) for entity in found if entity.get("entity_id") not in {anchor["id"] for anchor in anchors}), None)
        if chosen:
            anchors.append(chosen | {"asked": cue, "call": call["id"]})
    if not anchors:
        raise QlooUnavailable("Qloo did not resolve any public website cue.")
    return _query_profile(page, city, qloo, anchors, calls)


def _query_profile(page, city, qloo, anchors, calls):
    seed_ids = ",".join(anchor["id"] for anchor in anchors)
    outlets = []
    for domain, entity_type in OUTLETS:
        filter_type = "urn:demographics" if entity_type == "demographics" else f"urn:entity:{entity_type}"
        params = {"filter.type": filter_type, "signal.interests.entities": seed_ids, "take": 5}
        if entity_type == "place":
            params["filter.location.query"] = city
        call = qloo.get(f"brand profile {domain}", "/v2/insights", params)
        calls.append(call)
        found = _require_ok(call)
        entity = _demographic_entity(call) if entity_type == "demographics" else (short(found[0]) if found else None)
        if entity:
            outlets.append({"domain": domain, "entity": entity, "call": call["id"]})
    if len(outlets) < 4:
        raise QlooUnavailable("Qloo returned too few domains for a brand taste profile.")
    return {
        "mode": "live",
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "page": page,
        "city": city,
        "anchors": anchors,
        "outlets": outlets,
        "archetypes": _archetypes(outlets),
        "calls": [_call_row(call) for call in calls],
        "notice": "Qloo affinity describes cultural fit. It does not predict demand, conversion, or purchase intent.",
    }



def confirm_anchors(profile, approved_ids, env=None, base=None):
    """Explicit selection followed by five insights calls, never new searches."""
    env = os.environ if env is None else env
    approved = set(approved_ids or [])
    known = {a['id'] for a in profile.get('anchors', [])}
    if not approved or not approved.issubset(known):
        raise ValueError('Choose at least one proposed source entity; unknown IDs are refused.')
    key = env.get('QLOO_API_KEY')
    if not key:
        raise MissingKey('A configured server key is required to query the confirmed references.')
    anchors = [{**a, 'call':'source:'+a['call']} for a in profile['anchors'] if a['id'] in approved]
    source_calls = [{**c, 'id':'source:'+c['id']} for c in profile['calls'] if any(c['id']==a['call'].removeprefix('source:') for a in anchors)]
    qloo = Live(key, base=base, max_calls=5, pause=0)
    result = _query_profile(profile['page'], profile['city'], qloo, anchors, source_calls)
    result['anchor_confirmation'] = {'approved_ids':sorted(approved), 'source_recorded_at':profile['recorded_at'], 'notice':'Selected source entities, not measured customer tastes.'}
    return result


def build(url, city="London", env=None, cache_root=None, base=None, prefer_cache=True, fetcher=fetch_public_html):
    env = os.environ if env is None else env
    url = normalize_url(url)
    path = cache_path(url, cache_root)
    cached = _fallback(path)
    if prefer_cache and cached:
        return cached
    if env.get("QLOO_TASTE_OFFLINE") == "1":
        if cached:
            return cached
        raise QlooUnavailable("No recorded brand profile exists for this URL.")
    key = env.get("QLOO_API_KEY")
    if not key:
        if cached:
            return cached
        raise MissingKey("Set QLOO_API_KEY in the process environment and start again.")
    final_url, html = fetcher(url)
    result = _live(page_profile(final_url, html), str(city or "London")[:80], key, base=base or env.get("QLOO_BASE"))
    _record(path, result)
    return result
