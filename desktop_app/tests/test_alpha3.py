import random
import tempfile
import unittest
from pathlib import Path

from osrs_goal_generator.account_math import xp_for_level
from osrs_goal_generator.boss_rates import BOSS_RATES, boss_rate
from osrs_goal_generator.engine.goal_engine import GoalEngine
from osrs_goal_generator.models import Activity, GoalFilters, PlayerProfile, Skill
from osrs_goal_generator.services.progress import GoalProgressService, compare_profiles
from osrs_goal_generator.services.progression import ProgressionService
from osrs_goal_generator.services.storage import StateStore


def make_profile(vorkath=-1, total=1900, slayer=82):
    names = [
        "Attack", "Defence", "Strength", "Hitpoints", "Ranged", "Prayer", "Magic",
        "Cooking", "Woodcutting", "Fletching", "Fishing", "Firemaking", "Crafting",
        "Smithing", "Mining", "Herblore", "Agility", "Thieving", "Slayer", "Farming",
        "Runecraft", "Hunter", "Construction", "Sailing",
    ]
    skills = {"Overall": Skill("Overall", 1, total, 100_000_000)}
    for i, name in enumerate(names):
        level = 82 if name != "Slayer" else slayer
        skills[name] = Skill(name, i + 2, level, xp_for_level(level) + 1000)
    activities = {"Vorkath": Activity("Vorkath", -1 if vorkath < 0 else 1, vorkath)}
    return PlayerProfile("Alpha Three", "normal", "2026-09-27T17:30:00", skills, activities)


class Alpha3Tests(unittest.TestCase):
    def test_boss_rate_table_is_broad(self):
        self.assertGreaterEqual(len(BOSS_RATES), 65)
        self.assertIn("Vorkath", BOSS_RATES)
        self.assertIn("The Corrupted Gauntlet", BOSS_RATES)

    def test_boss_intensity_changes_target(self):
        profile = make_profile(vorkath=100)
        engine = GoalEngine(random.Random(1))
        targets = []
        for difficulty in ("chill", "moderate", "grind"):
            goal = engine.choose_boss_goal(
                profile,
                "Vorkath",
                GoalFilters("bossing", difficulty, 60),
            )
            targets.append(goal.target_value - goal.start_value)
        self.assertLess(targets[0], targets[1])
        self.assertLess(targets[1], targets[2])
        self.assertLessEqual(targets[2], boss_rate("Vorkath").benchmark_rate)

    def test_boss_session_length_changes_target(self):
        profile = make_profile(vorkath=100)
        engine = GoalEngine(random.Random(1))
        half_hour = engine.choose_boss_goal(
            profile, "Vorkath", GoalFilters("bossing", "moderate", 30)
        )
        hour = engine.choose_boss_goal(
            profile, "Vorkath", GoalFilters("bossing", "moderate", 60)
        )
        self.assertLess(half_hour.target_value, hour.target_value)

    def test_unranked_boss_is_zero_kc_and_targetable(self):
        profile = make_profile(vorkath=-1)
        goal = GoalEngine(random.Random(1)).choose_boss_goal(
            profile, "Vorkath", GoalFilters("bossing", "moderate", 60)
        )
        self.assertEqual(goal.start_value, 0)
        self.assertGreater(goal.target_value, 0)

    def test_zero_kc_progress_is_verifiable(self):
        profile = make_profile(vorkath=-1)
        goal = GoalEngine(random.Random(1)).choose_boss_goal(
            profile, "Vorkath", GoalFilters("bossing", "moderate", 60)
        )
        result = GoalProgressService().evaluate(goal, profile)
        self.assertTrue(result.verifiable)
        self.assertEqual(result.current_value, 0)
        self.assertEqual(result.progress_percent, 0.0)

    def test_first_boss_kc_is_visible_as_progress(self):
        previous = make_profile(vorkath=-1)
        current = make_profile(vorkath=3)
        changes = compare_profiles(previous, current)
        vorkath = next(item for item in changes["activities"] if item["name"] == "Vorkath")
        self.assertEqual(vorkath["old"], 0)
        self.assertEqual(vorkath["new"], 3)
        self.assertEqual(vorkath["delta"], 3)

    def test_special_boss_is_not_farmable(self):
        profile = make_profile()
        with self.assertRaises(ValueError):
            GoalEngine().choose_boss_goal(
                profile, "Mimic", GoalFilters("bossing", "moderate", 60)
            )

    def test_progression_path_evaluates(self):
        profile = make_profile(total=1900, slayer=82)
        service = ProgressionService()
        path = service.definition("slayer_95")
        evaluation = service.evaluate_path(path, profile, "high")
        self.assertFalse(evaluation.current_blocker.completed)
        self.assertEqual(evaluation.current_blocker.requirement.target, "Slayer")

    def test_active_path_feeds_scoring_targets(self):
        profile = make_profile(slayer=82)
        data = ProgressionService().scoring_data(
            profile, [{"path_id": "slayer_95", "priority": "high"}]
        )
        self.assertIn("Slayer", data.active_path_targets)
        self.assertIn("Slayer", data.blocker_targets)
        self.assertGreater(data.path_priority_bonus["Slayer"], 0)

    def test_path_storage_round_trip(self):
        profile = make_profile()
        with tempfile.TemporaryDirectory() as folder:
            store = StateStore(Path(folder) / "state.json")
            state = store.load()
            store.activate_path(state, profile, "base_90s", "critical")
            store.save(state)
            loaded = store.load()
            paths = store.active_paths(loaded, profile)
            self.assertEqual(paths, [{"path_id": "base_90s", "priority": "critical"}])
            store.deactivate_path(loaded, profile, "base_90s")
            self.assertEqual(store.active_paths(loaded, profile), [])


if __name__ == "__main__":
    unittest.main()
