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
