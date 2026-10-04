import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from osrs_goal_generator.config import ASSETS_DIR
from osrs_goal_generator.services import diary_sync

def sample():
    mapping=json.loads((ASSETS_DIR/'ardougne-task-mapping.json').read_text())
    tiers={}
    for tier in ('easy','medium','hard','elite'):
        tasks=[{'id':f"ardougne:{tier}:{r['varp']}:{r['bit']}", 'bit_set':tier!='elite' or r['bit'] in (9,10)} for r in mapping if r['tier']==tier]
        tiers[tier]={'tasks':tasks,'count_raw':sum(t['bit_set'] for t in tasks),'mapping_status':'count_matched_pending_journal_check'}
    return {'prototype_schema':1,'mapping_version':'ardougne-tasks-1','status':'observed_unverified','player_name':'Test Player','updated_at':datetime.now(timezone.utc).isoformat(),'tiers':tiers}

class DiarySyncTests(unittest.TestCase):
    def test_exact_tasks_and_account_guard(self):
        raw=sample()
        data=diary_sync.validate(raw,'Test Player')
        self.assertEqual(data['tiers']['elite']['count'],2)
        self.assertEqual(sum(t['completed'] for t in data['tiers']['elite']['tasks']),2)
        self.assertIsNone(diary_sync.validate(raw,'Other'))

    def test_count_mismatch_is_unknown(self):
        raw=sample();raw['tiers']['elite']['count_raw']=3
        tier=diary_sync.validate(raw,'Test Player')['tiers']['elite']
        self.assertFalse(tier['consistent'])
        self.assertTrue(all(t['completed'] is None for t in tier['tasks']))

    def test_duplicate_or_non_boolean_tasks_rejected(self):
        raw=sample();raw['tiers']['elite']['tasks'][0]=raw['tiers']['elite']['tasks'][1]
        self.assertIsNone(diary_sync.validate(raw,'Test Player'))
        raw=sample();raw['tiers']['elite']['tasks'][0]['bit_set']='false'
        self.assertIsNone(diary_sync.validate(raw,'Test Player'))

    def test_stale_and_corrupt_files_are_not_live(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'diary.json';raw=sample();raw['updated_at']='2000-01-01T00:00:00Z'
            path.write_text(json.dumps(raw))
            data,live=diary_sync.load('Test Player',path)
            self.assertIsNotNone(data);self.assertFalse(live)
            path.write_text('broken')
            self.assertEqual(diary_sync.load('Test Player',path),(None,False))
