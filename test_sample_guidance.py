"""The labelled sample answers one example; the page must say which before anyone taps."""
import unittest
from pathlib import Path

import sample_demo

PAGE = (Path(__file__).parent / "village.html").read_text(encoding="utf-8")


class SampleGuidance(unittest.TestCase):
    def test_page_sample_matches_the_server_sample(self):
        self.assertIn('SAMPLE_PICKS = ["Björk","Radiohead","Little Simz"], SAMPLE_CITY = "London"', PAGE)
        self.assertEqual(tuple(sample_demo.DEFAULT_PICKS), ("Björk", "Radiohead", "Little Simz"))

    def test_first_use_guide_and_recovery_exist(self):
        for marker in ("data-first-use", "data-sample-guide", 'id="usesample"', 'id="usesamplebrand"', "Live mode only"):
            self.assertIn(marker, PAGE)

    def test_other_tastes_still_refused_by_the_sample(self):
        with self.assertRaises(ValueError):
            sample_demo.discovery({"picks": ["Nils Frahm", "Rosalía", "Khruangbin"], "city": "London", "demo": True})


if __name__ == "__main__":
    unittest.main()
