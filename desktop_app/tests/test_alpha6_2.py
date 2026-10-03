from __future__ import annotations

import unittest
from pathlib import Path

from osrs_goal_generator.config import VERSION
from osrs_goal_generator.services.wiki_assets import WikiAssetService


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_WINDOW = PROJECT_ROOT / "src" / "osrs_goal_generator" / "gui" / "main_window.py"
WIKI_ASSETS = PROJECT_ROOT / "src" / "osrs_goal_generator" / "services" / "wiki_assets.py"


class Alpha62Tests(unittest.TestCase):
    def test_version_is_alpha6_family(self):
        self.assertTrue(VERSION.startswith(("4.0.0-alpha.6", "4.0.0-alpha.7", "4.0.0-alpha.8", "4.0.0-alpha.9")))

    def test_bosses_no_longer_use_page_art_or_fuzzy_search(self):
        source = WIKI_ASSETS.read_text(encoding="utf-8")
        self.assertNotIn("cache_page_image", source)
        self.assertNotIn("search_boss_icon_filenames", source)

    def test_boss_assets_are_local_and_available_immediately(self):
        service = WikiAssetService()
        path = service.cached_path("boss:Vorkath")
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())
        self.assertEqual(path.parent.name, "bosses")

    def test_boss_goal_column_reserves_real_widget_width_and_height(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn("self.boss_table.setColumnWidth(5, 188)", source)
        self.assertIn("self.boss_table.setRowHeight(row, 62)", source)
        self.assertIn("button.setMinimumSize(156, 40)", source)
        self.assertIn("favorite_button.setMinimumSize(82, 40)", source)

    def test_boss_display_order_is_explicitly_alphabetical(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn("sorted(all_boss_names(), key=str.casefold)", source)


if __name__ == "__main__":
    unittest.main()
