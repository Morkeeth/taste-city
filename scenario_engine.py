"""Shape one Qloo taste graph into brand and festival decision flows.

Qloo affinities support cultural fit and cross-domain relationships. They do
not support audience size, conversion, or spend predictions. Those numbers are
kept in a separate, plainly labelled scenario model.
"""
from __future__ import annotations

import math
import time


FLOW_CONFIG = {
    "brand": {
        "label": "Brand experiment",
        "experiments": {
            "popup": "city pop-up",
            "flavour": "limited flavour",
            "event": "late event",
            "merch": "merch drop",
        },
        "sizes": {
            "neighbourhood": {"label": "Neighbourhood test", "population": 50_000, "reach": 900, "spend": 12},
            "city": {"label": "City test", "population": 500_000, "reach": 4_000, "spend": 15},
            "metro": {"label": "Metro test", "population": 2_000_000, "reach": 12_000, "spend": 18},
        },
    },
    "festival": {
        "label": "Festival experiment",
        "experiments": {
            "lineup": "lineup swap",
            "sponsor": "sponsor pairing",
            "food": "food village",
            "night": "late-night programme",
        },
        "sizes": {
            "local": {"label": "Local festival", "population": 120_000, "reach": 2_000, "spend": 48},
            "city": {"label": "City festival", "population": 800_000, "reach": 15_000, "spend": 72},
            "destination": {"label": "Destination festival", "population": 3_000_000, "reach": 60_000, "spend": 110},
        },
    },
}

ARCHETYPE_BLUEPRINTS = {
    "brand:popup": [
        ("After-dark drop-ins", ("music", "film"), "Build the pop-up around a sound and screen world that already connect in this audience graph."),
        ("Local ritual seekers", ("food", "demographics"), "Set the service rhythm and hours for the strongest Qloo audience skew, then test it against a normal opening."),
        ("Culture-route regulars", ("film", "food"), "Pair the visit with one nearby culture cue, not a generic discount."),
    ],
    "brand:flavour": [
        ("Ritual tasters", ("food", "books"), "Give the flavour a tasting ritual and editorial story before the chef names the recipe."),
        ("Brand crossovers", ("brand", "food"), "Use the ranked brand and hospitality link as the launch territory, then blind-test purchase choice."),
        ("Focused regulars", ("demographics", "books"), "Choose the message for the returned audience skew without treating it as audience size."),
    ],
    "brand:event": [
        ("Scene builders", ("music", "film"), "Make the event one coherent sound and screen world."),
        ("Late-table regulars", ("food", "demographics"), "Shape timing and hospitality around the returned audience skew, then measure dwell time."),
        ("Cross-domain explorers", ("film", "food"), "Use the film and place connection as the reason to stay, not as decoration."),
    ],
    "brand:merch": [
        ("Editorial collectors", ("books", "brand"), "Make the object feel published and culturally placed, then require reservations before production."),
        ("Sound-led loyalists", ("music", "brand"), "Use the ranked music and brand bridge as the collaboration brief."),
        ("Selective regulars", ("demographics", "books"), "Adjust format and copy to the returned audience skew without claiming demand."),
    ],
    "festival:lineup": [
        ("Front-row explorers", ("music", "film"), "Test a music and film pairing as one programme block instead of adding a broad genre stage."),
        ("Destination diggers", ("places", "music"), "Tie one artist cluster to a destination story that can change the trip decision."),
        ("Age-skewed discoverers", ("demographics", "music"), "Sequence discovery for the returned audience skew and compare saves with the unchanged bill."),
    ],
    "festival:sponsor": [
        ("Credibility keepers", ("brand", "music"), "Shortlist a sponsor only when its ranked brand link fits the sound world."),
        ("Trip makers", ("places", "brand"), "Make the sponsor useful to the destination experience, not a logo layer."),
        ("Audience-fit skeptics", ("demographics", "brand"), "Check the returned skew before committing inventory, without reading it as reach."),
    ],
    "festival:food": [
        ("Taste-route wanderers", ("food", "places"), "Build a food route from a ranked local place and destination link."),
        ("Brand-curious diners", ("brand", "food"), "Use the cross-domain brand link to choose a partner territory, then test real menus."),
        ("Timed grazers", ("demographics", "food"), "Plan service windows for the returned audience skew and measure queues."),
    ],
    "festival:night": [
        ("After-hours explorers", ("music", "film"), "Program one late-night sound and screen world with a clear stop rule."),
        ("Night-table regulars", ("food", "demographics"), "Set the late hospitality offer for the returned skew, then compare dwell time."),
        ("Cross-domain roamers", ("film", "food"), "Connect the screening and food cue so the programme has one reason to exist."),
    ],
}


class InvalidScenario(ValueError):
    pass


def _choice(options, value, field):
    value = str(value or "").strip().lower()
    if value not in options:
        raise InvalidScenario(f"Choose a valid {field}.")
    return value


