"""Gear history, retagging, pause/resume and export boundaries; synthetic Garmin data only."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from gear_sync import sync_gear,clean_catalog,coverage,ACTIVITY_GEAR,LINKS
from run_cache import RunCache
from sync_job import SyncJob,SyncPaused
from garmin_backend import Session
from route_review_contract import validate_review
from comparison_contract import validate_snapshot

SHOES='1'*32
BANDANA='2'*32


def activity(identity,day='2026-10-24'):
    return dict(activityId=identity,activityName='Easy run',activityType='running',
                startTimeLocal=day+' 08:00:00',distance=6000,duration=2700,averageHR=128)


def catalog():
    return [dict(uuid=SHOES,displayName='Shoes',gearTypeName='Shoes',secret='excluded'),
            dict(uuid=BANDANA,displayName='Ice bandana',gearStatusName='Active',userProfilePk=99)]


class GearFixture:
    def setUp(self):
        self.cache=RunCache();self.addCleanup(self.cache.close)
        self.rows=[activity(1,'2026-06-01'),activity(2),activity(3)]
        self.cache.save_window('2025-06-01','2026-10-24',self.rows)
        self.client=Mock();self.client.profile_id=99;self.client.get_gear.return_value=catalog()
        self.links={SHOES:[1,2],BANDANA:[2]}
        def response(url,params=None):
            identity=url.split('/')[-2]
            return [dict(activityId=i,privateLocation='excluded') for i in self.links[identity]][params['start']:params['start']+params['limit']]
        self.client.connectapi.side_effect=response
        self.job=SyncJob();self.job.wait=Mock()
    def sync(self,refresh=False,now=1000):
        sync_gear(self.client,self.cache,self.rows,refresh,self.job,now)
    def gear(self,identity):return self.cache.detail(str(identity),ACTIVITY_GEAR)[1]


class GearSyncTest(GearFixture,unittest.TestCase):
    def test_custom_gear_label_falls_back_to_garmin_custom_make_model(self):
        item=clean_catalog([dict(uuid=BANDANA,displayName=None,customMakeModel='Ice bandana',gearTypeName='Other')])[0]
        self.assertEqual(item['name'],'Ice bandana')
        preferred=clean_catalog([dict(uuid=BANDANA,displayName='My bandana',customMakeModel='Ice bandana')])[0]
        self.assertEqual(preferred['name'],'My bandana')
    def test_bulk_backfill_matches_multiple_items_and_confirms_empty_without_recordings(self):
        self.sync()
        self.assertEqual([g['name'] for g in self.gear(2)['items']],['Shoes','Ice bandana'])
        self.assertEqual(self.gear(3)['items'],[]);self.assertTrue(self.gear(3)['complete'])
        self.assertEqual(self.client.connectapi.call_count,2)
        self.client.download_activity.assert_not_called();self.client.get_activity_gear.assert_not_called()
        self.assertNotIn('privateLocation',json.dumps(self.cache.all_details(LINKS)))
        self.assertNotIn('secret',json.dumps(self.cache.meta('gear_catalog_v1')))
    def test_pagination_checks_past_first_page_and_saves_only_known_ids(self):
        self.links[BANDANA]=list(range(1,151))
        self.sync()
        calls=[c for c in self.client.connectapi.call_args_list if BANDANA in c.args[0]]
        self.assertEqual([c.kwargs['params']['start'] for c in calls],[0,100])
        self.assertEqual(self.cache.detail(BANDANA,LINKS)[1]['activity_ids'],['1','2','3'])
    def test_cached_reopen_and_persistent_restart_need_no_network(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'gear.sqlite'
            cache=RunCache(path)
            try:sync_gear(self.client,cache,self.rows,False,self.job,1000)
            finally:cache.close()
            cache=RunCache(path)
            try:
                self.client.reset_mock()
                sync_gear(self.client,cache,self.rows,False,self.job,1100)
                self.assertEqual(self.client.mock_calls,[])
                self.assertEqual(len(cache.detail('2',ACTIVITY_GEAR)[1]['items']),2)
            finally:cache.close()
    def test_manual_sync_catches_historical_gear_edits_without_invalidating_terrain(self):
        self.sync();self.cache.save_detail('1','terrain_v1',dict(status='ok',elevation_gain=12))
        self.links[BANDANA]=[1]
        self.client.get_gear.return_value=[dict(uuid=SHOES,displayName='Shoes'),dict(uuid=BANDANA,displayName='Cooling bandana')]
        self.sync(refresh=True,now=1100)
        self.assertEqual([g['name'] for g in self.gear(1)['items']],['Shoes','Cooling bandana'])
        self.assertEqual([g['name'] for g in self.gear(2)['items']],['Shoes'])
        self.assertEqual(self.cache.detail('1','terrain_v1')[1]['elevation_gain'],12)
    def test_new_activity_refreshes_links_even_inside_cache_ttl(self):
        self.sync();self.rows.append(activity(4));self.links[BANDANA].append(4)
        self.client.reset_mock();self.sync(now=1100)
        self.assertEqual(self.gear(4)['items'][0]['name'],'Ice bandana')
        self.assertEqual(self.client.connectapi.call_count,2)
        self.client.get_gear.assert_not_called()
    def test_catalog_and_links_refresh_after_six_hours(self):
        self.sync();self.links[BANDANA]=[1];self.client.reset_mock();self.sync(now=1000+21601)
        self.client.get_gear.assert_called_once();self.assertEqual(self.gear(1)['items'][-1]['name'],'Ice bandana')
    def test_zero_gear_is_confirmed_without_activity_requests(self):
        self.client.get_gear.return_value=[];self.sync()
        self.client.connectapi.assert_not_called()
        self.assertTrue(all(self.gear(i)['complete'] and self.gear(i)['items']==[] for i in (1,2,3)))
    def test_partial_failure_is_unknown_and_resume_reuses_completed_gear(self):
        response=self.client.connectapi.side_effect
        def interrupted(url,params):
            if BANDANA in url:raise ValueError('synthetic private failure')
            return response(url,params)
        self.client.connectapi.side_effect=interrupted
        with self.assertRaises(ValueError):self.sync(refresh=True)
        self.assertFalse(self.gear(3)['complete']);self.assertFalse(self.gear(2)['complete'])
        self.assertEqual(self.gear(1)['items'][0]['name'],'Shoes')
        self.client.connectapi.side_effect=response;self.client.reset_mock();self.sync(refresh=True,now=1100)
        self.client.get_gear.assert_not_called()
        self.assertEqual(self.client.connectapi.call_count,1)
        self.assertTrue(self.gear(3)['complete'])
    def test_failed_refresh_preserves_old_positive_and_does_not_confirm_stale_negative(self):
        self.sync();response=self.client.connectapi.side_effect
        def broken(url,params):
            if BANDANA in url:raise ValueError('private')
            return response(url,params)
        self.client.connectapi.side_effect=broken
        with self.assertRaises(ValueError):self.sync(refresh=True,now=1100)
        self.assertFalse(self.gear(2)['complete']);self.assertFalse(self.gear(3)['complete'])
        self.assertIn('Ice bandana',[g['name'] for g in self.gear(2)['items']])
    def test_pause_preserves_completed_item_and_no_false_completion(self):
        class Progress:
            def isCancelled(inner):return self.cache.detail(SHOES,LINKS)[0]
            def update(inner,*args):pass
        self.job=SyncJob(Progress())
        with self.assertRaises(SyncPaused):self.sync()
        self.assertFalse(self.gear(3)['complete'])
        self.job=SyncJob();self.client.reset_mock();self.sync(refresh=True,now=1100)
        self.assertEqual(self.client.connectapi.call_count,1);self.assertTrue(self.gear(3)['complete'])
    def test_malformed_or_repeated_page_is_not_a_successful_empty_check(self):
        for raw in ({},None,[dict(uuid='invalid')]):
            with self.subTest(raw=raw),self.assertRaises((ValueError,TypeError)):clean_catalog(raw)
        self.client.connectapi.side_effect=lambda *args,**kwargs:[dict(activityId=1)]*100
        with self.assertRaises(ValueError):self.sync()
        self.assertFalse(self.gear(3)['complete'])
    def test_profile_restore_fetches_once_and_keeps_personal_fields_out(self):
        self.client.profile_id=None;response=self.client.connectapi.side_effect
        def profile(url,params=None):
            return dict(profileId=99,fullName='Not saved',email='private') if 'socialProfile' in url else response(url,params)
        self.client.connectapi.side_effect=profile;self.sync()
        self.assertEqual(self.cache.meta('gear_profile_v1'),dict(id=99))
        self.client.profile_id=None;self.client.reset_mock();self.sync(refresh=True,now=1100)
        self.assertFalse(any('socialProfile' in c.args[0] for c in self.client.connectapi.call_args_list))
    def test_deleted_gear_is_removed_only_after_a_complete_catalog_refresh(self):
        self.sync();self.client.get_gear.return_value=[dict(uuid=SHOES,displayName='Shoes')]
        self.sync(refresh=True,now=1100)
        self.assertEqual([i['name'] for i in self.gear(2)['items']],['Shoes'])


class GearIntegrationTest(GearFixture,unittest.TestCase):
    def test_normal_sync_backfills_full_history_and_exports_saved_gear_offline(self):
        session=Session();session.cache.close();session.cache=self.cache;session.client=self.client
        settings=json.dumps(dict(full_history=True,include_gear=True))
        result=session.dashboard('2026-10-24',7,settings)
        self.assertEqual(result['sync']['gear']['pending'],0)
        self.assertIsNotNone(self.gear(1))
        self.client.reset_mock()
        review=session.route_review('2026-10-24',settings)['route_review']
        comparison=session.comparison('2026-10-24',7,settings)['comparison']
        self.assertEqual(validate_review(review),review);self.assertEqual(validate_snapshot(comparison),comparison)
        self.assertEqual(review['details'][ACTIVITY_GEAR]['2']['items'][-1]['name'],'Ice bandana')
        self.assertNotIn('gear_profile',json.dumps(review))
        self.assertEqual(self.client.mock_calls,[])
        bad=copy.deepcopy(review);bad['details'][ACTIVITY_GEAR]['2']['items'][0]['password']='secret'
        with self.assertRaises(ValueError):validate_review(bad)
    def test_optional_gear_error_preserves_charts_and_reports_pending_without_provider_text(self):
        session=Session();session.cache.close();session.cache=self.cache;session.client=self.client
        self.client.get_gear.side_effect=ValueError('private provider detail')
        result=session.dashboard('2026-10-24',7,json.dumps(dict(full_history=True,include_gear=True)))
        self.assertTrue(result['sync_paused']);self.assertTrue(result['has_saved_data'])
        self.assertGreater(result['sync']['gear']['pending'],0)
        self.assertNotIn('private provider detail',str(result['warnings']))
    def test_terrain_only_and_disabled_gear_do_not_fetch_gear(self):
        session=Session();session.cache.close();session.cache=self.cache;session.client=self.client
        session.dashboard('2026-10-24',7,'{}')
        session.dashboard('2026-10-24',7,'{"include_gear":true}',terrain_only=True)
        self.client.get_gear.assert_not_called();self.client.connectapi.assert_not_called()


if __name__=='__main__':unittest.main()
