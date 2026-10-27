"""Taste City Engine scenario, evidence, performance, and benchmark checks."""
import json
import pathlib
import tempfile
import unittest

import benchmark
import scenario_engine
import taste_city


def graph():
    domains = (
        ("music", "artist", "Yves Tumor", "music-id", 0.924, "L04"),
        ("film", "movie", "Synecdoche, New York", "film-id", 0.930, "L05"),
        ("food", "place", "Caffè Estorick", "food-id", 0.930, "L06"),
        ("books", "book", "And Then It Fell Apart", "book-id", 0.920, "L07"),
        ("places", "destination", "Hastings", "place-id", 0.904, "L08"),
    )
    outlets = []
    for domain, kind, name, entity_id, affinity, call in domains:
        entity = {"type": kind, "name": name, "id": entity_id, "affinity": affinity}
        if domain == "food":
            entity["genre"] = "restaurant:cafe"
        outlets.append({"id": domain, "domain": domain, "entity": entity, "call": call})
    return {
        "mode": "live",
        "recorded_at": "2026-10-24T00:43:28+00:00",
        "picks": ["Björk", "Radiohead", "Little Simz"],
        "anchors": [{"id": str(i), "name": name} for i, name in enumerate(("Björk", "Radiohead", "Little Simz"))],
        "outlets": outlets,
        "calls": [{"id": f"L0{i}"} for i in range(1, 9)],
    }


class ScenarioEngine(unittest.TestCase):
    def test_brand_and_festival_are_distinct_flows_with_three_cited_archetypes(self):
        brand = scenario_engine.build({"flow": "brand", "experiment": "flavour", "size": "city", "picks": graph()["picks"]}, graph())
        festival = scenario_engine.build({"flow": "festival", "experiment": "lineup", "size": "destination", "picks": graph()["picks"]}, graph())
        self.assertEqual(brand["flow"], "brand")
        self.assertEqual(festival["flow"], "festival")
        self.assertNotEqual([row["name"] for row in brand["archetypes"]], [row["name"] for row in festival["archetypes"]])
        for result in (brand, festival):
            self.assertEqual(len(result["archetypes"]), 3)
            self.assertTrue(all(row["evidence"] for row in result["archetypes"]))
            self.assertTrue(all(item["call"].startswith("L") for row in result["archetypes"] for item in row["evidence"]))

    def test_demographic_signal_is_not_averaged_with_entity_affinity(self):
        rows = [{'domain':'music','entity':{'affinity':0.9}}, {'domain':'demographics','entity':{'affinity':0.2}}]
        self.assertEqual(scenario_engine._strength(rows), 90)
        self.assertIsNone(scenario_engine._strength(rows[1:]))

    def test_spend_is_separate_scenario_math_not_qloo_claim(self):
        result = scenario_engine.build({"flow": "brand", "experiment": "popup", "size": "neighbourhood", "reach": 1000, "spend": 10, "picks": graph()["picks"]}, graph())
        self.assertEqual([row["visitors"] for row in result["spend_sensitivity"]], [20, 50, 80])
        self.assertEqual([row["gross_spend"] for row in result["spend_sensitivity"]], [200, 500, 800])
        self.assertIn("does not predict", result["spend_assumption"]["notice"])

    def test_scale_follows_flow(self):
        brand = scenario_engine.clean_request({"flow": "brand", "experiment": "event", "size": "metro", "picks": graph()["picks"]})
        festival = scenario_engine.clean_request({"flow": "festival", "experiment": "night", "size": "local", "picks": graph()["picks"]})
        self.assertEqual(brand["population"], 2_000_000)
        self.assertEqual(festival["reach"], 2_000)

    def test_cached_first_path_makes_no_network_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            path = taste_city.cache_path(graph()["picks"], "London", root)
            taste_city._record(path, graph())
            result = taste_city.build(
                graph()["picks"], "London",
                env={"QLOO_API_KEY": "would-call", "QLOO_BASE": "http://127.0.0.1:1"},
                cache_root=root,
                prefer_cache=True,
            )
            self.assertEqual(result["mode"], "recorded")

    def test_benchmark_rubric_is_neutral_and_validator_recomputes_totals(self):
        self.assertEqual(set(benchmark.RUBRIC), set(benchmark.CRITERIA))
        self.assertNotIn("qloo", " ".join(benchmark.RUBRIC.values()).casefold())
        rows = []
        totals = {arm: {criterion: 20 for criterion in benchmark.CRITERIA} | {"total": 80} for arm in benchmark.ARMS}
        for index in range(5):
            rows.append({"answers": [
                {"arm": arm, "blind_id": f"{arm}-{index}", "scores": {criterion: 4 for criterion in benchmark.CRITERIA}}
                for arm in benchmark.ARMS
            ]})
        payload = {
            "answer_calls": 2,
            "answer_model": "Claude",
            "grader_model_family": "Gemini",
            "rows": rows,
            "totals": totals,
        }
        self.assertEqual(benchmark.validate(payload), totals)

    def test_idea_change_changes_archetypes_and_evidence_domains(self):
        popup_graph = graph() | {"profile": "brand:popup"}
        merch_graph = graph() | {"profile": "brand:merch"}
        popup = scenario_engine.build({"flow": "brand", "experiment": "popup", "size": "city", "picks": graph()["picks"]}, popup_graph)
        merch = scenario_engine.build({"flow": "brand", "experiment": "merch", "size": "city", "picks": graph()["picks"]}, merch_graph)
        self.assertNotEqual([row["name"] for row in popup["archetypes"]], [row["name"] for row in merch["archetypes"]])
        self.assertNotEqual(popup["qloo"]["profile"], merch["qloo"]["profile"])

    def test_host_and_vercel_route_the_scenario_api(self):
        root = pathlib.Path(__file__).parent
        host = (root / "match_app.py").read_text()
        self.assertIn('path == "/api/scenario"', host)
        self.assertIn('path == "/api/brand-taste"', host)
        config = json.loads((root / "vercel.json").read_text())
        self.assertIn("api/scenario.py", config["functions"])
        self.assertIn("api/brand_taste.py", config["functions"])

    def test_city_ui_exposes_public_brand_url_tasting(self):
        page = (pathlib.Path(__file__).parent / "village.html").read_text()
        self.assertIn('id="brandurl"', page)
        self.assertIn('fetch("/api/brand-taste"', page)
        self.assertIn("renderBrandTaste", page)
        self.assertIn("a.reaction", page)


if __name__ == "__main__":
    unittest.main()