def _number(value, default, low, high, field):
    try:
        number = float(value if value is not None else default)
    except (TypeError, ValueError):
        raise InvalidScenario(f"{field} must be a number.") from None
    if not low <= number <= high:
        raise InvalidScenario(f"{field} must be between {low:g} and {high:g}.")
    return number


def clean_request(body):
    flow = _choice(FLOW_CONFIG, body.get("flow") or "brand", "flow")
    config = FLOW_CONFIG[flow]
    experiment = _choice(config["experiments"], body.get("experiment"), "experiment")
    size = _choice(config["sizes"], body.get("size"), "size")
    defaults = config["sizes"][size]
    name = str(body.get("name") or ("North Star Coffee" if flow == "brand" else "North Star Festival")).strip()[:60]
    city = str(body.get("city") or "London").strip()[:60]
    reach = int(_number(body.get("reach"), defaults["reach"], 100, 500_000, "People in the scenario"))
    spend = _number(body.get("spend"), defaults["spend"], 1, 1_000, "Spend per visitor")
    return {
        "flow": flow,
        "name": name or "Untitled experiment",
        "city": city or "London",
        "experiment": experiment,
        "size": size,
        "population": defaults["population"],
        "reach": reach,
        "spend": round(spend, 2),
        "picks": body.get("picks"),
    }


def _by_domain(graph):
    return {row["domain"]: row for row in graph.get("outlets") or []}


def _evidence(row):
    if not row:
        return None
    entity = row.get("entity") or {}
    return {
        "domain": row.get("domain"),
        "name": entity.get("name"),
        "id": entity.get("id"),
        "type": entity.get("genre") or entity.get("type"),
        "affinity": entity.get("affinity"),
        "call": row.get("call"),
    }


def _strength(rows):
    values = [float((row.get("entity") or {}).get("affinity")) for row in rows if row.get("domain") != "demographics" and (row or {}).get("entity", {}).get("affinity") is not None]
    return round(sum(values) / len(values) * 100) if values else None


def archetypes(graph, flow, experiment):
    by = _by_domain(graph)
    profile = graph.get("profile") or f"{flow}:{next((key for key, label in FLOW_CONFIG[flow]['experiments'].items() if label == experiment), '')}"
    specs = ARCHETYPE_BLUEPRINTS.get(profile)
    if not specs:
        specs = [("Taste explorers", ("music", "film"), f"Test the {experiment} against the named Qloo graph."),
                 ("Regulars", ("books", "food"), "Build a repeatable ritual and measure it."),
                 ("City roamers", ("places", "music"), "Connect the visit to one destination cue.")]
    out = []
    for name, domains, action in specs:
        rows = [by[domain] for domain in domains if by.get(domain)]
        out.append({
            "name": name,
            "graph_strength": _strength(rows),
            "action": action,
            "evidence": [item for item in (_evidence(row) for row in rows) if item],
        })
    return out


def scenario_math(reach, spend):
    """Plain sensitivity range. These rates are assumptions, not Qloo output."""
    rates = (("Low", 0.02), ("Working", 0.05), ("High", 0.08))
    return [
        {
            "label": label,
            "rate": rate,
            "visitors": math.floor(reach * rate),
            "gross_spend": round(math.floor(reach * rate) * spend, 2),
        }
        for label, rate in rates
    ]


def build(body, graph):
    started = time.perf_counter()
    request = clean_request(body)
    flow = request["flow"]
    experiment_label = FLOW_CONFIG[flow]["experiments"][request["experiment"]]
    size = FLOW_CONFIG[flow]["sizes"][request["size"]]
    shaped = {
        "flow": flow,
        "name": request["name"],
        "city": request["city"],
        "experiment": {"id": request["experiment"], "label": experiment_label},
        "scale": {
            "id": request["size"],
            "label": size["label"],
            "population": request["population"],
            "people_in_scenario": request["reach"],
        },
        "archetypes": archetypes(graph, flow, experiment_label),
        "spend_sensitivity": scenario_math(request["reach"], request["spend"]),
        "spend_assumption": {
            "per_visitor": request["spend"],
            "currency": "GBP",
            "notice": "Scenario math from your people and spend inputs. Qloo does not predict purchases or attendance.",
        },
        "qloo": {
            "mode": graph.get("mode"),
            "recorded_at": graph.get("recorded_at"),
            "anchors": graph.get("anchors") or [],
            "calls": graph.get("calls") or [],
            "outlets": graph.get("outlets") or [],
            "profile": graph.get("profile") or f"{flow}:{request['experiment']}",
        },
    }
    if graph.get('mode') == 'synthetic':
        for row in shaped['archetypes']:
            row['action'] = row['action'].replace('Qloo ', 'sample ').replace('returned ', 'illustrative ')
    shaped["engine_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return shaped
