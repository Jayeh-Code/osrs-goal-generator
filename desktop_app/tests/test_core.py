import json
import random
import unittest
from unittest.mock import patch

from osrs_goal_generator.account_math import combat_level, xp_for_level, xp_to_next_level
from osrs_goal_generator.engine.goal_engine import GoalEngine
from osrs_goal_generator.engine.scoring import ScoringContext
from osrs_goal_generator.models import Activity, GoalFilters, PlayerProfile, Skill
from osrs_goal_generator.services.hiscores import HiscoresClient


def profile_fixture():
    names = [
        "Attack", "Strength", "Defence", "Hitpoints", "Ranged", "Prayer", "Magic",
        "Cooking", "Woodcutting", "Fletching", "Fishing", "Firemaking", "Crafting",
        "Smithing", "Mining", "Herblore", "Agility", "Thieving", "Slayer", "Farming",
        "Runecraft", "Hunter", "Construction", "Sailing",
    ]
    skills = {"Overall": Skill("Overall", 1, 1800, 100_000_000)}
    for i, name in enumerate(names):
        level = 70 + (i % 10)
        skills[name] = Skill(name, i + 1, level, xp_for_level(level) + 1000)
    activities = {
        "Vorkath": Activity("Vorkath", 1000, 347),
        "Clue Scrolls (hard)": Activity("Clue Scrolls (hard)", 2000, 87),
        "Collections Logged": Activity("Collections Logged", 5000, 417),
    }
    return PlayerProfile("Test", "normal", "2026-09-27T12:00:00", skills, activities)


class CoreTests(unittest.TestCase):
    def test_xp_table(self):
        self.assertEqual(xp_for_level(2), 83)
        self.assertEqual(xp_for_level(99), 13_034_431)

    def test_combat_level(self):
        self.assertGreater(combat_level(profile_fixture()), 3)

    def test_goal_engine_generates(self):
        engine = GoalEngine(random.Random(1))
        filters = GoalFilters("surprise me", "moderate", 60)
        goal = engine.choose_goal(profile_fixture(), filters, ScoringContext(session_minutes=60))
        self.assertTrue(goal.objective)
        self.assertGreater(goal.score, 0)

    def test_json_hiscores_parser_contract(self):
        payload = json.dumps({
            "skills": [
                {"name": "Overall", "rank": 1, "level": 2000, "xp": 123456789},
                {"name": "Attack", "rank": 2, "level": 99, "xp": 13034431},
            ],
            "activities": [
                {"name": "Vorkath", "rank": 3, "score": 500},
            ],
        }).encode()

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return payload

        with patch("osrs_goal_generator.services.hiscores.urlopen", return_value=FakeResponse()):
            profile = HiscoresClient().fetch("Test Player")
        self.assertEqual(profile.skill("Attack").level, 99)
        self.assertEqual(profile.activity("Vorkath").score, 500)


if __name__ == "__main__":
    unittest.main()
