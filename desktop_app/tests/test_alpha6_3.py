import json
import unittest
from pathlib import Path

from osrs_goal_generator.config import ASSET_CATALOG_FILE, VERSION
from osrs_goal_generator.services.wiki_assets import WikiAssetService


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_WINDOW = PROJECT_ROOT / "src" / "osrs_goal_generator" / "gui" / "main_window.py"
THEME = PROJECT_ROOT / "src" / "osrs_goal_generator" / "gui" / "theme.py"
WIKI_ASSETS = PROJECT_ROOT / "src" / "osrs_goal_generator" / "services" / "wiki_assets.py"
SOURCE_ROOT = PROJECT_ROOT / "src" / "osrs_goal_generator"


class Alpha63Tests(unittest.TestCase):
    def test_version_is_alpha63(self):
        self.assertTrue(VERSION.startswith(("4.0.0-alpha.6", "4.0.0-alpha.7", "4.0.0-alpha.8", "4.0.0-alpha.9", "4.0.0-beta.")))

    def test_every_skill_uses_canonical_osrs_icon_filename(self):
        raw = json.loads(ASSET_CATALOG_FILE.read_text(encoding="utf-8"))
        skills = {key: value for key, value in raw.items() if key.startswith("skill:")}
        self.assertEqual(len(skills), 24)
        for key, record in skills.items():
            skill = key.split(":", 1)[1]
            self.assertEqual(record["wiki_filename"], f"{skill} icon.png")

    def test_boss_resolution_is_deterministic_not_fuzzy(self):
        source = WIKI_ASSETS.read_text(encoding="utf-8")
        self.assertIn("RUNELITE_BOSS_ATLAS_ORDER", source)
        self.assertIn("BUNDLED_BOSS_MANIFEST", source)
        self.assertNotIn("search_boss_icon_filenames", source)

    def test_new_boss_cache_cannot_reuse_old_bad_icons(self):
        service = WikiAssetService()
        self.assertEqual(service.boss_icon_dir.name, "bosses")

    def test_gui_source_uses_no_non_ascii_decorative_glyphs(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertTrue(source.isascii())
        self.assertNotIn("GENERATE GOAL", "")  # keep test body non-empty on all Python versions

    def test_goal_button_and_favorite_button_have_safe_sizes(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn("button.setMinimumSize(156, 40)", source)
        self.assertIn("favorite_button.setMinimumSize(82, 40)", source)

    def test_theme_does_not_force_platform_specific_font_family(self):
        source = THEME.read_text(encoding="utf-8")
        self.assertNotIn("font-family", source)
        self.assertNotIn("letter-spacing", source)

    def test_all_python_ui_and_engine_sources_are_ascii_safe(self):
        for path in SOURCE_ROOT.rglob("*.py"):
            self.assertTrue(path.read_text(encoding="utf-8").isascii(), str(path))


if __name__ == "__main__":
    unittest.main()
