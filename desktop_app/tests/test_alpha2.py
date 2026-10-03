import json
import random
import tempfile
import unittest
from pathlib import Path

from osrs_goal_generator.account_math import xp_for_level
from osrs_goal_generator.engine.goal_engine import GoalEngine
from osrs_goal_generator.engine.scoring import ScoringContext
from osrs_goal_generator.models import Activity, Goal, GoalFilters, PlayerProfile, Skill
from osrs_goal_generator.services.progress import GoalProgressService, compare_profiles
from osrs_goal_generator.services.storage import StateStore


def make_profile(agility_xp=None, vorkath=347):
    agility_xp = agility_xp if agility_xp is not None else xp_for_level(70) + 1_000
    skills = {
        "Overall": Skill("Overall", 1, 1800, 100_000_000),
        "Attack": Skill("Attack", 1, 80, xp_for_level(80)),
        "Strength": Skill("Strength", 1, 80, xp_for_level(80)),
        "Defence": Skill("Defence", 1, 80, xp_for_level(80)),
        "Hitpoints": Skill("Hitpoints", 1, 80, xp_for_level(80)),
        "Ranged": Skill("Ranged", 1, 80, xp_for_level(80)),
        "Prayer": Skill("Prayer", 1, 70, xp_for_level(70)),
        "Magic": Skill("Magic", 1, 80, xp_for_level(80)),
        "Agility": Skill("Agility", 1, 70, agility_xp),
        "Runecraft": Skill("Runecraft", 1, 71, xp_for_level(71)),
    }
    activities = {
        "Vorkath": Activity("Vorkath", 1, vorkath),
        "Collections Logged": Activity("Collections Logged", 1, 400),
    }
    return PlayerProfile("Test Player", "normal", "2026-09-27T17:00:00", skills, activities)


class Alpha2Tests(unittest.TestCase):
    def test_skill_goal_progress_uses_xp(self):
        profile = make_profile()
        goal = Goal(
            goal_id="g1",
            generated_at="now",
            category="skilling",
            subtype="skill_level",
            target_name="Agility",
            title="Agility Progress",
            objective="Train Agility to 71",
            reasons=[],
            start_value=xp_for_level(70),
            target_value=xp_for_level(71),
            status="accepted",
        )
        mid_xp = (xp_for_level(70) + xp_for_level(71)) // 2
        profile.skills["Agility"].xp = mid_xp
        result = GoalProgressService().evaluate(goal, profile)
        self.assertTrue(result.verifiable)
        self.assertGreater(result.progress_percent, 45)
        self.assertLess(result.progress_percent, 55)

    def test_boss_goal_completes_on_refresh(self):
        goal = Goal(
            goal_id="boss1",
            generated_at="now",
            category="bossing",
            subtype="boss_kc",
            target_name="Vorkath",
            title="Vorkath KC",
            objective="347 to 357",
            reasons=[],
            start_value=347,
            target_value=357,
            status="accepted",
        )
        profile = make_profile(vorkath=360)
        result = GoalProgressService().apply(goal, profile)
        self.assertTrue(result.completed)
        self.assertEqual(goal.status, "completed")
        self.assertEqual(goal.progress_percent, 100.0)

    def test_profile_comparison(self):
        previous = make_profile(vorkath=347)
        current = make_profile(vorkath=352)
        current.skills["Agility"].xp += 12_345
        changes = compare_profiles(previous, current)
        self.assertEqual(changes["activities"][0]["delta"], 5)
        self.assertEqual(changes["skills"][0]["xp_delta"], 12_345)

    def test_storage_tracks_active_goal_and_history(self):
        with tempfile.TemporaryDirectory() as folder:
            store = StateStore(Path(folder) / "state.json")
            state = store.load()
            profile = make_profile()
            store.save_profile(state, profile)
            goal = Goal(
                goal_id="abc",
                generated_at="now",
                category="bossing",
                subtype="boss_kc",
                target_name="Vorkath",
                title="Vorkath KC",
                objective="347 to 357",
                reasons=[],
                start_value=347,
                target_value=357,
                status="accepted",
            )
            store.set_active_goal(state, profile, goal)
            store.save(state)
            loaded = store.load()
            self.assertEqual(store.active_goal(loaded, profile).goal_id, "abc")
            self.assertEqual(len(store.goal_history(loaded, profile)), 1)

    def test_blocked_target_is_not_selected(self):
        profile = make_profile()
        engine = GoalEngine(random.Random(2))
        filters = GoalFilters(category="bossing", difficulty="moderate", session_minutes=60)
        context = ScoringContext(session_minutes=60, blocked_targets={"Vorkath"})
        goal = engine.choose_goal(profile, filters, context)
        self.assertNotEqual(goal.target_name, "Vorkath")
        with self.assertRaises(ValueError):
            engine.choose_boss_goal(profile, "Vorkath", filters, context)

    def test_cancelled_active_goal_is_archived(self):
        with tempfile.TemporaryDirectory() as folder:
            store = StateStore(Path(folder) / "state.json")
            state = store.load()
            profile = make_profile()
            goal = Goal(
                goal_id="cancel-me",
                generated_at="now",
                category="skilling",
                subtype="skill_xp",
                target_name="Agility",
                title="Agility Progress",
                objective="Gain XP",
                reasons=[],
                start_value=xp_for_level(70),
                target_value=xp_for_level(71),
                status="accepted",
            )
            store.set_active_goal(state, profile, goal)
            archived = store.archive_active_goal(state, profile, "cancelled")
            self.assertIsNotNone(archived)
            self.assertIsNone(store.active_goal(state, profile))
            self.assertEqual(store.goal_history(state, profile)[-1].status, "cancelled")

    def test_blocked_active_goal_can_be_archived(self):
        with tempfile.TemporaryDirectory() as folder:
            store = StateStore(Path(folder) / "state.json")
            state = store.load()
            profile = make_profile()
            goal = Goal(
                goal_id="block-me",
                generated_at="now",
                category="bossing",
                subtype="boss_kc",
                target_name="Vorkath",
                title="Vorkath KC",
                objective="347 to 357",
                reasons=[],
                start_value=347,
                target_value=357,
                status="accepted",
            )
            store.set_active_goal(state, profile, goal)
            store.block_target(state, profile, "Vorkath")
            store.archive_active_goal(state, profile, "blocked")
            self.assertIn("Vorkath", store.preferences(state, profile)["blocked_targets"])
            self.assertIsNone(store.active_goal(state, profile))
            self.assertEqual(store.goal_history(state, profile)[-1].status, "blocked")

    def test_reroll_penalty_is_applied(self):
        profile = make_profile()
        engine = GoalEngine(random.Random(1))
        filters = GoalFilters(category="bossing", difficulty="moderate", session_minutes=60)
        candidate = engine._boss_candidate(profile, "Vorkath", filters)
        context = ScoringContext(session_minutes=60, rerolled_targets=["Vorkath"])
        engine.scorer.score(candidate, context)
        self.assertLess(candidate.score.variety, -20)


if __name__ == "__main__":
    unittest.main()
