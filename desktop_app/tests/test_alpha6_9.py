from __future__ import annotations

import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG = PROJECT_ROOT / "assets" / "catalog.json"
MAIN_WINDOW = PROJECT_ROOT / "src" / "osrs_goal_generator" / "gui" / "main_window.py"
CONFIG = PROJECT_ROOT / "src" / "osrs_goal_generator" / "config.py"


class Alpha69Tests(unittest.TestCase):
    def test_clue_goal_uses_canonical_clue_scroll_sprite(self):
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        self.assertEqual(catalog["goal:clues"]["wiki_filename"], "Clue scroll.png")

    def test_goal_asset_router_handles_clues(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn('if goal.category == "clues":', source)
        self.assertIn('return "goal:clues"', source)

    def test_clue_fallback_text_is_clue(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn('"clues": "CLUE"', source)

    def test_version_remains_in_alpha_6_series(self):
        source = CONFIG.read_text(encoding="utf-8")
        self.assertIn('VERSION = "4.0.0-alpha.', source)


if __name__ == "__main__":
    unittest.main()
