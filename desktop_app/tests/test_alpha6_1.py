import tempfile
import unittest
from pathlib import Path

from osrs_goal_generator.config import VERSION
from osrs_goal_generator.gui.theme import APP_STYLESHEET
from osrs_goal_generator.services.wiki_assets import WikiAssetService


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_WINDOW = PROJECT_ROOT / "src" / "osrs_goal_generator" / "gui" / "main_window.py"


class Alpha61Tests(unittest.TestCase):
    def make_asset_service(self, root: Path) -> WikiAssetService:
        catalog = root / "catalog.json"
        catalog.write_text("{}", encoding="utf-8")
        return WikiAssetService(cache_dir=root / "cache", catalog_path=catalog)

    def test_version_is_alpha6_or_later_patch(self):
        self.assertTrue(VERSION.startswith(("4.0.0-alpha.6", "4.0.0-alpha.7", "4.0.0-alpha.8", "4.0.0-alpha.9")))

    def test_bosses_are_backed_by_curated_manifest(self):
        from osrs_goal_generator.services.wiki_assets import RUNELITE_BOSS_ATLAS_ORDER
        with tempfile.TemporaryDirectory() as temp:
            service = self.make_asset_service(Path(temp))
            self.assertIn("Vorkath", RUNELITE_BOSS_ATLAS_ORDER)
            self.assertIn("The Corrupted Gauntlet", RUNELITE_BOSS_ATLAS_ORDER)
            self.assertTrue(service.can_fetch("boss:Vorkath"))

    def test_paths_and_diaries_use_card_layouts_not_cell_widgets(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn("self.paths_cards_layout", source)
        self.assertIn("self.diary_cards_layout", source)
        self.assertIn('card.setObjectName("PathCard")', source)
        self.assertIn('card.setObjectName("DiaryCard")', source)
        self.assertNotIn("self.paths_table = QTableWidget", source)
        self.assertNotIn("self.diary_table = QTableWidget", source)

    def test_home_uses_mockup_dashboard_hierarchy(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        for token in [
            'hero.setObjectName("DashboardHero")',
            'self.generate_button.setObjectName("HeroGenerate")',
            'QLabel("Account Overview")',
            'QLabel("Lowest Skills")',
            'QLabel("Active Long-Term Goal")',
            'QLabel("Recent Progress")',
            'QLabel("Playstyle Insights")',
        ]:
            self.assertIn(token, source)

    def test_mockup_visual_tokens_exist(self):
        for token in [
            "QFrame#DashboardHero",
            "QFrame#DashboardCard",
            "QFrame#OverviewTile",
            "QFrame#PathCard",
            "QFrame#DiaryCard",
            "QPushButton#HeroGenerate",
            "QLabel#HeroHeading",
            "QLabel#GoldPill",
        ]:
            self.assertIn(token, APP_STYLESHEET)


if __name__ == "__main__":
    unittest.main()
