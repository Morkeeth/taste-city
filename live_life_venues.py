"""Second pass for archetypes whose London places came back generic (landmarks, offices).
Same seeds as live_life.py, places filtered by a Qloo place genre tag. Appends to cache/life.json. 4 calls."""
import json, os, subprocess, pathlib
import backtest, radar, live_life

RERUN = [("romantic", "cafe"), ("romantic", "bar"), ("wine", "wine_bar"), ("wine", "restaurant")]

def main():
    key = os.environ.get("QLOO_API_KEY") or subprocess.check_output(["security", "find-generic-password", "-s", "QLOO_API_KEY", "-a", "qloo-hackathon", "-w"], text=True).strip()
    path = live_life.HERE / "cache" / "life.json"
    d = json.loads(path.read_text())
    call, log = live_life.client(key)
    for aid, genre in RERUN:
        ids = [x["id"] for x in d["archetypes"][aid]["anchors"]]
        c = call(f"{aid} place {genre}", {"filter.type": "urn:entity:place", "signal.interests.entities": ",".join(ids),
                                          "filter.location.query": live_life.CITY, "filter.tags": f"urn:tag:genre:place:{genre}", "take": 6})
        c["id"] = f"L{len(d['calls']) + 1:02}"
        d["calls"].append(c)
        d["archetypes"][aid]["calls"][f"place_{genre}"] = c["id"]
    path.write_text(json.dumps(d, indent=1))

if __name__ == "__main__":
    main()
