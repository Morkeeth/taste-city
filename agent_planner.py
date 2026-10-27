"""A bounded, rule-driven Qloo agent for one real buyer planning question.

The loop observes a live graph, chooses its next Qloo tool call from the
returned entity (not from a fixed second query), verifies that response, and
returns a small field test. No model API, recorded fallback, or raw response is
used here. Affinity is a cultural lead, not demand or partner availability.
"""
import os

from qloo_client import BudgetSpent, Live
import scenario_engine
import taste_city
from taste_match import entities, short

NEXT_DOMAIN = {
    'music': ('film', 'movie'),
    'film': ('music', 'artist'),
    'food': ('music', 'artist'),
    'brand': ('music', 'artist'),
    'books': ('film', 'movie'),
    'places': ('music', 'artist'),
}
MAX_HTTP_READS = 11  # at most 9 for the first graph, 2 for the adaptive follow-up


class AgentUnavailable(RuntimeError):
    pass


def plan(body, key=None, base=None, first_graph=None, followup_client=None):
    request = scenario_engine.clean_request(body)
    picks = taste_city.clean_picks(request['picks'])
    if body.get('demo') is True:
        raise ValueError('The live agent cannot use fictional demo data. Switch to live agent mode.')
    key = key or os.environ.get('QLOO_API_KEY')
    if not key and first_graph is None:
        raise taste_city.MissingKey('Set QLOO_API_KEY on the server to use the live Taste Agent.')
    profile = f"{request['flow']}:{request['experiment']}"
    graph = first_graph if first_graph is not None else taste_city._live(
        picks, request['city'], key, base=base, profile=profile, http_cap=9,
    )
    if graph.get('mode') != 'live' or graph.get('profile') != profile:
        raise AgentUnavailable('A live Qloo graph for this exact idea is required.')
    choices = [row for row in graph.get('outlets') or []
               if row.get('domain') in NEXT_DOMAIN and (row.get('entity') or {}).get('id')
               and (row.get('entity') or {}).get('affinity') is not None]
    if not choices:
        raise AgentUnavailable('Qloo did not return a cited cultural lead to investigate.')
    lead = max(choices, key=lambda row: float(row['entity']['affinity']))
    target_domain, target_type = NEXT_DOMAIN[lead['domain']]
    client = followup_client or Live(key, base=base, max_calls=1, pause=0, max_http_reads=2)
    call = client.get(
        f"agent follow-up: {target_domain} related to {lead['entity']['name']}",
        '/v2/insights',
        {'filter.type': f'urn:entity:{target_type}',
         'signal.interests.entities': lead['entity']['id'], 'take': 5},
    )
    if call.get('status') != 200:
        raise taste_city.QlooUnavailable(f"Qloo follow-up returned HTTP {call.get('status') or 0}.")
    found = entities(call)
    if not found:
        raise AgentUnavailable('Qloo returned no related entity for the adaptive follow-up.')
    bridge = short(found[0])
    if not bridge.get('id') or not bridge.get('name'):
        raise AgentUnavailable('Qloo follow-up had no usable cited entity.')
    follow_id = 'A08'
    safe_calls = [dict(row) for row in graph.get('calls') or []]
    safe_calls.append({'id': follow_id, 'purpose': call['purpose'], 'status': call['status'],
                       'url': call.get('url', '').split('?', 1)[0]})
    return {
        'mode': 'live', 'agent_kind': 'bounded adaptive Qloo tool loop', 'model_calls': 0,
        'flow': request['flow'], 'idea': scenario_engine.FLOW_CONFIG[request['flow']]['experiments'][request['experiment']],
        'city': request['city'], 'picks': picks,
        'steps': [
            {'action': 'Observe', 'detail': f"Qloo returned {lead['entity']['name']} as the strongest cited cultural lead in this idea's graph.",
             'domain': lead['domain'], 'call': lead['call'], 'affinity': lead['entity']['affinity'], 'entity_id': lead['entity']['id']},
            {'action': 'Choose tool', 'detail': f"The lead is {lead['domain']}, so the agent asks Qloo for a related {target_domain} lead, seeded with that returned entity ID.",
             'seed_call': lead['call'], 'target_domain': target_domain, 'seed_entity_id': lead['entity']['id'],
             'query': {'path': '/v2/insights', 'filter.type': f'urn:entity:{target_type}', 'signal.interests.entities': lead['entity']['id']}},
            {'action': 'Verify', 'detail': f"Qloo returned {bridge['name']} for the follow-up. The agent cites that call and stops.",
             'call': follow_id, 'affinity': bridge.get('affinity'), 'entity_id': bridge['id']},
        ],
        'lead': {'name': lead['entity']['name'], 'id': lead['entity']['id'], 'domain': lead['domain'], 'call': lead['call'], 'affinity': lead['entity']['affinity']},
        'bridge': {'name': bridge['name'], 'id': bridge['id'], 'domain': target_domain, 'call': follow_id, 'affinity': bridge.get('affinity')},
        'reject_if': [
            f"The owner cannot get a quote, rights or availability for a {bridge['name']} tie-in.",
            'One small test costs more than the pilot budget the owner set.',
            f"The owner judges the {lead['entity']['name']} to {bridge['name']} link wrong for their customers. Affinity is a cultural lead, not their audience.",
        ],
        'next_action': 'Ask for one real quote and rights/availability check, then test paid interest before booking.',
        'stop_rule': 'Stop if rights, availability or the pilot budget cannot be confirmed.',
        'limits': 'Qloo affinities indicate cultural fit. They do not establish demand, cost or partner consent.',
        'qloo_calls': safe_calls,
        'actual_http_reads': graph.get('http_reads', len(graph.get('calls') or [])) + getattr(client, 'http_reads', 1),
        'max_http_reads': MAX_HTTP_READS,
    }
