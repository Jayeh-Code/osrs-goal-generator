from __future__ import annotations

import json
import unittest
from pathlib import Path

from osrs_goal_generator.services.wiki_assets import (
    BUNDLED_BOSS_ICON_DIR,
    BUNDLED_BOSS_MANIFEST,
    RUNELITE_BOSS_ATLAS_ORDER,
    WikiAssetService,
)


class Alpha64Tests(unittest.TestCase):
    def test_curated_boss_manifest_has_all_expected_entries(self):
        self.assertEqual(len(RUNELITE_BOSS_ATLAS_ORDER), 71)
        self.assertEqual(RUNELITE_BOSS_ATLAS_ORDER[0], "Abyssal Sire")
        self.assertEqual(RUNELITE_BOSS_ATLAS_ORDER[-1], "Zulrah")

    def test_all_71_boss_icons_are_bundled(self):
        raw = json.loads(BUNDLED_BOSS_MANIFEST.read_text(encoding="utf-8"))
        bosses = raw["bosses"]
        self.assertEqual(set(bosses), set(RUNELITE_BOSS_ATLAS_ORDER))
        for boss, record in bosses.items():
            path = BUNDLED_BOSS_ICON_DIR / record["file"]
            self.assertTrue(path.exists(), boss)
            self.assertGreater(path.stat().st_size, 100, boss)

    def test_bosses_resolve_without_network_or_cache(self):
        service = WikiAssetService()
        first = service.cached_path("boss:Abyssal Sire")
        last = service.cached_path("boss:Zulrah")
        self.assertIsNotNone(first)
        self.assertIsNotNone(last)
        self.assertTrue(first.exists())
        self.assertTrue(last.exists())

    def test_unknown_boss_is_not_claimed(self):
        service = WikiAssetService()
        self.assertTrue(service.can_fetch("boss:Vorkath"))
        self.assertFalse(service.can_fetch("boss:Definitely Not A Boss"))


if __name__ == "__main__":
    unittest.main()
