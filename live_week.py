"""More Qloo taste for the week view: 25 London places and 8 artists per archetype. Appends to cache/life.json. 12 calls.
Key from QLOO_API_KEY, else the macOS keychain; never printed or written."""
import json, os, subprocess
import live_life

def main():
    key = os.environ.get("QLOO_API_KEY") or subprocess.check_output(
        ["security", "find-generic-password", "-s", "QLOO_API_KEY", "-a", "qloo-hackathon", "-w"], text=True).strip()
    path = live_life.HERE / "cache" / "life.json"
    d = json.loads(path.read_text())
    call, log = live_life.client(key)
    for aid, a in d["archetypes"].items():
        seed = ",".join(x["id"] for x in a["anchors"])
        for name, params in (("places25", {"filter.type": "urn:entity:place", "filter.location.query": live_life.CITY, "take": 25}),
                             ("artists", {"filter.type": "urn:entity:artist", "take": 8})):
            c = call(f"{aid} {name}", {**params, "signal.interests.entities": seed})
            c["id"] = f"L{len(d['calls']) + 1:02}"
            d["calls"].append(c); a["calls"][name] = c["id"]
            path.write_text(json.dumps(d, indent=1))

if __name__ == "__main__":
    main()
