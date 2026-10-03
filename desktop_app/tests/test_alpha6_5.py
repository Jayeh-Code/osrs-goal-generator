from __future__ import annotations

import json
import random
import unittest
from pathlib import Path

from osrs_goal_generator.engine.goal_engine import GoalEngine
from osrs_goal_generator.engine.scoring import ScoringContext
from osrs_goal_generator.models import GoalFilters
from osrs_goal_generator.services.wiki_assets import BUNDLED_BOSS_ICON_DIR, BUNDLED_BOSS_MANIFEST
from test_core import profile_fixture


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_WINDOW = PROJECT_ROOT / "src" / "osrs_goal_generator" / "gui" / "main_window.py"
GOAL_ENGINE = PROJECT_ROOT / "src" / "osrs_goal_generator" / "engine" / "goal_engine.py"


class SpyRandom:
    def __init__(self):
        self.population_size = 0

    def shuffle(self, sequence):
        # Deterministic no-op: the test only needs to inspect the full draw pool.
        return None

    def choices(self, population, weights=None, k=1):
        self.population_size = len(population)
        return [population[-1]]


class Alpha65Tests(unittest.TestCase):
    def test_every_boss_has_a_local_png(self):
        manifest = json.loads(BUNDLED_BOSS_MANIFEST.read_text(encoding="utf-8"))["bosses"]
        self.assertEqual(len(manifest), 71)
        for boss, record in manifest.items():
            self.assertTrue((BUNDLED_BOSS_ICON_DIR / record["file"]).is_file(), boss)

    def test_bossing_draw_uses_full_pool_not_top_seven(self):
        rng = SpyRandom()
        engine = GoalEngine(rng)
        filters = GoalFilters("bossing", "moderate", 60)
        engine.choose_goal(
            profile_fixture(),
            filters,
            ScoringContext(session_minutes=60),
        )
        self.assertGreater(rng.population_size, 50)

    def test_repeated_boss_rerolls_are_random_and_varied(self):
        engine = GoalEngine(random.Random(42))
        filters = GoalFilters("bossing", "moderate", 60)
        rerolled: list[str] = []
        sequence: list[str] = []
        for _ in range(15):
            goal = engine.choose_goal(
                profile_fixture(),
                filters,
                ScoringContext(session_minutes=60, rerolled_targets=list(rerolled)),
            )
            sequence.append(goal.target_name)
            rerolled.insert(0, goal.target_name)
            del rerolled[8:]

        self.assertGreaterEqual(len(set(sequence)), 12)
        self.assertNotEqual(sequence, sorted(sequence, key=str.casefold))

    def test_recent_rerolls_are_temporarily_held_out(self):
        engine = GoalEngine(random.Random(7))
        filters = GoalFilters("bossing", "moderate", 60)
        context = ScoringContext(
            session_minutes=60,
            rerolled_targets=["Vorkath", "Zulrah", "Cerberus"],
        )
        for _ in range(20):
            goal = engine.choose_goal(profile_fixture(), filters, context)
            self.assertNotIn(goal.target_name, {"Vorkath", "Zulrah", "Cerberus"})

    def test_boss_action_columns_are_hardened(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn("self.boss_table.setColumnWidth(0, 112)", source)
        self.assertIn("favorite_button.setMinimumSize(82, 40)", source)
        self.assertIn("self.boss_table.setColumnWidth(5, 188)", source)
        self.assertIn("button.setMinimumSize(156, 40)", source)

    def test_old_top_seven_boss_bottleneck_is_gone(self):
        source = GOAL_ENGINE.read_text(encoding="utf-8")
        self.assertIn('if filters.category == "bossing":', source)
        self.assertIn("_choose_bossing_candidate", source)
        self.assertIn("Weighted selection then samples the entire remaining pool", source)


if __name__ == "__main__":
    unittest.main()
