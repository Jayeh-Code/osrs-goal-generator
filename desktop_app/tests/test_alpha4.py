from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from osrs_goal_generator.account_math import xp_for_level
from osrs_goal_generator.engine.goal_engine import GoalEngine
from osrs_goal_generator.engine.scoring import ScoringContext
from osrs_goal_generator.models import Activity, Goal, GoalFilters, PlayerProfile, Skill
from osrs_goal_generator.services.analytics import AnalyticsService
from osrs_goal_generator.services.progression import ProgressionService
from osrs_goal_generator.services.storage import StateStore


def make_profile(
    *,
    rsn: str = "Alpha Tester",
    overall_level: int = 1900,
    overall_xp: int = 100_000_000,
    agility_level: int = 70,
    agility_xp: int | None = None,
    slayer_level: int = 80,
    slayer_xp: int | None = None,
    vorkath: int = 0,
    fetched_at: str = "2026-09-27T10:00:00",
) -> PlayerProfile:
    agility_xp = xp_for_level(agility_level) if agility_xp is None else agility_xp
    slayer_xp = xp_for_level(slayer_level) if slayer_xp is None else slayer_xp
    skills = {
        "Overall": Skill("Overall", 1, overall_level, overall_xp),
        "Agility": Skill("Agility", 1, agility_level, agility_xp),
        "Slayer": Skill("Slayer", 1, slayer_level, slayer_xp),
    }
    return PlayerProfile(
        rsn=rsn,
        account_type="normal",
        fetched_at=fetched_at,
        skills=skills,
        activities={"Vorkath": Activity("Vorkath", 1 if vorkath else -1, vorkath if vorkath else -1)},
    )


class Alpha4Tests(unittest.TestCase):
    def test_boss_favorites_persist_per_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(Path(tmp) / "state.json")
            state = store.load()
            profile = make_profile()
            self.assertTrue(store.toggle_favorite_boss(state, profile, "Vorkath"))
            self.assertIn("Vorkath", store.favorite_bosses(state, profile))
            store.save(state)
            state2 = store.load()
            self.assertIn("Vorkath", store.favorite_bosses(state2, profile))
            self.assertFalse(store.toggle_favorite_boss(state2, profile, "Vorkath"))
            self.assertNotIn("Vorkath", store.favorite_bosses(state2, profile))

    def test_analytics_uses_first_and_last_snapshots(self) -> None:
        first = make_profile()
        last = make_profile(
            overall_level=1902,
            overall_xp=101_500_000,
            agility_level=71,
            agility_xp=xp_for_level(71) + 5_000,
            slayer_level=81,
            slayer_xp=xp_for_level(81) + 10_000,
            vorkath=12,
            fetched_at="2026-09-29T10:00:00",
        )
        history = [
            Goal("g1", "2026-09-27T11:00:00", "skilling", "skill_xp", "Agility", "Agility", "", [], status="completed"),
            Goal("g2", "2026-09-28T11:00:00", "bossing", "boss_kc", "Vorkath", "Vorkath", "", [], status="cancelled"),
        ]
        summary = AnalyticsService().summarize([first, last], history)
        self.assertEqual(summary.total_xp_gained, 1_500_000)
        self.assertEqual(summary.total_levels_gained, 2)
        self.assertEqual(summary.completed_tasks, 1)
        self.assertEqual(summary.cancelled_tasks, 1)
        self.assertEqual(summary.completion_rate, 50.0)
        self.assertTrue(any(item.name == "Vorkath" and item.delta == 12 for item in summary.activity_gains))
        self.assertEqual(summary.tracking_days, 2)

    def test_path_specific_goal_targets_current_blocker(self) -> None:
        profile = make_profile(agility_level=70, slayer_level=80)
        service = ProgressionService()
        path = service.definition("slayer_95")
        assert path is not None
        evaluation = service.evaluate_path(path, profile, "high")
        engine = GoalEngine(random.Random(1))
        filters = GoalFilters(category="progression", difficulty="moderate", session_minutes=60)
        goal = engine.choose_path_goal(profile, evaluation, filters, ScoringContext(session_minutes=60))
        self.assertEqual(goal.target_name, "Slayer")
        self.assertEqual(goal.category, "progression")
        self.assertEqual(goal.metadata.get("source_path_id"), "slayer_95")
        self.assertTrue(any("95 Slayer" in reason for reason in goal.reasons))

    def test_total_level_path_generates_trainable_skill_goal(self) -> None:
        profile = make_profile(overall_level=1900, agility_level=70, slayer_level=80)
        service = ProgressionService()
        path = service.definition("total_2000")
        assert path is not None
        evaluation = service.evaluate_path(path, profile, "high")
        goal = GoalEngine(random.Random(1)).choose_path_goal(
            profile,
            evaluation,
            GoalFilters(category="progression", difficulty="chill", session_minutes=30),
            ScoringContext(session_minutes=30),
        )
        self.assertIn(goal.target_name, {"Agility", "Slayer"})
        self.assertEqual(goal.metadata.get("source_path_id"), "total_2000")

    def test_completed_path_is_hidden_from_available_definitions(self) -> None:
        profile = make_profile(overall_level=2200, agility_level=99, slayer_level=99)
        service = ProgressionService()
        available_ids = {path.path_id for path in service.incomplete_definitions(profile)}
        self.assertNotIn("total_2000", available_ids)
        self.assertNotIn("total_2200", available_ids)
        self.assertNotIn("slayer_95", available_ids)
        self.assertNotIn("slayer_99", available_ids)

    def test_completed_active_path_is_not_returned_for_scoring_or_home(self) -> None:
        profile = make_profile(overall_level=2000, agility_level=70, slayer_level=95)
        service = ProgressionService()
        evaluations = service.evaluate_active_paths(
            profile,
            [{"path_id": "slayer_95", "priority": "high"}],
        )
        self.assertEqual(evaluations, [])


if __name__ == "__main__":
    unittest.main()
