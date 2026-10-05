import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from test_alpha2 import make_profile
from osrs_goal_generator.services.runelite_sync import RuneLiteSyncService
from osrs_goal_generator.services.progress import GoalProgressService
from osrs_goal_generator.models import Goal

class LiveBossCountsTests(unittest.TestCase):
    def test_merge_validation_fingerprint_and_account_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sync.json'
            raw={'schema_version':1,'updated_at':datetime.now(timezone.utc).isoformat(),
                 'connected':True,'game_state':'LOGGED_IN','player':{'name':'Test Player'},
                 'boss_counts':{'Vorkath':350,'Zulrah':True,'Unknown':999,'Brutus':-1}}
            path.write_text(json.dumps(raw));service=RuneLiteSyncService(path);snapshot=service.load()
            self.assertEqual(snapshot.boss_counts,{'Vorkath':350})
            profile=make_profile(vorkath=347)
            self.assertEqual(service.merge_profile(profile,snapshot).activity('Vorkath').score,350)
            self.assertEqual(profile.activity('Vorkath').score,347)
            self.assertEqual(service.merge_profile(make_profile(vorkath=400),snapshot).activity('Vorkath').score,400)
            before=service.fingerprint(snapshot)
            raw['boss_counts']['Vorkath']=351;path.write_text(json.dumps(raw))
            self.assertNotEqual(before,service.fingerprint(service.load()))
            profile.rsn='Other'
            self.assertEqual(service.merge_profile(profile,snapshot).activity('Vorkath').score,347)

    def test_boss_goal_completes_live_and_checkpoint_does_not_regress(self):
        from osrs_goal_generator.services.runelite_sync import RuneLiteSyncSnapshot
        snapshot=RuneLiteSyncSnapshot(1,'test',datetime.now(timezone.utc).isoformat(),True,'LOGGED_IN','Test Player','unknown',None,None,None,boss_counts={'Vorkath':350})
        goal=Goal('boss-test','2026-10-05','bossing','boss_kc','Vorkath','Kill Vorkath','',[],start_value=347,target_value=350,status='accepted')
        service=GoalProgressService()
        result=service.apply(goal,make_profile(),snapshot)
        self.assertTrue(result.completed)
        self.assertEqual(result.source,'RuneLite live')
        self.assertEqual(service.evaluate(goal,make_profile(vorkath=347),None).current_value,350)
