"""Resolve a user-supplied area and verify Qloo place coordinates locally."""
import json
import math
import urllib.parse
import urllib.request

class LocationInvalid(ValueError):
    pass

class LocationUnavailable(RuntimeError):
    pass

def resolve_area(query):
    if not isinstance(query, str) or not query.strip() or len(query.strip()) > 160:
        raise LocationInvalid('Enter an address or postcode, with its city or country.')
    url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode({'q': query.strip(), 'format': 'jsonv2', 'limit': 1})
    req = urllib.request.Request(url, headers={'User-Agent': 'TasteCity/1.0 (https://taste-city.vercel.app)', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            rows = json.loads(response.read())
        if not rows:
            raise LocationInvalid('No matching address was found. Add its city or country and try again.')
        row = rows[0]
        lat, lon = float(row['lat']), float(row['lon'])
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError('coordinates')
        return {'lat': lat, 'lon': lon, 'label': str(row.get('display_name') or query)[:240], 'source': 'OpenStreetMap Nominatim'}
    except LocationInvalid:
        raise
    except Exception:
        raise LocationUnavailable('Address lookup is temporarily unavailable. Try again shortly.') from None

def radius_metres(value):
    if isinstance(value, bool):
        raise LocationInvalid('Choose a search radius from 500 to 1500 metres.')
    try:
        radius = int(value)
        if float(value) != radius or not 500 <= radius <= 1500:
            raise ValueError('radius')
        return radius
    except (ValueError, TypeError, OverflowError):
        raise LocationInvalid('Choose a search radius from 500 to 1500 metres.') from None

def distance_metres(area, entity):
    location = entity.get('location') or {}
    try:
        lat, lon = float(location['lat']), float(location['lon'])
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            return None
        a, b = math.radians(area['lat']), math.radians(lat)
        dlat, dlon = b-a, math.radians(lon-area['lon'])
        h = math.sin(dlat/2)**2 + math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
        return 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, h))))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def within_popularity_cap(entity, maximum=0.5):
    value = entity.get('popularity')
    if isinstance(value, bool):
        return False
    try:
        return 0 <= float(value) <= maximum
    except (TypeError, ValueError, OverflowError):
        return False
