"""Grade the frozen next-week calls. Run after the check week ends:
python3 check_predictions.py ~/.local/state/fleet/pages-data/HIPSTER-V2/predictions-20261019.json
Fetches English Wikipedia daily pageviews (no key) for the check week, Monday to Sunday, and applies the frozen rule."""
import datetime as dt, json, sys, urllib.parse
import fetch

def grade(pred, daily):
    end = dt.date.fromisoformat(pred["check_week"])
    days = [(end - dt.timedelta(6 - i)).strftime("%Y%m%d") for i in range(7)]
    if not all(d in daily for d in days):
        return {"artist": pred["artist"], "result": "not yet", "days_found": sum(d in daily for d in days)}
    total = sum(daily[d] for d in days)
    return {"artist": pred["artist"], "views": total, "needs": pred["needs_views"], "result": "called it" if total >= pred["needs_views"] else "missed"}

def main(path):
    frozen = json.loads(open(path).read())
    for aid, p in frozen["predictions"].items():
        if not p or not p.get("wikipedia"):
            print(aid, "no prediction or no title"); continue
        end = dt.date.fromisoformat(p["check_week"])
        art = urllib.parse.quote(p["wikipedia"].replace(" ", "_"), safe="")
        url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
               f"{art}/daily/{(end - dt.timedelta(6)).strftime('%Y%m%d')}00/{end.strftime('%Y%m%d')}00")
        status, body = fetch.get(url)
        daily = {it["timestamp"][:8]: it["views"] for it in body.get("items", [])}
        print(aid, json.dumps(grade(p, daily), ensure_ascii=False))

if __name__ == "__main__":
    main(sys.argv[1])
