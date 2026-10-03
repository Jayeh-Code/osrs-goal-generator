from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from osrs_goal_generator.config import RUNELITE_SYNC_FILE, VERSION
from osrs_goal_generator.services.runelite_sync import RuneLiteSyncService
from test_alpha2 import make_profile


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = ROOT.parent
MAIN_WINDOW = ROOT / "src" / "osrs_goal_generator" / "gui" / "main_window.py"
# In the Codex starter workspace the RuneLite companion has one canonical home
# at the workspace root, rather than a duplicate nested inside desktop_app.
PLUGIN = WORKSPACE_ROOT / "runelite_companion" / "src" / "main" / "java" / "com" / "osrsgoalgenerator" / "OsrsGoalGeneratorPlugin.java"
BUILD = WORKSPACE_ROOT / "runelite_companion" / "build.gradle"
PROPERTIES = WORKSPACE_ROOT / "runelite_companion" / "runelite-plugin.properties"


def sample_sync(player_name: str = "Test Player") -> dict:
    return {
        "schema_version": 1,
        "plugin_version": "0.1.0-alpha8",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "connected": True,
        "game_state": "LOGGED_IN",
        "player": {
            "name": player_name,
            "account_type": "unknown",
            "combat_level": 112,
            "total_level": 1802,
            "total_xp": 100_123_456,
        },
        "skills": {
            "Agility": {"level": 72, "xp": 900_000},
            "Attack": {"level": 81, "xp": 2_300_000},
        },
        "session": {
            "started_at": "2026-09-27T20:00:00Z",
            "last_event": "stat:Agility",
            "xp_gained": {"Agility": 12345},
        },
        "collection_log": {
            "pages": {
                "Vorkath": {
                    "updated_at": "2026-09-27T22:00:00Z",
                    "items": [
                        {"item_id": 22000, "name": "Vorki", "obtained": True},
                        {"item_id": 22001, "name": "Jar of decay", "obtained": False},
                    ],
                }
            },
            "recent_unlocks": ["Vorki"],
        },
    }


class Alpha8Tests(unittest.TestCase):
    def test_version_is_alpha8(self):
        self.assertTrue(VERSION.startswith(("4.0.0-alpha.8", "4.0.0-alpha.9")))

    def test_bridge_path_matches_runelite_plugin_data_directory(self):
        normalized = str(RUNELITE_SYNC_FILE).replace("\\", "/")
        self.assertTrue(normalized.endswith(".runelite/plugin-data/osrs-goal-generator-companion/sync.json"))

    def test_sync_snapshot_parses_skills_and_collection_log(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sync.json"
            path.write_text(json.dumps(sample_sync()), encoding="utf-8")
            snapshot = RuneLiteSyncService(path).load()
            self.assertIsNotNone(snapshot)
            assert snapshot is not None
            self.assertEqual(snapshot.player_name, "Test Player")
            self.assertEqual(snapshot.skills["Agility"]["level"], 72)
            self.assertEqual(snapshot.collection_page_count, 1)
            self.assertEqual(snapshot.collection_item_count, 2)
            self.assertEqual(snapshot.collection_obtained_count, 1)
            self.assertEqual(snapshot.collection_pages["Vorkath"].missing_items[0].name, "Jar of decay")

    def test_bad_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sync.json"
            payload = sample_sync()
            payload["schema_version"] = 999
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIsNone(RuneLiteSyncService(path).load())

    def test_snapshot_matches_loaded_account_case_insensitively(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sync.json"
            path.write_text(json.dumps(sample_sync("test player")), encoding="utf-8")
            snapshot = RuneLiteSyncService(path).load()
            assert snapshot is not None
            self.assertTrue(snapshot.matches(make_profile()))
            self.assertTrue(snapshot.is_fresh())

    def test_merge_profile_overlays_skills_but_preserves_hiscore_activities(self):
        profile = make_profile(vorkath=347)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sync.json"
            path.write_text(json.dumps(sample_sync()), encoding="utf-8")
            snapshot = RuneLiteSyncService(path).load()
            assert snapshot is not None
            merged = RuneLiteSyncService.merge_profile(profile, snapshot)
            self.assertEqual(merged.skill("Agility").level, 72)
            self.assertEqual(merged.skill("Agility").xp, 900_000)
            self.assertEqual(merged.overall.level, 1802)
            self.assertEqual(merged.activity("Vorkath").score, 347)
            self.assertEqual(profile.skill("Agility").level, 70)  # original not mutated

    def test_desktop_has_live_bridge_polling_and_settings_status(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn("QTimer(self)", source)
        self.assertIn("self.runelite_sync_service = RuneLiteSyncService()", source)
        self.assertIn("def _poll_runelite_sync", source)
        self.assertIn("RUNELITE LIVE", source)
        self.assertIn('QLabel("RuneLite Companion")', source)
        self.assertIn("Refresh RuneLite Bridge", source)

    def test_collection_page_supports_live_and_cached_runelite_pages(self):
        source = MAIN_WINDOW.read_text(encoding="utf-8")
        self.assertIn("RUNELITE LIVE", source)
        self.assertIn("RUNELITE CACHED", source)
        self.assertIn("bridge_snapshot.collection_pages", source)
        self.assertIn("cached pages remain visible when RuneLite is closed", source)

    @unittest.skipUnless(PLUGIN.exists(), "Companion source is tested in its separate repository")
    def test_plugin_uses_current_runelite_file_sandbox(self):
        source = PLUGIN.read_text(encoding="utf-8")
        self.assertIn('internalName = "osrs-goal-generator-companion"', source)
        self.assertIn("getPluginDirectory()", source)
        self.assertIn("Filepath", source)
        self.assertNotIn("java.io.File", source)
        self.assertNotIn("RuneLite.RUNELITE_DIR", source)

    @unittest.skipUnless(PLUGIN.exists(), "Companion source is tested in its separate repository")
    def test_plugin_collection_log_capture_matches_runelite_interface_contract(self):
        source = PLUGIN.read_text(encoding="utf-8")
        self.assertIn("import net.runelite.api.ScriptID;", source)
        self.assertNotIn("import net.runelite.api.gameval.ScriptID;", source)
        self.assertIn("ScriptID.COLLECTION_DRAW_LIST", source)
        self.assertIn("InterfaceID.Collection.HEADER_TEXT", source)
        self.assertIn("InterfaceID.Collection.ITEMS_CONTENTS", source)
        self.assertIn("child.getOpacity() == 0", source)
        self.assertIn("child.getItemId()", source)

    @unittest.skipUnless(PLUGIN.exists(), "Companion source is tested in its separate repository")
    def test_plugin_is_local_only_and_uses_off_client_thread_file_write(self):
        source = PLUGIN.read_text(encoding="utf-8")
        self.assertNotIn("OkHttp", source)
        self.assertNotIn("HttpURLConnection", source)
        self.assertNotIn("java.net", source)
        self.assertIn("executor.execute", source)
        self.assertIn("writeAtomic", source)
        self.assertIn("StandardCopyOption.ATOMIC_MOVE", source)

    @unittest.skipUnless(PLUGIN.exists(), "Companion source is tested in its separate repository")
    def test_plugin_build_targets_java_11_and_latest_runelite(self):
        build = BUILD.read_text(encoding="utf-8")
        self.assertIn("runeLiteVersion = 'latest.release'", build)
        self.assertIn("options.release.set(11)", build)
        props = PROPERTIES.read_text(encoding="utf-8")
        self.assertIn("plugins=com.osrsgoalgenerator.OsrsGoalGeneratorPlugin", props)


if __name__ == "__main__":
    unittest.main()
