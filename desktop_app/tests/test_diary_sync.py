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
    def test_automatic_completion_ignores_rewards_and_rejects_mismatch(self):
        raw = sample()
        raw['tiers']['easy']['reward_raw'] = 0
        self.assertEqual(diary_sync.completed_ids(raw, 'Test Player'),
                         {'ardougne:easy', 'ardougne:medium', 'ardougne:hard'})
        raw['tiers']['easy']['count_raw'] = 0
        self.assertNotIn('ardougne:easy', diary_sync.completed_ids(raw, 'Test Player'))
        self.assertEqual(diary_sync.completed_ids(raw, 'Other'), set())

    def test_observed_completion_persists_separately_from_manual(self):
        from osrs_goal_generator.services.storage import StateStore
        from test_alpha2 import make_profile
        with tempfile.TemporaryDirectory() as folder:
            store = StateStore(Path(folder)/'state.json')
            state = store.load(); profile = make_profile()
            entry = store.ensure_profile_entry(state, profile.rsn, profile.account_type)
            entry['diary_prototype_snapshot'] = sample()
            store.mark_diary_complete(state, profile, 'karamja:elite')
            store.save(state); state = store.load()
            self.assertIn('ardougne:easy', store.completed_diaries(state, profile))
            self.assertIn('karamja:elite', store.completed_diaries(state, profile))
            self.assertEqual(store.ensure_profile_entry(state, profile.rsn, profile.account_type)['completed_diaries'], ['karamja:elite'])
            self.assertNotIn('ardougne:elite', store.completed_diaries(state, profile))

    def test_all_regions_and_legacy_compatibility(self):
        raw=sample()
        mapping=json.loads((ASSETS_DIR/'diary-task-mapping.json').read_text())
        raw['regions_mapping_version']='all-diaries-1';raw['regions']={}
        for region in diary_sync.REGIONS:
            raw['regions'][region]={}
            for tier in ('easy','medium','hard','elite'):
                tasks=[{'id':r['id'],'bit_set':False} for r in mapping if r['region']==region and r['tier']==tier]
                raw['regions'][region][tier]={'tasks':tasks,'count_raw':0,'mapping_status':'count_matched_pending_journal_check'}
        data=diary_sync.validate(raw,'Test Player')
        self.assertEqual(len(data['regions']),12)
        self.assertEqual(sum(t['total'] for r in data['regions'].values() for t in r.values()),492)
        raw['regions']['Karamja']['easy']['count_raw']=1
        data=diary_sync.validate(raw,'Test Player')
        self.assertFalse(data['regions']['Karamja']['easy']['consistent'])
        self.assertTrue(data['regions']['Varrock']['easy']['consistent'])
        self.assertEqual(set(diary_sync.validate(sample(),'Test Player')['regions']),{'Ardougne'})

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
