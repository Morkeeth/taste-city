"""Turn three tap-card choices into a Qloo-backed city response.

The key is read from QLOO_API_KEY only. Successful results are recorded under
cache/taste-city/ (gitignored) and become the exact-choice fallback when Qloo
is unavailable. Cached files never contain the key.
"""
import datetime
import hashlib
import json
import os
import pathlib

from qloo_client import Live, BudgetSpent
from local_places import resolve_area, radius_metres, distance_metres, within_popularity_cap, LocationUnavailable
from taste_match import MissingKey, entities, short

HERE = pathlib.Path(__file__).resolve().parent
CACHE = (pathlib.Path("/tmp") if os.environ.get("VERCEL") else HERE / "cache") / "taste-city"
OUTLETS = (
    ("echo", "music", "artist"),
    ("frame", "film", "movie"),
    ("spoon", "food", "place"),
    ("margin", "books", "book"),
    ("atlas", "places", "destination"),
)
SCENARIO_PLANS = {
    "brand:popup": ("music", "film", "food", "demographics"),
    "brand:flavour": ("food", "brand", "books", "demographics"),
    "brand:event": ("music", "film", "food", "demographics"),
    "brand:merch": ("brand", "books", "music", "demographics"),
    "festival:lineup": ("music", "film", "places", "demographics"),
    "festival:sponsor": ("brand", "music", "places", "demographics"),
    "festival:food": ("food", "brand", "places", "demographics"),
    "festival:night": ("music", "film", "food", "demographics"),
}
DOMAIN_TYPES = {
    "music": "artist", "film": "movie", "food": "place",
    "books": "book", "places": "destination", "brand": "brand",
    "demographics": "demographics",
}
SEARCH_TYPES = ("artist", "movie", "tv_show", "book", "brand", "podcast", "videogame", "place", "destination")
CALL_CAP = 8
FOOD_GENRES = ("restaurant",)


class InvalidTaste(ValueError):
    pass


class QlooUnavailable(RuntimeError):
    pass


def clean_picks(picks):
    out = []
    for value in picks or []:
        value = str(value).strip()[:80]
        if value and value.casefold() not in {x.casefold() for x in out}:
            out.append(value)
    if len(out) != 3:
        raise InvalidTaste("Choose exactly three different taste cards.")
    return out


def cache_path(picks, city="London", root=None, profile=None):
    payload = json.dumps({
        "picks": clean_picks(picks),
        "city": city.strip()[:80] or "London",
        "profile": profile or "legacy",
    }, sort_keys=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:20]
    return pathlib.Path(root or os.environ.get("QLOO_TASTE_CACHE") or CACHE) / f"{digest}.json"


def _call_row(call):
    return {k: call.get(k) for k in ("id", "purpose", "status", "url")}


def _require_ok(call):
    if call.get("status") != 200:
        raise QlooUnavailable(f"Qloo returned HTTP {call.get('status') or 0}.")
    return entities(call)


def place_genre(entity):
    """Return Qloo's primary place genre, never a secondary attraction tag."""
    primary = (entity.get("properties") or {}).get("primary_genre") or {}
    if isinstance(primary, dict):
        genre = primary.get("id") or primary.get("name") or ""
        prefix = "urn:tag:genre:place:"
        genre = genre[len(prefix):] if genre.startswith(prefix) else genre
        if genre:
            return genre.strip().lower().replace(" ", "_")
    return ""


def is_food_place(entity):
    genre = place_genre(entity)
    return bool(genre and any(token in genre for token in FOOD_GENRES))


def food_candidate_log(entities_list):
    """Safe fields used to verify Qloo's live place genre shape. Never a key."""
    rows = []
    for entity in entities_list:
        properties = entity.get("properties") or {}
        rows.append({
            "id": entity.get("entity_id"),
            "name": entity.get("name"),
            "types": entity.get("types") or [],
            "subtype": entity.get("subtype"),
            "primary_genre": {
                key: (properties.get("primary_genre") or {}).get(key)
                for key in ("id", "name", "type")
            } if isinstance(properties.get("primary_genre"), dict) else properties.get("primary_genre"),
            "property_keys": sorted(properties),
            "genre_tags": [
                {key: tag.get(key) for key in ("id", "name", "type")}
                for tag in (entity.get("tags") or [])
                if ":genre:place:" in str(tag.get("id") or "") or ":category:place:" in str(tag.get("id") or "")
            ],
        })
    return rows


def _write_food_diagnostics(path, call, found):
    if not path:
        return
    destination = pathlib.Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({
        "call": call.get("id"),
        "purpose": call.get("purpose"),
        "status": call.get("status"),
        "candidates": food_candidate_log(found),
    }, ensure_ascii=False, indent=2) + "\n")


