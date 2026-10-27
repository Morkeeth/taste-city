"""The Taste City universe from recorded Qloo calls.

Raw Qloo responses stay outside git. Set HIPSTER_QLOO_FIXTURE when the fixture
is not in the historical sibling location.
"""
import json, os, pathlib

HERE = pathlib.Path(__file__).resolve().parent
FIXTURE = pathlib.Path(os.environ.get(
    "HIPSTER_QLOO_FIXTURE",
    HERE.parent / "live" / "slice1-core-20261015.json",
))
TAG_TYPES = ("urn:tag:genre:music", "urn:tag:genre:qloo", "urn:tag:audience:qloo")

def entities(call):
    r = call.get("response") or {}
    res = r.get("results") if isinstance(r, dict) else None
    return (res.get("entities") if isinstance(res, dict) else res) or []

def load(path=FIXTURE):
    """Returns {entity_id: {...}}. neighbours: the other artists that share a Qloo similar-artist list with it."""
    if not pathlib.Path(path).exists():
        raise FileNotFoundError(
            f"Qloo fixture not found at {path}. Set HIPSTER_QLOO_FIXTURE to the recorded slice."
        )
    calls = json.load(open(path))["calls"]
    out, lists = {}, []
    for c in calls:
        if not c["purpose"].startswith("similar: "):
            continue
        ids = []
        for rank, e in enumerate(entities(c), 1):
            eid = e["entity_id"]
            if eid not in out:
                out[eid] = {"id": eid, "name": e["name"], "wikidata": (e.get("external") or {}).get("wikidata", [{}])[0].get("id"),
                            "popularity": e.get("popularity"),
                            "tags": sorted({t["name"].lower() for t in e.get("tags", []) if t.get("type") in TAG_TYPES}),
                            "seen_in": [], "neighbours": set()}
            out[eid]["seen_in"].append({"call": c["id"], "anchor": c["purpose"][9:], "rank": rank})
            ids.append(eid)
        lists.append(ids)
    for ids in lists:
        for a in ids:
            out[a]["neighbours"].update(b for b in ids if b != a)
    for e in out.values():
        e["neighbours"] = sorted(e["neighbours"])
    return out
