"""Public rows paired with Qloo: English Wikipedia pageviews for each villager's love, joined through the Wikidata id
that Qloo search returns (properties.external.wikidata). Both sources are CC0, need no key, and every row keeps the
public URL it came from. Two hops: one Wikidata call for all titles, then one pageviews call per title."""
import datetime, json, os, urllib.error, urllib.parse, urllib.request

WIKIDATA = "https://www.wikidata.org/w/api.php"
PAGEVIEWS = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user"
UA = "taste-village/0.1 (Qloo hackathon demo; https://github.com/Morkeeth/taste-village)"   # Wikimedia asks for a descriptive agent
LICENCE = "CC0 1.0 (Wikimedia analytics data and Wikidata)"

def _base(default, env):
    b = os.environ.get("WIKI_BASE")   # tests point both hops at one fake server
    return (b.rstrip("/") + env) if b else default

def _get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (urllib.error.URLError, TimeoutError, ValueError):
        return 0, {}

def qid(entity):
    """The Wikidata id Qloo search carries, upper-cased (Qloo writes q44190), or None."""
    x = (((entity.get("properties") or {}).get("external") or {}).get("wikidata") or {})
    x = x[0] if isinstance(x, list) and x else x
    v = (x.get("id") if isinstance(x, dict) else x) or ""
    return v.upper() if v[:1] in "qQ" and v[1:].isdigit() else None

def window(today=None):
    """The last 30 complete days, as YYYYMMDD strings."""
    end = (today or datetime.date.today()) - datetime.timedelta(days=1)
    start = end - datetime.timedelta(days=29)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

def rows(qids, today=None):
    """{qid: row}. A qid with no English article or no views gets a row that says so; nothing is invented."""
    qids = [q for q in dict.fromkeys(qids) if q]
    if not qids:
        return {}
    wd_url = _base(WIKIDATA, "/w/api.php") + "?" + urllib.parse.urlencode(
        {"action": "wbgetentities", "ids": "|".join(qids[:50]), "props": "sitelinks", "sitefilter": "enwiki", "format": "json"})
    st, body = _get(wd_url)
    start, end = window(today)
    out = {}
    for q in qids:
        title = (((body.get("entities") or {}).get(q) or {}).get("sitelinks") or {}).get("enwiki", {}).get("title")
        row = {"source": "Wikipedia pageviews", "licence": LICENCE, "wikidata": q, "wikidata_url": f"https://www.wikidata.org/wiki/{q}",
               "title": title, "days": f"{start} to {end}", "views_30d": None, "status": st}
        if title:
            url = _base(PAGEVIEWS, "/pageviews") + "/" + urllib.parse.quote(title.replace(" ", "_"), safe="") + f"/daily/{start}/{end}"
            pst, pv = _get(url)
            items = pv.get("items") or []
            row.update(url=url, status=pst,
                       views_30d=sum(int(i.get("views") or 0) for i in items) if pst == 200 else None)
        out[q] = row
    return out