def _valid_result(result):
    food = next((row for row in result.get("outlets") or [] if row.get("domain") == "food"), None)
    genre = str((food or {}).get("entity", {}).get("genre") or "")
    if food is None:
        return bool(result.get("outlets"))
    return bool(genre and any(token in genre for token in FOOD_GENRES))


def _record(path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"version": 1, "result": result}, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def _fallback(path):
    if not path.exists():
        return None
    result = json.loads(path.read_text()).get("result")
    if not isinstance(result, dict) or not result.get("outlets") or not _valid_result(result):
        return None
    return {**result, "mode": "recorded"}


def _demographic_entity(call):
    rows = (((call.get("response") or {}).get("results") or {}).get("demographics") or [])
    query = (rows[0].get("query") or {}) if rows else {}
    age = query.get("age") or {}
    gender = query.get("gender") or {}
    age_band, age_score = max(age.items(), key=lambda item: item[1], default=("unknown age", None))
    gender_band, gender_score = max(gender.items(), key=lambda item: item[1], default=("no gender skew", None))
    label = f"{age_band.replace('_', ' ')}; {gender_band.replace('_', ' ')}"
    return {
        "name": label,
        "id": None,
        "type": "demographics",
        "affinity": age_score,
        "age": age,
        "gender": gender,
        "gender_skew": gender_score,
    }


def _scenario_outlets(profile):
    if not profile:
        return OUTLETS
    if profile not in SCENARIO_PLANS:
        raise InvalidTaste("Choose a valid scenario profile.")
    return tuple((f"scenario-{index}", domain, DOMAIN_TYPES[domain]) for index, domain in enumerate(SCENARIO_PLANS[profile], 1))


def _live(picks, city, key, base=None, diagnostics_path=None, profile=None, http_cap=None, local_area=None, radius=1000, discovery=False, core=False):
    qloo = Live(key, base=base, max_calls=9 if core else CALL_CAP, pause=0, max_http_reads=9 if core else http_cap)
    calls, anchors = [], []
    types = ",".join(f"urn:entity:{kind}" for kind in SEARCH_TYPES)
    for pick in picks:
        call = qloo.get(f"resolve {pick}", "/search", {"query": pick, "types": types, "take": 1})
        calls.append(call)
        found = _require_ok(call)
        if not found:
            raise QlooUnavailable(f"Qloo did not resolve {pick}.")
        anchors.append(short(found[0]) | {"asked": pick, "call": call["id"]})

    seed_ids = ",".join(anchor["id"] for anchor in anchors)
    outlets, used_types = [], {}
    nearby_places = []
    for outlet_id, domain, entity_type in _scenario_outlets(profile):
        filter_type = "urn:demographics" if entity_type == "demographics" else f"urn:entity:{entity_type}"
        params = {"filter.type": filter_type, "signal.interests.entities": seed_ids, "take": 5}
        if entity_type == "place":
            if local_area:
                params['filter.location'] = f"POINT({local_area['lon']} {local_area['lat']})"
                params['filter.location.radius'] = radius
                params['take'] = 25
                if discovery:
                    params['filter.popularity.max'] = 0.5
            else:
                params["filter.location.query"] = city
            params["filter.tags"] = "urn:tag:genre:place:restaurant"
        call = qloo.get(f"fill {domain} outlet", "/v2/insights", params)
        calls.append(call)
        if entity_type == "demographics":
            _require_ok(call)
            outlets.append({
                "id": outlet_id,
                "domain": domain,
                "entity": _demographic_entity(call),
                "call": call["id"],
                "source_entities": [{"id": anchor["id"], "name": anchor["name"]} for anchor in anchors],
            })
            continue
        found = _require_ok(call)
        if not found:
            if core and entity_type == "place":
                continue
            raise QlooUnavailable(f"Qloo returned no {domain} entity.")
        if entity_type == "place":
            _write_food_diagnostics(diagnostics_path, call, found)
        result_index = used_types.get(entity_type, 0)
        used_types[entity_type] = result_index + 1
        if entity_type == "place":
            candidates = [entity for entity in found if is_food_place(entity)]
            if local_area:
                candidates = [entity for entity in candidates if entity.get("entity_id") and (not discovery or within_popularity_cap(entity)) and (distance_metres(local_area, entity) is not None and distance_metres(local_area, entity) <= radius)]
                seen = set()
                for entity in candidates:
                    entity_id = entity.get('entity_id')
                    if not entity_id or entity_id in seen:
                        continue
                    seen.add(entity_id)
                    nearby_places.append(short(entity) | {'distance_m': round(distance_metres(local_area, entity)), 'call': call['id'], 'why': 'Qloo taste connection to your three choices', 'popularity': entity.get('popularity')})
                nearby_places = nearby_places[:5]
            chosen = next(iter(candidates), None)
            if not chosen:
                if core:
                    continue
                raise QlooUnavailable(f"No matching restaurant was found within {radius} metres. Try a larger radius or turn off less mainstream discovery." if local_area else "Qloo returned no restaurant-typed food entity.")
        else:
            chosen = found[result_index] if result_index < len(found) else found[0]
        shaped = short(chosen)
        if entity_type == "place":
            shaped["genre"] = place_genre(chosen)
            if local_area:
                shaped["distance_m"] = round(distance_metres(local_area, chosen))
        outlets.append({
            "id": outlet_id,
            "domain": domain,
            "entity": shaped,
            "call": call["id"],
            "source_entities": [{"id": anchor["id"], "name": anchor["name"]} for anchor in anchors],
        })

    if core:
        params = {'filter.type':'urn:entity:place', 'signal.interests.entities':seed_ids,
                  'filter.location':f"POINT({local_area['lon']} {local_area['lat']})",
                  'filter.location.radius':radius, 'take':25}
        if discovery:
            params['filter.popularity.max']=0.5
        call=qloo.get('local places for this audience','/v2/insights',params)
        calls.append(call)
        nearby_places=[]
        seen=set()
        for entity in _require_ok(call):
            distance=distance_metres(local_area,entity)
            eid=entity.get('entity_id')
            if not eid or eid in seen or distance is None or distance>radius or (discovery and not within_popularity_cap(entity)):
                continue
            seen.add(eid)
            nearby_places.append(short(entity) | {'genre':place_genre(entity), 'distance_m':round(distance),
                'call':call['id'],'why':'Qloo connects this place to the three selected audience tastes',
                'popularity':entity.get('popularity')})
        nearby_places=nearby_places[:5]
        if not nearby_places:
            raise QlooUnavailable('No coordinate-checked places matched this audience and radius. Change the radius or discovery filter.')

    return {
        "mode": "live",
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "city": city,
        "picks": picks,
        "profile": profile,
        "anchors": anchors,
        "outlets": outlets,
        "calls": [_call_row(call) for call in calls],
        "http_reads": qloo.http_reads,
        "local_area": ({"label": local_area["label"], "source": local_area["source"], "radius_m": radius, "popularity_cap": 0.5 if discovery else None} if local_area else None),
        "nearby_places": nearby_places,
    }


