import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from osrs_goal_generator.services.bridge_status import bridge_status
from osrs_goal_generator.services.progress import GoalProgressService
from osrs_goal_generator.services.runelite_sync import RuneLiteSyncService
from test_alpha2 import make_profile
from test_alpha8 import sample_sync


class BridgeStatusTests(unittest.TestCase):
    def setUp(self):
        self.profile = make_profile()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'sync.json'
            path.write_text(json.dumps(sample_sync()))
            self.snapshot = RuneLiteSyncService(path).load()

    def test_missing_and_unreadable_are_distinct(self):
        self.assertEqual(bridge_status(None, self.profile).title, 'RUNELITE NOT DETECTED')
        self.assertEqual(bridge_status(None, self.profile, file_exists=True).title, 'BRIDGE UNAVAILABLE')

    def test_disconnect_and_stale_explain_fallback(self):
        status = bridge_status(replace(self.snapshot, connected=False), self.profile)
        self.assertEqual(status.title, 'RUNELITE DISCONNECTED')
        self.assertIn('HiScores', status.detail)
        self.assertEqual(bridge_status(replace(self.snapshot, updated_at='2000-01-01T00:00:00Z'), self.profile).title, 'RUNELITE NOT UPDATING')

    def test_wrong_account_is_never_live(self):
        status = bridge_status(replace(self.snapshot, player_name='Other account'), self.profile)
        self.assertEqual(status.title, 'ACCOUNT MISMATCH')
        self.assertFalse(status.live)

    def test_connection_without_loaded_account_has_next_step(self):
        status = bridge_status(self.snapshot, None)
        self.assertEqual(status.title, 'RUNELITE CONNECTED')
        self.assertIn('Load that account', status.detail)

    def test_fresh_non_logged_in_state_is_disconnected(self):
        self.assertEqual(bridge_status(replace(self.snapshot, game_state='LOGIN_SCREEN'), self.profile).title, 'RUNELITE DISCONNECTED')

    def test_collection_heartbeat_does_not_claim_pages_are_current(self):
        goal = GoalProgressService().collection_goal(self.profile, self.snapshot, 'Vorkath')
        status = bridge_status(self.snapshot, self.profile, goal)
        self.assertTrue(status.live)
        self.assertIn('Reopen', status.detail)
        self.assertIn('Vorkath', status.detail)

    def test_missing_page_requests_refresh(self):
        goal = GoalProgressService().collection_goal(self.profile, self.snapshot, 'Vorkath')
        status = bridge_status(replace(self.snapshot, collection_pages={}), self.profile, goal)
        self.assertEqual(status.title, 'WAITING FOR PAGE REFRESH')
        self.assertTrue(status.live)

    def test_unlock_hint_requests_refresh_without_completing_goal(self):
        service = GoalProgressService()
        goal = service.collection_goal(self.profile, self.snapshot, 'Vorkath')
        snapshot = replace(self.snapshot, session={'last_event':'collection_unlock:Jar of decay'})
        self.assertEqual(bridge_status(snapshot, self.profile, goal).title, 'WAITING FOR PAGE REFRESH')
        self.assertFalse(service.evaluate(goal, self.profile, snapshot).completed)

    def test_unrelated_unlock_does_not_request_tracked_page_refresh(self):
        goal = GoalProgressService().collection_goal(self.profile, self.snapshot, 'Vorkath')
        snapshot = replace(self.snapshot, session={'last_event':'collection_unlock:Other item'})
        self.assertEqual(bridge_status(snapshot, self.profile, goal).title, 'RUNELITE LIVE')
