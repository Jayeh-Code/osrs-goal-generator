import json
from pathlib import Path
import tempfile
import unittest
import os
import runpy
import sys
from unittest.mock import patch

from osrs_goal_generator.services.save_migration import import_save
from osrs_goal_generator.services.storage import StateStore


class PackagingTests(unittest.TestCase):
    def test_malformed_nested_save_is_rejected_without_replacing_original(self):
        from osrs_goal_generator.services.save_migration import read_save
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'state.json'
            for entry in ({'preferences': []}, {'collection_targets': [{'current': 'broken'}]},
                          {'active_goal': {'metadata': []}}, {'snapshots': [{'skills': []}]}):
                path.write_text(json.dumps({'profiles': {'normal:test': entry}}))
                before = path.read_bytes()
                with self.assertRaises(ValueError):
                    read_save(path)
                self.assertEqual(path.read_bytes(), before)

    def test_import_preserves_every_field_and_original_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = root / "old.json"
            new = root / "stable" / "state.json"
            raw = {"profiles": {"normal:test": {"active_goal": {"id": "abc"}, "goal_history": [{"id": "old"}], "preferences": {"favorite_bosses": ["Brutus"]}}}, "future_field": [1, 2]}
            old.write_text(json.dumps(raw), encoding="utf-8")
            before = old.read_bytes()
            self.assertTrue(import_save(old, new))
            self.assertEqual(new.read_bytes(), before)
            self.assertEqual(old.read_bytes(), before)
            self.assertEqual((new.parent / "imported-original.json").read_bytes(), before)

    def test_import_never_replaces_existing_save(self):
        with tempfile.TemporaryDirectory() as folder:
            old, new = Path(folder)/"old.json", Path(folder)/"state.json"
            old.write_text('{"profiles":{}}')
            new.write_text('{"profiles":{}, "marker":1}')
            before = new.read_bytes()
            self.assertFalse(import_save(old, new))
            self.assertEqual(new.read_bytes(), before)

    def test_invalid_import_does_not_create_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            old, new = Path(folder)/"old.json", Path(folder)/"state.json"
            for data in ['broken', '[]', '{"profiles":[]}']:
                old.write_text(data)
                with self.assertRaises(ValueError):
                    import_save(old, new)
                self.assertFalse(new.exists())

    def test_saving_keeps_previous_good_version(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"state.json"
            store = StateStore(path)
            store.save({"profiles":{}, "marker":1})
            before = path.read_bytes()
            store.save({"profiles":{}, "marker":2})
            self.assertEqual(path.with_suffix('.backup.json').read_bytes(), before)
            self.assertEqual(store.load()['marker'], 2)

    def test_corrupt_save_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"state.json"
            path.write_text('broken')
            with self.assertRaises(ValueError):
                StateStore(path).save({"profiles":{}})
            self.assertEqual(path.read_text(), 'broken')

    def test_same_save_survives_different_app_folders(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(__file__).resolve().parents[1]/'src/osrs_goal_generator/config.py'
            with patch.dict(os.environ, {'LOCALAPPDATA':folder, 'OSRS_DATA_DIR':''}), patch.object(sys, 'frozen', True, create=True):
                with patch.object(sys, '_MEIPASS', str(Path(folder)/'version1'), create=True):
                    first = runpy.run_path(str(config))
                StateStore(first['STATE_FILE']).save({'profiles':{}, 'history':['completed']})
                with patch.object(sys, '_MEIPASS', str(Path(folder)/'version2'), create=True):
                    second = runpy.run_path(str(config))
                self.assertEqual(first['STATE_FILE'], second['STATE_FILE'])
                self.assertNotEqual(first['ASSETS_DIR'], second['ASSETS_DIR'])
                self.assertEqual(StateStore(second['STATE_FILE']).load()['history'], ['completed'])
