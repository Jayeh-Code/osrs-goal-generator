from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG = PROJECT_ROOT / "assets" / "catalog.json"
MAIN_WINDOW = PROJECT_ROOT / "src" / "osrs_goal_generator" / "gui" / "main_window.py"


class Alpha68Tests(unittest.TestCase):
    def test_collection_goal_uses_exact_collection_log_sprite(self):
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        self.assertEqual(
            catalog["goal:collection"]["wiki_filename"],
            "Collection log icon.png",
        )

    def test_money_goal_uses_stacked_gp_sprite(self):
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        self.assertEqual(
            catalog["goal:money"]["wiki_filename"],
            "Coins 10000.png",
        )

    def test_goal_asset_router_handles_collection_and_money(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn('if goal.category == "collection":', source)
        self.assertIn('return "goal:collection"', source)
        self.assertIn('if goal.category == "money":', source)
        self.assertIn('return "goal:money"', source)

    def test_goal_fallback_text_matches_new_categories(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn('"collection": "LOG"', source)
        self.assertIn('"money": "GP"', source)


if __name__ == "__main__":
    unittest.main()
