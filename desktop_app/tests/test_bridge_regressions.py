"""Synthetic bridge cases: no private account files or login required."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from osrs_goal_generator.services.runelite_sync import RuneLiteSyncService
from test_alpha8 import sample_sync
from test_alpha2 import make_profile


class BridgeRegressionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "sync.json"
        self.service = RuneLiteSyncService(self.path)

    def load(self, payload):
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        return self.service.load()

    def test_missing_partial_and_invalid_utf8_files_are_unavailable(self):
        self.assertIsNone(self.service.load())
        for data in (b'{"schema_version":', b'\xff', b'[]'):
            self.path.write_bytes(data)
            self.assertIsNone(self.service.load())

    def test_invalid_schema_types_are_rejected_without_crashing(self):
        for version in ("oops", [], {}, None, True, 1.5):
            with self.subTest(version=version):
                payload = sample_sync()
                payload["schema_version"] = version
                self.assertIsNone(self.load(payload))

    def test_malformed_page_items_do_not_crash_reader(self):
        for items in (None, 17, "items", {}):
            with self.subTest(items=items):
                payload = sample_sync()
                payload["collection_log"]["pages"]["Vorkath"]["items"] = items
                self.assertEqual(self.load(payload).collection_item_count, 0)

    def test_non_boolean_obtained_never_fabricates_completion(self):
        payload = sample_sync()
        payload["collection_log"]["pages"]["Vorkath"]["items"][0]["obtained"] = "false"
        self.assertEqual(self.load(payload).collection_obtained_count, 0)

    def test_stale_and_disconnected_keep_pages_but_are_not_live(self):
        payload = sample_sync()
        payload["updated_at"] = (datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
        self.assertFalse(self.load(payload).is_fresh())
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload["connected"] = False
        snapshot = self.load(payload)
        self.assertFalse(snapshot.is_fresh())
        self.assertEqual(snapshot.collection_page_count, 1)

    def test_bad_timestamp_is_not_live(self):
        payload = sample_sync()
        payload["updated_at"] = "invalid"
        self.assertFalse(self.load(payload).is_fresh())

    def test_other_account_does_not_match(self):
        self.assertFalse(self.load(sample_sync("Other Account")).matches(make_profile()))

    def test_live_xp_and_level_update_preserve_hiscores_and_original(self):
        profile = make_profile()
        before = profile.to_dict()
        payload = sample_sync()
        first = self.load(payload)
        payload["skills"]["Agility"] = {"level": 73, "xp": 1_000_000}
        second = self.load(payload)
        merged = self.service.merge_profile(profile, second)
        self.assertNotEqual(self.service.fingerprint(first), self.service.fingerprint(second))
        self.assertEqual(merged.skill("Agility").xp, 1_000_000)
        self.assertEqual(merged.skill("Agility").level, 73)
        self.assertEqual(merged.skill("Agility").rank, profile.skill("Agility").rank)
        self.assertEqual(merged.activity("Vorkath").score, profile.activity("Vorkath").score)
        self.assertEqual(profile.to_dict(), before)

    def test_heartbeat_does_not_change_content_fingerprint(self):
        payload = sample_sync()
        first = self.load(payload)
        payload["updated_at"] = (datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
        self.assertEqual(self.service.fingerprint(first), self.service.fingerprint(self.load(payload)))

    def test_large_page_set_survives_reader_restart(self):
        payload = sample_sync()
        # Synthetic pages test volume, not real account completion.
        page = payload["collection_log"]["pages"]["Vorkath"]
        payload["collection_log"]["pages"] = {f"Test page {i}":page for i in range(124)}
        first = self.load(payload)
        second = RuneLiteSyncService(self.path).load()
        self.assertEqual(first.collection_pages, second.collection_pages)
        self.assertEqual(second.collection_page_count, 124)
        self.assertEqual(second.collection_item_count, 248)
        self.assertEqual(second.collection_obtained_count, 124)

    def test_atomic_replacement_is_seen_without_reader_restart(self):
        payload = sample_sync()
        first = self.load(payload)
        payload["collection_log"]["pages"]["Vorkath"]["items"][1]["obtained"] = True
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload), encoding="utf-8")
        temp.replace(self.path)
        second = self.service.load()
        self.assertNotEqual(self.service.fingerprint(first), self.service.fingerprint(second))
        self.assertEqual(second.collection_obtained_count, 2)
