import pathlib
import unittest

from capture_contract import validate_capture


def moves(food_type="restaurant"):
    return [
        {"role": "Sound", "entity": "A", "entity_type": "artist", "evidence": "L04"},
        {"role": "Story", "entity": "B", "entity_type": "movie", "evidence": "L05"},
        {"role": "Hospitality", "entity": "C", "entity_type": food_type, "evidence": "L06"},
        {"role": "Editorial", "entity": "D", "entity_type": "book", "evidence": "L07"},
        {"role": "Next city", "entity": "E", "entity_type": "destination", "evidence": "L08"},
    ]


class CaptureContract(unittest.TestCase):
    def test_exact_capture_runner_layout_and_mixed_case_role_pass(self):
        food = validate_capture(
            moves(), {"x": 198, "width": 182}, inner_width=390, scroll_width=390,
            errors=[], taste_requests=1,
        )
        self.assertEqual(food["role"], "Hospitality")

    def test_museum_fails_even_when_it_is_not_tate_modern(self):
        bad = moves("museum")
        bad[2]["entity"] = "Wellcome Collection"
        with self.assertRaisesRegex(ValueError, "not restaurant-typed"):
            validate_capture(bad, {"x": 198, "width": 182}, 390, 390, [], 1)

    def test_browser_errors_request_count_move_count_clipping_and_overflow_fail(self):
        cases = [
            (moves(), {"x": 198, "width": 182}, 390, 390, ["boom"], 1),
            (moves(), {"x": 198, "width": 182}, 390, 390, [], 2),
            (moves()[:4], {"x": 198, "width": 182}, 390, 390, [], 1),
            (moves(), {"x": 220, "width": 182}, 390, 390, [], 1),
            (moves(), {"x": 198, "width": 182}, 390, 391, [], 1),
        ]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_capture(*args)

    def test_external_script_uses_the_tested_contract_and_dom_entity_type(self):
        script = pathlib.Path(__file__).resolve().parent / "tests" / "capture_brand_plan.py"
        source = script.read_text()
        self.assertIn("validate_moves(moves, errors, len(taste_requests))", source)
        self.assertIn('entity_type: node.dataset.entityType', source)
        self.assertIn('validate_layout(nav_box, layout["innerWidth"], layout["scrollWidth"])', source)
        self.assertIn("qloo-brand-plan-failure-1440x1000.png", source)
        self.assertIn("capture-failure.json", source)
        self.assertIn("taste_responses", source)
        self.assertNotIn('row["role"] == "HOSPITALITY"', source)


if __name__ == "__main__":
    unittest.main()
