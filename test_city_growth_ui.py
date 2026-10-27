import pathlib
import unittest


HTML = pathlib.Path(__file__).with_name("village.html").read_text()


class CityGrowthUI(unittest.TestCase):
    def test_population_has_three_density_tiers(self):
        self.assertIn('n >= 20 ? "city" : n >= 11 ? "town" : "village"', HTML)
        self.assertIn('id="population"', HTML)
        self.assertIn('min="5" max="25"', HTML)

    def test_city_features_share_the_existing_scene(self):
        for feature in ("townLayer", "cityLayer", "subwayLayer", "festivalLayer"):
            self.assertIn(f"scene.add(townLayer, cityLayer, subwayLayer, festivalLayer)", HTML)
            self.assertIn(feature, HTML)
        self.assertIn("subwayTrains.forEach", HTML)
        self.assertIn("festivalCrowd.forEach", HTML)

    def test_residents_stay_under_population_control(self):
        self.assertIn("c.populationEligible = i < streetCount", HTML)
        self.assertIn("if (!c.populationEligible || !g.visible) continue", HTML)
        self.assertIn("data-simulation-residents", (pathlib.Path(__file__).parent / "tests" / "play_marketplace.py").read_text())

    def test_marketplace_stays_in_the_same_view(self):
        self.assertIn("the marketplace lives in the moving village", HTML)
        self.assertIn("marketplace open", HTML)
        self.assertIn("window.__tasteCity", HTML)
        self.assertIn("Building the city from Qloo", HTML)
        self.assertIn("Play the taste game in this city", HTML)
        self.assertNotIn("Building the village from Qloo", HTML)
        self.assertNotIn("Play the taste game in this village", HTML)

    def test_local_demo_never_calls_qloo(self):
        self.assertIn('q.get("demo") === "1" ? Promise.resolve(DEMO_VILLAGE)', HTML)
        self.assertIn('if (q.get("demo") === "1")', HTML)

    def test_city_is_visibly_denser_at_full_population(self):
        self.assertIn("const innerCity", HTML)
        self.assertIn("const cityCrowd", HTML)
        self.assertIn("dataset.cityCrowd", HTML)

    def test_sixty_second_day_night_cycle_respects_reduced_motion(self):
        self.assertIn("const DAY_SECONDS = 60", HTML)
        self.assertIn("reduce ? 0.25 : (elapsed % DAY_SECONDS) / DAY_SECONDS", HTML)
        self.assertIn("windowMaterials.forEach", HTML)
        self.assertIn("moon.visible", HTML)

    def test_five_obvious_domain_outlets_offer_tap_cards(self):
        for domain in ("music", "film", "food", "books", "places"):
            self.assertIn(f'domain:"{domain}"', HTML)
        self.assertIn('className = "sign outlet-sign"', HTML)
        self.assertIn('data-taste-pick', HTML)
        self.assertIn("function clampLabel(el, x, y, w, h)", HTML)
        self.assertIn("clampLabel(outlet.el", HTML)
        self.assertNotIn("Google Forms", HTML)

    def test_three_taps_fill_outlets_from_qloo_entities(self):
        self.assertIn('fetch("/api/taste"', HTML)
        self.assertIn('picked.size !== 3', HTML)
        self.assertIn('label.el.dataset.qlooEntity = row.entity.id', HTML)
        self.assertIn('data-entity-id="${esc(row.entity.id)}"', HTML)
        self.assertNotIn('Qloo entity ${esc(row.entity.id)}</small>', HTML)
        self.assertIn('d.mode === "live" ? "Live Qloo response"', HTML)

    def test_brand_planner_turns_same_qloo_result_into_five_cited_moves(self):
        self.assertIn('Brand planning mode', HTML)
        self.assertIn('data-brand-pick', HTML)
        self.assertIn('document.body.dataset.brandPlan = "ready"', HTML)
        self.assertIn('document.body.dataset.brandPlan = "error"', HTML)
        for move in ("Sound", "Story", "Hospitality", "Editorial", "Next city"):
            self.assertIn(f'move("{move}"', HTML)
        self.assertIn('data-entity-type="${esc(row.entity.genre || row.entity.type)}"', HTML)
        self.assertIn('data-entity-id="${esc(row.entity.id)}"', HTML)
        self.assertIn('d.mode === "synthetic" ? "fictional example" : "Qloo "', HTML)
        self.assertIn('esc(row.entity.genre || row.entity.type) + " · " + esc(row.call)', HTML)
        self.assertNotIn('${esc(row.entity.genre || row.entity.type)} ${esc(row.entity.id)}', HTML)
        self.assertIn('else if (q.get("judge") === "1") openBrandPlanner();', HTML)

    def test_phone_header_stacks_without_clipping_brand_planner(self):
        self.assertIn('@media (max-width: 600px)', HTML)
        self.assertIn('class="city-heading"', HTML)
        self.assertIn('.city-heading {', HTML)
        self.assertIn('background:rgba(255,250,241,.95)', HTML)
        self.assertIn('.topnav { width:100%; margin-top:6px; }', HTML)
        self.assertIn('For business</button>', HTML)

    def test_capture_uses_http_and_attached_load_marker(self):
        capture = (pathlib.Path(__file__).parent / "tests" / "capture_city_growth.py").read_text()
        self.assertIn("ThreadingHTTPServer", capture)
        self.assertIn('state="attached"', capture)
        self.assertNotIn("as_uri()", capture)


if __name__ == "__main__":
    unittest.main()
