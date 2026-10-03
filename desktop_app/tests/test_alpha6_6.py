from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from osrs_goal_generator.services.storage import StateStore
from test_alpha2 import make_profile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_WINDOW = PROJECT_ROOT / "src" / "osrs_goal_generator" / "gui" / "main_window.py"


class Alpha66Tests(unittest.TestCase):
    def test_reroll_memory_can_be_cleared_without_touching_other_preferences(self):
        with tempfile.TemporaryDirectory() as folder:
            store = StateStore(Path(folder) / "state.json")
            state = store.load()
            profile = make_profile()
            store.record_reroll(state, profile, "Vorkath")
            store.record_reroll(state, profile, "Zulrah")
            store.block_target(state, profile, "Cerberus")

            store.clear_rerolls(state, profile)
            prefs = store.preferences(state, profile)
            self.assertEqual(prefs["rerolled_targets"], [])
            self.assertIn("Cerberus", prefs["blocked_targets"])

    def test_settings_exposes_clear_reroll_memory(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn('QPushButton("Clear Reroll Memory")', source)
        self.assertIn("def _clear_reroll_memory", source)
        self.assertIn("self.store.clear_rerolls(self.state, profile)", source)

    def test_lowest_skills_uses_persistent_rows(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn("self.lowest_skill_rows", source)
        self.assertIn("for _ in range(5):", source)
        # Alpha 6.5 rebuilt/deleted the entire panel during every Home refresh.
        self.assertNotIn("self._clear_layout(self.skill_box)", source)

    def test_lowest_skills_card_has_stable_minimum_height(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn("skill_card.setMinimumHeight(250)", source)


if __name__ == "__main__":
    unittest.main()
