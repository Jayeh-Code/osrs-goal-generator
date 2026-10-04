from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from osrs_goal_generator.config import VERSION
from osrs_goal_generator.services.storage import StateStore
from test_alpha2 import make_profile


ROOT = Path(__file__).resolve().parents[1]
MAIN_WINDOW = ROOT / "src" / "osrs_goal_generator" / "gui" / "main_window.py"
THEME = ROOT / "src" / "osrs_goal_generator" / "gui" / "theme.py"


class Alpha7Tests(unittest.TestCase):
    def test_version_is_alpha7(self):
        self.assertTrue(VERSION.startswith(("4.0.0-alpha.7", "4.0.0-alpha.8", "4.0.0-alpha.9", "4.0.0-beta.")))

    def test_collection_targets_round_trip_and_clamp(self):
        with tempfile.TemporaryDirectory() as folder:
            store = StateStore(Path(folder) / "state.json")
            state = store.load()
            profile = make_profile()
            store.save_collection_target(
                state,
                profile,
                {
                    "target_id": "vorkath-uniques",
                    "name": "Vorkath uniques",
                    "category": "Bosses",
                    "current": 9,
                    "total": 5,
                    "notes": "Manual from in-game log",
                },
            )
            store.save(state)
            loaded = store.collection_targets(store.load(), profile)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["current"], 5)
            self.assertEqual(loaded[0]["total"], 5)
            self.assertEqual(loaded[0]["category"], "Bosses")

    def test_collection_target_update_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            store = StateStore(Path(folder) / "state.json")
            state = store.load()
            profile = make_profile()
            target = {
                "target_id": "cox",
                "name": "CoX uniques",
                "category": "Raids",
                "current": 2,
                "total": 23,
                "notes": "",
            }
            store.save_collection_target(state, profile, target)
            target["current"] = 3
            store.save_collection_target(state, profile, target)
            self.assertEqual(len(store.collection_targets(state, profile)), 1)
            self.assertEqual(store.collection_targets(state, profile)[0]["current"], 3)

    def test_collection_target_delete(self):
        with tempfile.TemporaryDirectory() as folder:
            store = StateStore(Path(folder) / "state.json")
            state = store.load()
            profile = make_profile()
            store.save_collection_target(
                state,
                profile,
                {"target_id": "x", "name": "Test", "current": 0, "total": 1},
            )
            store.delete_collection_target(state, profile, "x")
            self.assertEqual(store.collection_targets(state, profile), [])

    def test_collection_log_is_real_page_not_placeholder(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn("self.collection_page = self._build_collection_page()", source)
        self.assertIn("def _render_collection", source)
        self.assertIn("Overall Collections Logged is verified from public HiScores", source)
        self.assertIn("Generate Collection Goal", source)
        self.assertIn("+ Track Grind", source)
        self.assertIn('card.setObjectName("CollectionCard")', source)

    def test_manual_collection_goal_updates_tracker_on_completion(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn('subtype="manual_collection_target"', source)
        self.assertIn('"collection_target_id": target_id', source)
        self.assertIn('collection_target_id = active.metadata.get("collection_target_id")', source)
        self.assertIn('target["current"] = int(target["current"]) + 1', source)

    def test_boss_detail_screen_exists(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn('"Favorite", "Boss / Activity", "KC", "Late-mid / h", "Session Target", "Goal", "Details"', source)
        self.assertIn("def _show_boss_detail", source)
        self.assertIn('QLabel("Session Targets")', source)
        self.assertIn('QPushButton("Generate Boss Goal")', source)

    def test_diary_detail_screen_exists(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn("def _show_diary_detail", source)
        self.assertIn('["Requirement", "Current", "Status", "Source"]', source)
        self.assertIn('details = QPushButton("Details")', source)
        self.assertIn('"HiScores" if item.measurable else "Manual"', source)

    def test_collection_card_is_part_of_visual_system(self):
        theme = THEME.read_text(encoding="utf-8")
        self.assertIn("QFrame#CollectionCard", theme)


if __name__ == "__main__":
    unittest.main()
