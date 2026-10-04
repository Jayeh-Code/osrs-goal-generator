from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Alpha610OverviewIconTests(unittest.TestCase):
    def test_overview_asset_manifest_uses_curated_osrs_files(self) -> None:
        catalog = json.loads((ROOT / "assets" / "catalog.json").read_text(encoding="utf-8"))
        expected = {
            "overview:total_level": "Skills icon.png",
            "overview:combat_level": "Combat icon.png",
            "overview:total_xp": "XP drops icon.png",
            "overview:collections": "Collection log icon.png",
            "overview:account_type": "Account Management.png",
            "overview:snapshots": "Account Management - View History icon.png",
        }
        for key, filename in expected.items():
            self.assertEqual(catalog[key]["wiki_filename"], filename)

    def test_home_overview_routes_six_sprite_keys(self) -> None:
        source = (ROOT / "src" / "osrs_goal_generator" / "gui" / "main_window.py").read_text(encoding="utf-8")
        for key in [
            "overview:total_level",
            "overview:combat_level",
            "overview:total_xp",
            "overview:collections",
            "overview:account_type",
            "overview:snapshots",
        ]:
            self.assertIn(key, source)
        self.assertIn("def _render_overview_icons", source)
        self.assertIn("self._request_assets(overview_asset_keys)", source)

    def test_version_is_alpha_6_10(self) -> None:
        source = (ROOT / "src" / "osrs_goal_generator" / "config.py").read_text(encoding="utf-8")
        self.assertIn('VERSION = "4.0.0-', source)


if __name__ == "__main__":
    unittest.main()
