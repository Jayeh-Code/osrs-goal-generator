from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_WINDOW = PROJECT_ROOT / "src" / "osrs_goal_generator" / "gui" / "main_window.py"


class Alpha67Tests(unittest.TestCase):
    def test_lowest_skill_layout_is_attached_to_card(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn("skill_layout.addLayout(self.skill_box, 1)", source)

    def test_lowest_skill_rows_still_update_in_place(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn("self.lowest_skill_rows", source)
        self.assertIn("for index, widgets in enumerate(self.lowest_skill_rows):", source)
        self.assertNotIn("self._clear_layout(self.skill_box)", source)


if __name__ == "__main__":
    unittest.main()

# Additional Alpha 6.7 regression coverage is appended here so the build can
# verify both the Home-card repair and the Surprise Me category-balancing fix.
import random
import sys

sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from osrs_goal_generator.engine.goal_engine import GoalEngine
from osrs_goal_generator.engine.scoring import ScoringContext
from osrs_goal_generator.models import GoalFilters
from test_core import profile_fixture


class Alpha67SurpriseTests(unittest.TestCase):
    def test_surprise_me_reaches_all_available_goal_categories(self):
        engine = GoalEngine(random.Random(42))
        filters = GoalFilters("surprise me", "moderate", 60)
        categories = {
            engine.choose_goal(
                profile_fixture(),
                filters,
                ScoringContext(session_minutes=60),
            ).category
            for _ in range(40)
        }
        self.assertEqual(
            categories,
            {"skilling", "bossing", "clues", "collection", "progression", "money"},
        )

    def test_surprise_me_is_not_skilling_only(self):
        engine = GoalEngine(random.Random(7))
        filters = GoalFilters("surprise me", "moderate", 60)
        sequence = [
            engine.choose_goal(
                profile_fixture(),
                filters,
                ScoringContext(session_minutes=60),
            ).category
            for _ in range(12)
        ]
        self.assertIn("bossing", sequence)
        self.assertGreater(len(set(sequence)), 2)
