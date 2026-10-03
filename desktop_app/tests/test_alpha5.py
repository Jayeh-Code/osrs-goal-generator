from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from osrs_goal_generator.account_math import xp_for_level
from osrs_goal_generator.engine.goal_engine import GoalEngine
from osrs_goal_generator.engine.scoring import ScoringContext
from osrs_goal_generator.models import (
    Activity,
    GoalFilters,
    PathDefinition,
    PlayerProfile,
    Requirement,
    Skill,
)
from osrs_goal_generator.services.diaries import DiaryDataService
from osrs_goal_generator.services.progression import ProgressionService
from osrs_goal_generator.services.storage import StateStore


def make_profile() -> PlayerProfile:
    levels = {
        "Attack": 82,
        "Defence": 80,
        "Strength": 86,
        "Hitpoints": 88,
        "Ranged": 85,
        "Prayer": 77,
        "Magic": 86,
        "Agility": 70,
        "Mining": 79,
        "Slayer": 80,
        "Construction": 76,
        "Sailing": 65,
    }
    skills = {
        "Overall": Skill("Overall", 1, 1950, 120_000_000),
        **{
            name: Skill(name, 1, level, xp_for_level(level))
            for name, level in levels.items()
        },
    }
    return PlayerProfile(
        rsn="Alpha Five",
        account_type="normal",
        fetched_at="2026-09-27T20:00:00",
        skills=skills,
        activities={
            "Vorkath": Activity("Vorkath", 1, 240),
            "General Graardor": Activity("General Graardor", -1, -1),
        },
    )


class Alpha5Tests(unittest.TestCase):
    def test_custom_path_storage_round_trip_multiple_requirements(self) -> None:
        profile = make_profile()
        path = PathDefinition(
            path_id="custom:test",
            name="My Mixed Goal",
            category="custom",
            requirements=(
                Requirement("r1", "skill", "Agility", 80, "Agility 80"),
                Requirement("r2", "boss_kc", "Vorkath", 500, "Vorkath 500 KC"),
            ),
            is_custom=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(Path(tmp) / "state.json")
            state = store.load()
            store.save_custom_path(state, profile, path)
            store.save(state)
            loaded = store.custom_paths(store.load(), profile)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].name, "My Mixed Goal")
            self.assertEqual(len(loaded[0].requirements), 2)
            self.assertTrue(loaded[0].is_custom)

    def test_base_level_requirement_uses_lowest_skill(self) -> None:
        profile = make_profile()
        req = Requirement("base85", "base_level", "All Skills", 85, "Base 85s")
        result = ProgressionService().evaluate_requirement(req, profile)
        self.assertEqual(result.current_value, 65)
        self.assertFalse(result.completed)

    def test_base_level_path_generates_low_skill_goal(self) -> None:
        profile = make_profile()
        service = ProgressionService()
        path = PathDefinition(
            "custom:base85",
            "Base 85s",
            "custom",
            (Requirement("base85", "base_level", "All Skills", 85, "Base 85s"),),
            is_custom=True,
        )
        evaluation = service.evaluate_path(path, profile, "high")
        goal = GoalEngine(random.Random(1)).choose_path_goal(
            profile,
            evaluation,
            GoalFilters(category="progression", difficulty="moderate", session_minutes=60),
            ScoringContext(session_minutes=60),
        )
        self.assertEqual(goal.target_name, "Sailing")
        self.assertEqual(goal.metadata.get("source_path_id"), "custom:base85")

    def test_shared_blocker_wins_over_closer_isolated_requirement(self) -> None:
        profile = make_profile()
        p1 = PathDefinition(
            "custom:p1",
            "Path One",
            "custom",
            (
                Requirement("a80", "skill", "Agility", 80, "Agility 80"),
                Requirement("m80", "skill", "Mining", 80, "Mining 80"),
            ),
            is_custom=True,
        )
        p2 = PathDefinition(
            "custom:p2",
            "Path Two",
            "custom",
            (
                Requirement("a85", "skill", "Agility", 85, "Agility 85"),
                Requirement("s90", "skill", "Slayer", 90, "Slayer 90"),
            ),
            is_custom=True,
        )
        service = ProgressionService()
        service.set_custom_paths([p1, p2])
        evaluations = service.evaluate_active_paths(
            profile,
            [
                {"path_id": p1.path_id, "priority": "high"},
                {"path_id": p2.path_id, "priority": "high"},
            ],
        )
        by_id = {item.path.path_id: item for item in evaluations}
        self.assertEqual(by_id["custom:p1"].current_blocker.requirement.target, "Agility")
        scoring = service.scoring_data(
            profile,
            [
                {"path_id": p1.path_id, "priority": "high"},
                {"path_id": p2.path_id, "priority": "high"},
            ],
        )
        self.assertEqual(scoring.path_target_counts.get("Agility"), 2)
        self.assertIn("Agility", scoring.blocker_targets)

    def test_diary_parser_ignores_quests_and_keeps_measurable_requirements(self) -> None:
        raw = {
            "Testland|ELITE": {
                "skills": [{"skill": "AGILITY", "level": 80}],
                "prereqQuests": ["SOME_QUEST"],
                "bossKills": [{"bossName": "Vorkath", "killCount": 1}],
                "unlocks": [],
                "itemReqs": [{"itemId": 1, "displayName": "Thing", "quantity": 1}],
                "accountReqs": [],
            }
        }
        definitions = DiaryDataService.parse(raw)
        self.assertEqual(len(definitions), 1)
        diary = definitions[0]
        kinds = [req.kind for req in diary.requirements]
        self.assertIn("skill", kinds)
        self.assertIn("boss_kc", kinds)
        self.assertIn("manual", kinds)
        self.assertTrue(all(req.kind != "quest" for req in diary.requirements))
        self.assertEqual(diary.manual_requirement_count, 1)

    def test_diary_tracking_and_manual_completion_persist(self) -> None:
        profile = make_profile()
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(Path(tmp) / "state.json")
            state = store.load()
            store.track_diary(state, profile, "ardougne:elite")
            self.assertEqual(store.active_diaries(state, profile)[0]["diary_id"], "ardougne:elite")
            store.mark_diary_complete(state, profile, "ardougne:elite")
            self.assertNotIn("ardougne:elite", {x["diary_id"] for x in store.active_diaries(state, profile)})
            self.assertIn("ardougne:elite", store.completed_diaries(state, profile))
            store.restore_diary(state, profile, "ardougne:elite")
            self.assertNotIn("ardougne:elite", store.completed_diaries(state, profile))

    def test_tracked_diary_can_feed_cross_path_scoring(self) -> None:
        profile = make_profile()
        raw = {
            "Testland|ELITE": {
                "skills": [{"skill": "AGILITY", "level": 80}],
                "prereqQuests": [],
                "bossKills": [],
                "unlocks": [],
                "itemReqs": [],
                "accountReqs": [],
            }
        }
        diary = DiaryDataService.parse(raw)[0]
        diary_path = DiaryDataService.as_path(diary)
        custom = PathDefinition(
            "custom:agility",
            "Agility Goal",
            "custom",
            (Requirement("a85", "skill", "Agility", 85, "Agility 85"),),
            is_custom=True,
        )
        service = ProgressionService()
        service.set_custom_paths([custom])
        service.set_external_paths([diary_path])
        scoring = service.scoring_data(
            profile,
            [
                {"path_id": custom.path_id, "priority": "high"},
                {"path_id": diary_path.path_id, "priority": "medium"},
            ],
        )
        self.assertEqual(scoring.path_target_counts.get("Agility"), 2)


if __name__ == "__main__":
    unittest.main()
