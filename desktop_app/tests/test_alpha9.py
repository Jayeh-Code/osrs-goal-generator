import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from osrs_goal_generator.models import Goal
from osrs_goal_generator.services.progress import GoalProgressService
from osrs_goal_generator.services.runelite_sync import RuneLiteSyncService
from osrs_goal_generator.services.storage import StateStore
from test_alpha2 import make_profile
from test_alpha8 import sample_sync


class Alpha9Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.profile = make_profile()
        self.service = GoalProgressService()
        self.raw = sample_sync()
        self.raw["skills"]["Agility"] = {"level":70,"xp":1500}
        self.snapshot = self.read()

    def read(self):
        p = self.path / "sync.json"
        p.write_text(json.dumps(self.raw),encoding="utf-8")
        return RuneLiteSyncService(p).load()

    def skill_goal(self):
        return Goal("test","now","skilling","skill_xp","Agility","Agility","Gain XP",[],
                    start_value=1000,target_value=2000,status="accepted")

    def test_live_skill_progress_and_remaining(self):
        goal = self.skill_goal()
        r = self.service.apply(goal,self.profile,self.snapshot)
        self.assertEqual(r.progress_percent,50)
        self.assertEqual(r.source,"RuneLite live")
        self.assertIn("500 XP remaining",r.label)

    def test_progress_checkpoint_survives_save_and_stale_hiscores(self):
        goal = self.skill_goal()
        self.service.apply(goal,self.profile,self.snapshot)
        store=StateStore(self.path / "state.json"); state=store.load()
        store.set_active_goal(state,self.profile,goal); store.save(state)
        restored=store.active_goal(store.load(),self.profile)
        self.profile.skills["Agility"].xp=1000
        r=self.service.apply(restored,self.profile)
        self.assertEqual(r.current_value,1500)
        self.assertEqual(r.source,"Last verified progress")

    def test_completion_timestamp_is_not_repeated(self):
        goal=self.skill_goal(); self.raw["skills"]["Agility"]["xp"]=2000
        self.service.apply(goal,self.profile,self.read())
        timestamp=goal.completed_at
        self.service.apply(goal,self.profile,self.read())
        self.assertEqual(goal.status,"completed")
        self.assertEqual(goal.completed_at,timestamp)

    def test_mismatched_snapshot_cannot_supply_xp(self):
        self.profile.skills["Agility"].xp=1000
        wrong=replace(self.snapshot,player_name="Other")
        self.assertEqual(self.service.evaluate(self.skill_goal(),self.profile,wrong).progress_percent,0)

    def test_collection_baseline_excludes_owned_items(self):
        goal=self.service.collection_goal(self.profile,self.snapshot,"Vorkath")
        self.assertEqual(goal.metadata["collection_item_ids"],[22001])
        self.assertFalse(self.service.evaluate(goal,self.profile,self.snapshot).completed)

    def test_only_tracked_item_can_complete_collection_goal(self):
        goal=self.service.collection_goal(self.profile,self.snapshot,"Vorkath")
        self.raw["collection_log"]["pages"]["Other"] = {"items":[{"item_id":999,"name":"Synthetic", "obtained":True}]}
        self.assertFalse(self.service.evaluate(goal,self.profile,self.read()).completed)
        self.raw["collection_log"]["pages"]["Vorkath"]["items"][1]["obtained"]=True
        self.assertTrue(self.service.evaluate(goal,self.profile,self.read()).completed)

    def test_cached_or_wrong_account_collection_never_completes(self):
        goal=self.service.collection_goal(self.profile,self.snapshot,"Vorkath")
        self.raw["collection_log"]["pages"]["Vorkath"]["items"][1]["obtained"]=True
        live=self.read()
        for snapshot in (replace(live,connected=False),replace(live,updated_at="2000-01-01T00:00:00Z"),
                         replace(live,player_name="Other"),replace(live,game_state="LOGIN_SCREEN")):
            self.assertFalse(self.service.evaluate(goal,self.profile,snapshot).completed)

    def test_incomplete_page_waits_without_fabricating_progress(self):
        goal=self.service.collection_goal(self.profile,self.snapshot,"Vorkath")
        self.raw["collection_log"]["pages"]["Vorkath"]["items"]=[]
        result=self.service.evaluate(goal,self.profile,self.read())
        self.assertFalse(result.verifiable)
        self.assertEqual(result.source,"Waiting for RuneLite")

    def test_collection_goal_requires_live_observed_missing_items(self):
        for snapshot,page in [(None,"Vorkath"),(self.snapshot,"Unknown")]:
            with self.assertRaises(ValueError): self.service.collection_goal(self.profile,snapshot,page)

    def test_boss_progress_remains_hiscores(self):
        goal=Goal("b","now","bossing","boss_kc","Vorkath","Boss","Kill",[],start_value=300,target_value=400)
        r=self.service.evaluate(goal,self.profile,self.snapshot)
        self.assertEqual(r.current_value,347)
        self.assertEqual(r.source,"HiScores")

    def test_gui_poll_persists_partial_and_archives_once(self):
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
        try:
            from PySide6.QtWidgets import QApplication
            from osrs_goal_generator.gui.main_window import MainWindow
        except ImportError:
            self.skipTest("PySide6 required for GUI integration test")
        app=QApplication.instance() or QApplication([])
        store=StateStore(self.path / "gui-state.json")
        reader=RuneLiteSyncService(self.path / "sync.json")
        with patch("osrs_goal_generator.gui.main_window.StateStore",return_value=store), \
             patch("osrs_goal_generator.gui.main_window.RuneLiteSyncService",return_value=reader), \
             patch.object(MainWindow,"_request_assets"), \
             patch("osrs_goal_generator.gui.main_window.QMessageBox.information") as message:
            window=MainWindow(); window.runelite_timer.stop()
            try:
                window.session.profile=self.profile
                goal=self.skill_goal()
                store.set_active_goal(window.state,self.profile,goal)
                window._poll_runelite_sync()
                self.assertEqual(store.active_goal(store.load(),self.profile).current_value,1500)
                self.assertIn("RuneLite live",window.home_active_status.text())
                self.raw["skills"]["Agility"]["xp"]=2000; self.read()
                window._poll_runelite_sync(); window._poll_runelite_sync()
                self.assertIsNone(store.active_goal(store.load(),self.profile))
                self.assertEqual(len(store.goal_history(store.load(),self.profile)),1)
                self.assertEqual(message.call_count,1)
                # Create through the actual collection action, accept, then
                # observe exactly one previously missing item being obtained.
                window._generate_live_collection_goal("Vorkath")
                self.assertEqual(window.session.current_goal.subtype,"collection_slot")
                window._accept_goal()
                self.assertIsNone(window.session.current_goal)
                self.assertIsNotNone(store.active_goal(window.state,self.profile))
                reader.path.write_text(json.dumps({**self.raw,"connected":False}),encoding="utf-8")
                window._poll_runelite_sync()
                self.assertIn("Waiting for RuneLite",window.home_active_status.text())
                self.raw["collection_log"]["pages"]["Vorkath"]["items"][1]["obtained"]=True
                self.read(); window._poll_runelite_sync(); window._poll_runelite_sync()
                self.assertIsNone(store.active_goal(store.load(),self.profile))
                self.assertEqual(len(store.goal_history(store.load(),self.profile)),2)
                self.assertEqual(message.call_count,3)  # skill completion, acceptance, collection completion
            finally:
                window.close(); window.deleteLater(); app.processEvents()
