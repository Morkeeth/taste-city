"""Carry server-checked local evidence between functions without another provider lookup.

Signed with a purpose-derived server key, never a browser-supplied evidence claim.
The token is short-lived planning context, not authentication or a booking.
"""
import base64
import copy
import hashlib
import hmac
import json
import os
import time

class InvalidLocalContext(ValueError):
    pass

FIELDS = ('mode','recorded_at','city','picks','anchors','outlets','calls','http_reads','local_area','nearby_places')

def _key(env):
    value = env.get('QLOO_API_KEY')
    if not value:
        raise InvalidLocalContext('Local planning evidence is unavailable. Refresh the local search.')
    return hmac.new(value.encode(), b'taste-city/local-context/v1', hashlib.sha256).digest()

def issue(graph, env=None, now=None):
    env = os.environ if env is None else env
    now = int(time.time() if now is None else now)
    payload = {'v':1,'issued':now,'expires':now+3600,'graph':{k:graph.get(k) for k in FIELDS}}
    raw = json.dumps(payload,separators=(',',':'),ensure_ascii=False).encode()
    if graph.get('mode') not in ('live','recorded') or not graph.get('local_area') or not graph.get('nearby_places') or len(raw)>28000:
        raise InvalidLocalContext('No usable local planning evidence. Try the search again.')
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip('=')
    return encoded+'.'+hmac.new(_key(env),encoded.encode(),hashlib.sha256).hexdigest()

def read(token, env=None, now=None):
    env = os.environ if env is None else env
    now = int(time.time() if now is None else now)
    try:
        if not isinstance(token,str) or len(token)>40000:
            raise ValueError()
        encoded,signature=token.split('.')
        expected=hmac.new(_key(env),encoded.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature,expected):
            raise ValueError()
        payload=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
        if payload['v']!=1 or not payload['issued']<=now<payload['expires'] or payload['expires']-payload['issued']!=3600:
            raise ValueError()
        return payload['graph']
    except Exception:
        raise InvalidLocalContext('Local evidence expired or changed. Run the local search again.') from None

def for_request(body, env=None, now=None):
    """Core planning must select real IDs from this exact, signed audience search."""
    if body.get('demo') is True:
        import sample_demo
        try:
            graph=sample_demo.local_discovery({'picks':body.get('picks'),'city':'London'})
        except ValueError:
            raise InvalidLocalContext('The fictional sample uses its three labelled example tastes.') from None
    else:
        graph=read(body.get('planning_token'),env,now)
    import taste_city
    try:
        picks=taste_city.clean_picks(body.get('picks'))
    except ValueError:
        raise InvalidLocalContext('Choose three audience tastes and run the local search first.') from None
    if picks != graph['picks']:
        raise InvalidLocalContext('Audience changed. Search local places for these tastes first.')
    ids=body.get('selected_place_ids')
    if not isinstance(ids,list) or not 1<=len(ids)<=3 or any(not isinstance(x,str) for x in ids) or len(set(ids))!=len(ids):
        raise InvalidLocalContext('Choose one to three places from your local results.')
    places={p['id']:p for p in graph['nearby_places']}
    if any(x not in places for x in ids):
        raise InvalidLocalContext('That place is outside this local result. Choose again.')
    selected=[copy.deepcopy(places[x]) for x in ids]
    return {'graph':copy.deepcopy(graph),'area':copy.deepcopy(graph['local_area']),'places':selected,'mode':graph['mode'],'recorded_at':graph.get('recorded_at'),'notice':('Fictional places and illustrative distances only. No provider inference or real-world verification.' if graph['mode']=='synthetic' else 'Coordinates checked against the search radius, not opening hours, availability, rights or suitability.')}

def graph_for(context, body):
    graph=copy.deepcopy(context['graph'])
    graph['profile']=None
    graph['planning_profile']=f"{body['flow']}:{body['experiment']}"
    graph['shared_local_graph']=True
    return graph

def public(context):
    return {k:copy.deepcopy(context[k]) for k in ('area','places','mode','recorded_at','notice')}


def place_filter(context):
    from urllib.parse import urlparse, parse_qs
    for call in reversed(context['graph'].get('calls') or []):
        query=parse_qs(urlparse(call.get('url') or '').query)
        if query.get('filter.location') and query.get('filter.location.radius'):
            return {'filter.location':query['filter.location'][0], 'filter.location.radius':int(query['filter.location.radius'][0])}
    raise InvalidLocalContext('Local search geometry is missing. Refresh the search.')
