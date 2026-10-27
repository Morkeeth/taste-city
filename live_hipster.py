"""Oscar's one live command for Hipster. 13 Qloo calls, under the demo's 20-call cap. Not run by any agent.
  cd ~/CODE/hack-proofs/qloo && python3 hipster/live_hipster.py
1 call: /v2/trending, the endpoint hack.md (RESEARCH 17 Oct) says decides the trend radar. Params are from the docs, unverified live.
12 calls: per archetype, one /search for a cross-domain anchor and one /v2/insights for what that tribe also loves.
Writes hipster/cache/live-<time>.json (gitignored). The key is read from QLOO_API_KEY and never written."""
import json, os, pathlib, sys, time

HERE = pathlib.Path(__file__).resolve().parent
import qloo_client as live

MOBY = os.environ.get("HIPSTER_MOBY_ID", "HIPSTER_MOBY_ID")   # the Qloo entity ID for Moby; an ID is not a key, but no Qloo ID lives in git
TRENDING = ("trending: artists among Moby fans", "/v2/trending",
            {"filter.type": "urn:entity:artist", "signal.interests.entities": MOBY,
             "filter.start_date": "2026-04-01", "filter.end_date": "2026-10-12", "take": 20})
ANCHORS = [  # archetype id, search query, Qloo type of the anchor, type to ask for next
    ("digger", "Technics", "urn:entity:brand", "urn:entity:brand"),
    ("monk", "Berghain", "urn:entity:place", "urn:entity:brand"),
    ("poet", "Dr. Martens", "urn:entity:brand", "urn:entity:brand"),
    ("romantic", "Urban Outfitters", "urn:entity:brand", "urn:entity:book"),
    ("sneaker", "Nike", "urn:entity:brand", "urn:entity:brand"),
    ("wine", "Noble Rot", "urn:entity:place", "urn:entity:place"),
]
PLANNED_CALLS = 1 + 2 * len(ANCHORS)

def first_id(call):
    res = call["response"].get("results") if isinstance(call["response"], dict) else None
    hits = res.get("entities", []) if isinstance(res, dict) else (res or [])
    return (hits[0]["entity_id"], hits[0].get("name")) if hits else (None, None)

def run(client):
    calls = [client.get(*TRENDING)]
    for aid, query, qtype, want in ANCHORS:
        s = client.get(f"search: {query} ({aid})", "/search", {"query": query, "types": qtype, "take": 1})
        calls.append(s)
        eid, _ = first_id(s)
        if eid:
            calls.append(client.get(f"tribe {aid}: {want} for {query}", "/v2/insights",
                                    {"filter.type": want, "signal.interests.entities": eid, "take": 10}))
    return calls

if __name__ == "__main__":
    key = os.environ.get("QLOO_API_KEY")
    if not key:
        sys.exit("QLOO_API_KEY is not set. No call made.")
    if MOBY == "HIPSTER_MOBY_ID":
        sys.exit("HIPSTER_MOBY_ID is not set. No call made.")
    client = live.Live(key)
    calls = run(client)
    out = HERE / "cache" / f"live-{time.strftime('%Y%m%d-%H%M')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"base": client.base, "calls": calls}, indent=1))
    for c in calls:
        print(f"{c['status']:>3} {c['purpose']}")
    print(f"{client.n} calls (cap {client.max_calls}), written to {out}")
