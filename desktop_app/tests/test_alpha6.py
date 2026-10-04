import json
import tempfile
import unittest
from pathlib import Path

from osrs_goal_generator.config import ASSET_CATALOG_FILE, VERSION
from osrs_goal_generator.gui.theme import APP_STYLESHEET
from osrs_goal_generator.services.wiki_assets import WikiAssetService


class Alpha6Tests(unittest.TestCase):
    def test_version_remains_alpha6_family(self):
        self.assertTrue(VERSION.startswith(("4.0.0-alpha.6", "4.0.0-alpha.7", "4.0.0-alpha.8", "4.0.0-alpha.9", "4.0.0-beta.")))

    def test_boss_assets_can_resolve_without_curated_catalog_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            catalog = root / "catalog.json"
            catalog.write_text("{}", encoding="utf-8")
            service = WikiAssetService(cache_dir=root / "cache", catalog_path=catalog)
            self.assertTrue(service.can_fetch("boss:Zulrah"))
            self.assertFalse(service.can_fetch("item:Definitely Not Curated"))

    def test_all_current_skills_have_curated_wiki_assets(self):
        raw = json.loads(ASSET_CATALOG_FILE.read_text(encoding="utf-8"))
        skill_keys = [key for key in raw if key.startswith("skill:")]
        self.assertEqual(len(skill_keys), 24)
        self.assertIn("skill:Sailing", raw)

    def test_approved_visual_shell_tokens_exist(self):
        for token in [
            "QFrame#Sidebar",
            "QFrame#TopBar",
            "QFrame#HeroCard",
            "QFrame#StatTile",
            "QLabel#Brand",
            "QLabel#GoalTitle",
        ]:
            self.assertIn(token, APP_STYLESHEET)


if __name__ == "__main__":
    unittest.main()
