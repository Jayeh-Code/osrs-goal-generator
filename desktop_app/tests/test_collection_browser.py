import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from osrs_goal_generator.services.storage import StateStore
from osrs_goal_generator.services.runelite_sync import RuneLiteSyncService
from test_alpha2 import make_profile
from test_alpha8 import sample_sync


class CollectionBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest("PySide6 needed for collection browser integration")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from osrs_goal_generator.gui.main_window import MainWindow
        self.context = ExitStack()
        self.addCleanup(self.context.close)
        folder = self.context.enter_context(tempfile.TemporaryDirectory())
        self.store = StateStore(Path(folder) / "state.json")
        self.path = Path(folder) / "sync.json"
        self.raw = sample_sync()
        original = self.raw["collection_log"]["pages"]["Vorkath"]
        self.raw["collection_log"]["pages"] = {name:json.loads(json.dumps(original)) for name in ("Alpha", "Completed page", "Zeta")}
        for item in self.raw["collection_log"]["pages"]["Completed page"]["items"]:
            item["obtained"] = True
        self.write()
        reader = RuneLiteSyncService(self.path)
        self.context.enter_context(patch("osrs_goal_generator.gui.main_window.StateStore", return_value=self.store))
        self.context.enter_context(patch("osrs_goal_generator.gui.main_window.RuneLiteSyncService", return_value=reader))
        self.context.enter_context(patch.object(MainWindow,"_request_assets"))
        self.window = MainWindow()
        self.window.runelite_timer.stop()
        self.window.session.profile = make_profile()
        self.window._poll_runelite_sync()
        self.window._switch_page(4)
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def write(self):
        self.path.write_text(json.dumps(self.raw),encoding="utf-8")

    def test_diary_checklist_persists_and_never_changes_manual_completion(self):
        from test_diary_sync import sample
        from osrs_goal_generator.services import diary_sync
        raw=sample();w=self.window
        with patch.object(diary_sync,'load',return_value=(raw,True)):
            w._poll_diary_checklist();w._render_diary_checklist()
            self.assertIn('LIVE',w.diary_live_note.text())
            self.assertEqual(w.diary_task_table.rowCount(),8)
            self.assertEqual(sum(w.diary_task_table.item(i,0).text()=='Complete' for i in range(8)),2)
        w.state=self.store.load()
        with patch.object(diary_sync,'load',return_value=(None,False)):
            w._poll_diary_checklist();w._render_diary_checklist()
            self.assertIn('CACHED',w.diary_live_note.text())
            self.assertEqual(w.diary_task_table.rowCount(),8)
            self.assertEqual(self.store.completed_diaries(w.state,w.session.profile),set())
            w.session.profile.rsn='Another account'
            w._poll_diary_checklist();w._render_diary_checklist()
            self.assertEqual(w.diary_task_table.rowCount(),0)

    def test_diary_loading_does_not_block_ui_and_failure_can_retry(self):
        import threading
        import time
        from PySide6.QtCore import QTimer
        started, release = threading.Event(), threading.Event()
        w = self.window
        def delayed(**kwargs):
            started.set()
            release.wait(3)
            raise OSError('simulated offline')
        with patch.object(w.diary_service, 'load', side_effect=delayed) as load:
            try:
                w._load_diary_definitions()
                self.assertTrue(started.wait(2))
                w._load_diary_definitions()
                tick = []
                QTimer.singleShot(0, lambda: tick.append(True))
                self.app.processEvents()
                self.assertTrue(tick)
                self.assertEqual(load.call_count, 1)
            finally:
                release.set()
                deadline = time.monotonic() + 3
                while w.diary_loading and time.monotonic() < deadline:
                    self.app.processEvents()
                    time.sleep(.005)
        self.assertFalse(w.diary_loading)
        self.assertIn('simulated offline', w.diary_error)
        with patch.object(w.diary_service, 'load', return_value=[]):
            w._load_diary_definitions(force_refresh=True)
            deadline = time.monotonic() + 3
            while w.diary_loading and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.005)
        self.assertFalse(w.diary_loading)
        self.assertIsNone(w.diary_error)

    def test_cached_account_label_distinguishes_live_memory_from_saved_snapshot(self):
        w = self.window
        self.raw['connected'] = False
        self.write()
        w._poll_runelite_sync()
        w._render_home()
        self.assertIn('Cached skills', w.account_summary.text())
        w.last_live_update = None
        w._render_home()
        self.assertIn('Cached HiScores snapshot', w.account_summary.text())
        self.assertIn('Saved goal progress may be newer', w.account_summary.text())

    def test_failed_completion_save_can_retry_without_duplicate_history(self):
        w = self.window
        profile = w.session.profile
        goal = w.progress_service.collection_goal(profile, w.runelite_snapshot, 'Alpha')
        goal.status = 'accepted'
        self.store.set_active_goal(w.state, profile, goal)
        self.store.save(w.state)
        for item in self.raw['collection_log']['pages']['Alpha']['items']:
            item['obtained'] = True
        self.write()
        with patch.object(self.store, 'save', side_effect=PermissionError('locked')), patch('osrs_goal_generator.gui.main_window.QMessageBox.information') as notice:
            w._poll_runelite_sync()
            self.assertTrue(w.save_pending)
            self.assertFalse(w.save_notice.isHidden())
            notice.assert_not_called()
            self.assertIsNotNone(self.store.active_goal(self.store.load(), profile))
        self.assertTrue(w._save_state())
        restored = self.store.load()
        self.assertIsNone(self.store.active_goal(restored, profile))
        history = self.store.goal_history(restored, profile)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].status, 'completed')
        self.assertTrue(w.save_notice.isHidden())
        w._poll_runelite_sync()
        self.assertEqual(len(self.store.goal_history(w.state, profile)), 1)

    def test_failed_acceptance_and_preferences_survive_retry(self):
        w = self.window
        profile = w.session.profile
        w.session.current_goal = w.progress_service.collection_goal(profile, w.runelite_snapshot, 'Alpha')
        with patch.object(self.store, 'save', side_effect=OSError('disk full')), patch('osrs_goal_generator.gui.main_window.QMessageBox.information') as notice:
            w._accept_goal()
            w._toggle_boss_favorite('Brutus')
            self.assertTrue(w.save_pending)
            notice.assert_not_called()
        self.assertTrue(w._save_state())
        restored = self.store.load()
        self.assertIsNotNone(self.store.active_goal(restored, profile))
        self.assertIn('Brutus', self.store.favorite_bosses(restored, profile))

    def test_failed_partial_progress_save_blocks_close_and_retries(self):
        from osrs_goal_generator.models import Goal
        from PySide6.QtGui import QCloseEvent
        w = self.window
        profile = w.session.profile
        goal = Goal('partial', 'now', 'skilling', 'skill_xp', 'Agility', 'Train', 'XP', [],
                    start_value=800000, target_value=1000000, status='accepted')
        self.store.set_active_goal(w.state, profile, goal)
        self.store.save(w.state)
        with patch.object(self.store, 'save', side_effect=OSError('disk full')):
            w._poll_runelite_sync()
            event = QCloseEvent()
            w.closeEvent(event)
            self.assertFalse(event.isAccepted())
            self.assertFalse(w.closing)
        self.assertTrue(w._save_state())
        restored = self.store.active_goal(self.store.load(), profile)
        self.assertEqual(restored.current_value, 900000)
        self.assertEqual(restored.progress_percent, 50)

    def test_refresh_rejects_non_logged_in_snapshot(self):
        self.raw['game_state'] = 'LOGIN_SCREEN'
        self.write()
        profile = make_profile()
        profile.skills['Agility'].xp = 123
        self.window._profile_loaded(profile)
        self.assertEqual(self.window.session.profile.skills['Agility'].xp, 123)

    def test_delayed_lookup_is_single_and_close_waits_safely(self):
        import threading
        import time
        from PySide6.QtGui import QCloseEvent
        started, release = threading.Event(), threading.Event()
        calls = []
        def delayed(_client, rsn, account_type):
            calls.append(rsn)
            started.set()
            release.wait(3)
            return make_profile()
        w = self.window
        original = w.session.profile
        w.rsn_input.setText('Test Player')
        with patch('osrs_goal_generator.gui.main_window.HiscoresClient.fetch', delayed):
            try:
                w._load_account()
                self.assertTrue(started.wait(2))
                w._load_account()
                self.assertEqual(calls, ['Test Player'])
                self.assertFalse(w.rsn_input.isEnabled())
                event = QCloseEvent()
                w.closeEvent(event)
                self.assertFalse(event.isAccepted())
                self.assertTrue(w.closing)
            finally:
                release.set()
                deadline = time.monotonic() + 3
                while w.lookup_pending and time.monotonic() < deadline:
                    self.app.processEvents()
                    time.sleep(.005)
            self.assertFalse(w.lookup_pending)
            self.assertIs(w.session.profile, original)
            event = QCloseEvent()
            w.closeEvent(event)
            self.assertTrue(event.isAccepted())

    def test_home_compact_layout_has_no_horizontal_scroll(self):
        from PySide6.QtWidgets import QBoxLayout
        self.window._switch_page(0)
        self.window.show()
        self.window.resize(1100, 760)
        self.app.processEvents()
        self.assertEqual(self.window.home_main_layout.direction(), QBoxLayout.Direction.TopToBottom)
        self.assertEqual(self.window.home_page.horizontalScrollBar().maximum(), 0)
        self.window.resize(1440, 900)
        self.app.processEvents()
        self.assertEqual(self.window.home_main_layout.direction(), QBoxLayout.Direction.LeftToRight)

    def test_active_goal_hides_generation_controls_and_restores_them_after_archive(self):
        profile = self.window.session.profile
        goal = self.window.progress_service.collection_goal(profile, self.window.runelite_snapshot, 'Alpha')
        goal.status = 'accepted'
        self.store.set_active_goal(self.window.state, profile, goal)
        self.window._render_goal_panel()
        self.assertTrue(self.window.generate_button.isHidden())
        self.assertTrue(self.window.home_filter_panel.isHidden())
        self.assertFalse(self.window.home_goal_panel.isHidden())
        self.store.archive_active_goal(self.window.state, profile, 'cancelled')
        self.window._render_goal_panel()
        self.assertFalse(self.window.generate_button.isHidden())
        self.assertFalse(self.window.home_filter_panel.isHidden())

    def test_status_banner_and_open_settings_follow_disconnect_and_reconnect(self):
        self.window._switch_page(7)
        self.assertEqual(self.window.runelite_bridge_status.text(), "RUNELITE LIVE")
        self.raw["connected"] = False
        self.write()
        self.window._poll_runelite_sync()
        self.assertEqual(self.window.top_status_label.text(), "RUNELITE DISCONNECTED")
        self.assertEqual(self.window.runelite_bridge_status.text(), "RUNELITE DISCONNECTED")
        self.assertIn("HiScores", self.window.bridge_status_note.text())
        self.raw["connected"] = True
        self.write()
        self.window._poll_runelite_sync()
        self.assertEqual(self.window.runelite_bridge_status.text(), "RUNELITE LIVE")

    def test_status_banner_rejects_wrong_account(self):
        self.raw["player"]["name"] = "Another account"
        self.write()
        self.window._poll_runelite_sync()
        self.assertEqual(self.window.top_status_label.text(), "ACCOUNT MISMATCH")
        self.assertIn("Another account", self.window.bridge_status_note.text())

    def cards(self):
        layout = self.window.collection_cards_layout
        return [layout.itemAt(i).widget() for i in range(layout.count())
                if layout.itemAt(i).widget() and layout.itemAt(i).widget().property("syncedPageName")]

    def names(self):
        return [card.property("syncedPageName") for card in self.cards()]

    def test_search_and_completion_filters(self):
        self.assertEqual(self.names(),["Alpha","Zeta"])
        self.window.collection_status.setCurrentText("All")
        self.assertEqual(len(self.cards()),3)
        self.window.collection_status.setCurrentText("Completed")
        self.assertEqual(self.names(),["Completed page"])
        self.window.collection_status.setCurrentText("All")
        self.window.collection_search.setText("  zEtA  ")
        self.assertEqual(self.names(),["Zeta"])
        self.window.collection_search.setText("no match")
        self.assertEqual(self.names(),[])
        from PySide6.QtWidgets import QLabel
        labels=self.window.collection_page.findChildren(QLabel)
        self.assertTrue(any("No synced pages match" in label.text() for label in labels))

    def test_active_first_respects_search_and_opens_home(self):
        from PySide6.QtWidgets import QPushButton
        profile=self.window.session.profile
        goal=self.window.progress_service.collection_goal(profile,self.window.runelite_snapshot,"Zeta")
        goal.status="accepted"
        self.store.set_active_goal(self.window.state,profile,goal)
        self.window._render_collection()
        self.assertEqual(self.names(),["Zeta","Alpha"])
        button=self.cards()[0].findChildren(QPushButton)[0]
        self.assertEqual(button.text(),"View active goal")
        self.assertTrue(button.isEnabled())
        button.click()
        self.assertEqual(self.window.pages.currentIndex(),0)
        self.window.collection_search.setText("Alpha")
        self.assertEqual(self.names(),["Alpha"])
        self.assertFalse(self.cards()[0].findChildren(QPushButton)[0].isEnabled())

    def test_cached_pages_remain_searchable_but_tracking_is_disabled(self):
        from PySide6.QtWidgets import QPushButton
        self.raw["connected"]=False
        self.write(); self.window._poll_runelite_sync()
        self.window.collection_search.setText("Zeta")
        self.assertEqual(self.names(),["Zeta"])
        self.assertFalse(self.cards()[0].findChildren(QPushButton)[0].isEnabled())

    def test_tracking_button_chooses_the_correct_filtered_page(self):
        from PySide6.QtWidgets import QPushButton
        self.window.collection_search.setText("Zeta")
        self.cards()[0].findChildren(QPushButton)[0].click()
        self.assertEqual(self.window.session.current_goal.target_name,"Zeta")
        self.assertIsNone(self.store.active_goal(self.window.state,self.window.session.profile))

    def test_completed_page_has_no_tracking_action(self):
        from PySide6.QtWidgets import QPushButton
        self.window.collection_status.setCurrentText("Completed")
        button=self.cards()[0].findChildren(QPushButton)[0]
        self.assertFalse(button.isEnabled())
        self.assertIn("All captured items",button.toolTip())

    def test_categories_filter_synced_and_manual_data_together(self):
        from PySide6.QtWidgets import QLabel
        original=self.raw["collection_log"]["pages"]["Alpha"]
        names=("Vorkath", "Chambers of Xeric", "Pest Control", "Slayer", "All Pets",
               "Hard Treasure Trails", "New unknown page")
        self.raw["collection_log"]["pages"]={name:json.loads(json.dumps(original)) for name in names}
        profile=self.window.session.profile
        self.store.save_collection_target(self.window.state,profile,
            {"target_id":"manual","name":"Manual raid tracker","category":"Raids","current":0,"total":2})
        self.write(); self.window._poll_runelite_sync()
        expected={"Bosses":"Vorkath","Raids":"Chambers of Xeric","Minigames":"Pest Control",
                  "Slayer":"Slayer","Other":"All Pets","Clues":"Hard Treasure Trails",
                  "Uncategorized":"New unknown page"}
        for category,name in expected.items():
            with self.subTest(category=category):
                self.window.collection_category.setCurrentText(category)
                self.assertEqual(self.names(),[name])
                layout=self.window.collection_cards_layout
                cards=[layout.itemAt(i).widget() for i in range(layout.count()) if layout.itemAt(i).widget()]
                labels=[label.text() for card in cards for label in card.findChildren(QLabel)]
                self.assertEqual("Manual raid tracker" in labels,category=="Raids")
        self.window.collection_category.setCurrentText("All Categories")
        self.assertEqual(len(self.names()),len(names))
        self.window.collection_category.setCurrentText("Bosses")
        self.window.collection_search.setText("Chambers")
        self.assertEqual(self.names(),[])
        self.window.collection_search.clear()
        self.window.collection_status.setCurrentText("Completed")
        self.assertEqual(self.names(),[])
        self.window.collection_status.setCurrentText("Incomplete")
        self.raw["connected"]=False; self.write(); self.window._poll_runelite_sync()
        self.assertEqual(self.names(),["Vorkath"])

    def test_category_mapping_is_exact_normalized_and_raid_specific(self):
        from osrs_goal_generator.services.collection_categories import collection_page_category
        self.assertEqual(collection_page_category("  VORKATH  "),"Bosses")
        self.assertEqual(collection_page_category("Rogues’ Den"),"Minigames")
        self.assertEqual(collection_page_category("Tombs of Amascut"),"Raids")
        self.assertEqual(collection_page_category("Vorkath invented extension"),"Uncategorized")