def build(picks, city="London", env=None, cache_root=None, base=None, prefer_cache=False, profile=None, local=False, radius=1000, discovery=True, core=False):
    """Use live Qloo once, then exact-choice cache on an unavailable network.

    QLOO_TASTE_OFFLINE=1 forces the recorded path. No keychain access exists
    here: callers must put QLOO_API_KEY in this process environment.
    """
    env = os.environ if env is None else env
    picks = clean_picks(picks)
    if local:
        if profile:
            raise InvalidTaste('Local discovery is a personal discovery option.')
        if not isinstance(city, str) or not city.strip() or len(city.strip()) > 160:
            raise InvalidTaste('Enter an address or postcode, with its city or country.')
        radius = radius_metres(radius)
        if not isinstance(discovery, bool):
            raise InvalidTaste('Choose whether to explore less mainstream places.')
    city = str(city or "London").strip()[:160 if local else 80] or "London"
    path = cache_path(picks, city, cache_root, profile=({"local_v": 2 if core else 1, "query": city, "radius": radius, "discovery": discovery} if local else profile))
    cached = _fallback(path)
    if prefer_cache and cached:
        return cached
    if env.get("QLOO_TASTE_OFFLINE") == "1":
        if cached:
            return cached
        raise QlooUnavailable("No recorded Qloo response exists for these three choices.")
    key = env.get("QLOO_API_KEY")
    if not key:
        if cached:
            return cached
        raise MissingKey("Set QLOO_API_KEY in the process environment and start again.")
    try:
        result = _live(
            picks, city, key, base=base or env.get("QLOO_BASE"),
            diagnostics_path=env.get("QLOO_TASTE_DIAGNOSTICS"),
            profile=profile,
            local_area=resolve_area(city) if local else None, radius=radius, discovery=discovery, core=core,
        )
        _record(path, result)
        return result
    except (QlooUnavailable, LocationUnavailable, BudgetSpent):
        if cached:
            return cached
        raise
