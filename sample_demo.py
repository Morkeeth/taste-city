"""Clearly fictional, tracked demo data for a fresh public checkout.

These names and affinity values are hand-authored examples. They are not Qloo
responses, do not carry provider provenance, and must never enter live mode.
"""
import scenario_engine
import taste_city

DEFAULT_PICKS = ('Björk', 'Radiohead', 'Little Simz')
EXAMPLES = {
    'music': ('Example Night Radio', 'artist', .78),
    'film': ('Example Midnight Cinema', 'movie', .73),
    'food': ('Example Corner Café', 'restaurant:cafe', .69),
    'books': ('Example Small Press', 'book', .64),
    'places': ('Example River Quarter', 'destination', .70),
    'brand': ('Example Studio Goods', 'brand', .67),
    'demographics': ('Example age skew', 'demographics', None),
}


def graph(body):
    request = scenario_engine.clean_request(body)
    picks = taste_city.clean_picks(request['picks'])
    if sorted(picks) != sorted(DEFAULT_PICKS) or request['city'] != 'London':
        raise ValueError('The fictional sample uses the three default tastes in London. Change to live mode for other choices.')
    profile = f"{request['flow']}:{request['experiment']}"
    domains = taste_city.SCENARIO_PLANS[profile]
    outlets = []
    for domain in domains:
        name, kind, affinity = EXAMPLES[domain]
        entity = {'id': f'fictional:{profile}:{domain}', 'name': name, 'type': kind}
        if affinity is not None:
            entity['affinity'] = affinity
        if domain == 'food':
            entity['genre'] = kind
        outlets.append({'id': domain, 'domain': domain, 'entity': entity, 'call': 'fictional sample'})
    return {
        'mode': 'synthetic', 'recorded_at': None, 'profile': profile,
        'picks': picks, 'city': 'London', 'anchors': [], 'calls': [],
        'outlets': outlets, 'demo_shared': False,
    }


def scenario(body):
    sample = graph(body)
    result = scenario_engine.build(body, sample)
    result['qloo']['demo_shared'] = False
    result['qloo']['source_notice'] = 'Fictional example only. No Qloo request, affinity result or agent run.'
    result['total_ms'] = 0
    return result


def discovery(body):
    """Five fictional discovery outlets; never present these as provider evidence."""
    picks = taste_city.clean_picks(body.get('picks'))
    if sorted(picks) != sorted(DEFAULT_PICKS) or body.get('city', 'London') != 'London':
        raise ValueError('The fictional sample uses Björk, Radiohead and Little Simz in London. Use live mode for other tastes.')
    return {'mode': 'synthetic', 'recorded_at': None, 'city': 'London', 'picks': picks,
            'anchors': [], 'calls': [], 'outlets': [
                {'id': outlet_id, 'domain': domain, 'entity': {'id': 'fictional:' + domain,
                 'name': EXAMPLES[domain][0], 'type': kind}, 'call': 'fictional sample'}
                for outlet_id, domain, kind in taste_city.OUTLETS]}


def local_discovery(body):
    result=discovery(body)
    result['local_area']={'label':'Fictional example neighbourhood, London','radius_m':1000,'popularity_cap':None,'source':'fictional sample'}
    result['nearby_places']=[{'id':'fictional:local:'+kind,'name':name,'type':'place','genre':kind,
        'distance_m':distance,'call':'fictional sample','why':'Illustrated connection only, no provider inference',
        'popularity':None} for kind,name,distance in [('cafe','Example Corner Café',300),('cinema','Example Neighbourhood Cinema',650),('venue','Example Listening Room',900)]]
    return result
