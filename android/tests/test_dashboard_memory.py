"""Detailed recording caches must never be multiplied across UI/chart responses."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from garmin_backend import Session
from route_terrain import metrics


class DashboardMemoryTest(unittest.TestCase):
    def setUp(self):
        self.session=Session();self.addCleanup(self.session.cache.close)
        rows=[dict(activityId=i,activityName='Easy reference',activityType='running',startTimeLocal=f'2026-10-{i:02d} 06:00:00',
            distance=6000,duration=1800,averageHR=128,elevationGain=30,elevationLoss=30) for i in range(1,21)]
        self.session.cache.save_window('2026-10-01','2026-10-21',rows)
        self.recording=dict(profile_version=1,geometry_version=2,source='opentopodata:synthetic',
            profile=[[i*6,round(i*.03,4),round(i*.03,4)] for i in range(1001)],
            heights=[[i*6,100+(i%20)*.2] for i in range(1001)],
            track=[[i*6,round(i/1000,6),round((i%100)/100,6)] for i in range(1000)])
        for i in range(1,21):
            self.session.cache.save_detail(str(i),'terrain_v1',dict(status='ok',source='opentopodata:synthetic',elevation_gain=30,elevation_loss=30,samples=1001,route=self.recording))
            self.session.cache.save_detail(str(i),'route_data_v1',dict(profile_version=2,profile=self.recording['profile'],cells=[[1,1],[2,2]]))
        fingerprint=self.session.cache.db.execute("SELECT fingerprint FROM runs WHERE id='1'").fetchone()[0]
        self.session.cache.save_meta('route_book_v2',[dict(id='test',name='Test course',shape='out_back',surface='road',extent=3000,extent_version=1,reverse=False,
            reference=dict(id='1',title='Reference',date='2026-10-01',distance=6000,duration=1800,fingerprint=fingerprint))])
        self.settings=json.dumps(dict(include_terrain=True,include_recovery=False,include_recordings=False,include_weather=False,include_station_weather=False,
            classification_mode='native',target_source='custom',target_time='20:00',target_route_id='test',target_route_engine=4))
    def test_profiles_stay_cached_but_never_enter_dashboard_json_or_chart_points(self):
        fixed=self.session.cached_dashboard('2026-10-21',30,self.settings)
        encoded=json.dumps(fixed)
        for key in ('"profile"','"heights"','"track"','"cells"','"profile_version"'):
            self.assertNotIn(key,encoded)
        self.assertLess(len(encoded),500_000)
        self.assertEqual(fixed['sync']['terrain']['done'],20)
        self.assertTrue(fixed['targets']['route_plans'])
        self.assertEqual(self.session.cache.detail('1','terrain_v1')[1]['route'],self.recording)
        # Reproduce the previous transfer bug with exactly the same cache/model.
        with patch('dashboard_sync.terrain_metrics',side_effect=lambda entry:entry):
            oversized=self.session.cached_dashboard('2026-10-21',30,self.settings)
        self.assertGreater(len(json.dumps(oversized)),len(encoded)*20)
    def test_coverage_picker_and_exports_stream_large_entries_and_keep_only_needed_fields(self):
        original=self.session.cache.all_details
        def guard(kind):
            if kind in ('terrain_v1','route_data_v1'):raise AssertionError('Full recording catalog retained in memory')
            return original(kind)
        with patch.object(self.session.cache,'all_details',side_effect=guard):
            self.session.cached_dashboard('2026-10-21',30,self.settings)
            selection=self.session.route_use('test',self.settings)['selection']
            self.assertIn('gain_per_mile',selection)
            self.assertEqual(len(self.session.route_candidates_v2('test','2026-10-21',self.settings)['candidates']),20)
            comparison=self.session.comparison('2026-10-21',30,self.settings)['comparison']
            self.assertNotIn('route',comparison['details']['terrain_v1']['1'])
            review=self.session.route_review('2026-10-21',self.settings)['route_review']
            self.assertEqual(len(review['reference_recordings']),1)
            self.assertNotIn('route',review['details']['terrain_v1']['1'])
    def test_metrics_allowlist_is_small_and_does_not_mutate_original(self):
        raw=dict(status='ok',source='opentopodata:synthetic',elevation_gain=30,elevation_loss=30,route=copy.deepcopy(self.recording),extra='ignored')
        before=copy.deepcopy(raw)
        self.assertEqual(metrics(raw),dict(status='ok',source='opentopodata:synthetic',elevation_gain=30,elevation_loss=30))
        self.assertEqual(raw,before)
    def test_startup_builds_flags_once_then_chart_refresh_reuses_them_and_sync_updates_them(self):
        with patch.object(self.session.cache,'iter_details',wraps=self.session.cache.iter_details) as reads:
            self.session.cached_dashboard('2026-10-21',30,self.settings)
            self.session.cached_dashboard('2026-10-21',30,self.settings)
            self.assertEqual(sum(call.args==('terrain_v1',) for call in reads.call_args_list),1)
            self.session.cache.save_detail('20','terrain_v1',dict(status='skipped',reason='no_route'))
            updated=self.session.cached_dashboard('2026-10-21',30,self.settings)
            self.assertEqual(updated['sync']['terrain']['done'],19);self.assertEqual(updated['sync']['terrain']['skipped'],1)
            self.assertEqual(sum(call.args==('terrain_v1',) for call in reads.call_args_list),1)
        rows=self.session.cache.activities('2026-10-01','2026-10-21');rows[0]['distance']+=100
        self.session.cache.save_window('2026-10-01','2026-10-21',rows)
        self.assertNotIn(str(rows[0]['activityId']),self.session.cache._terrain_states)
        self.session.cache.clear();self.assertIsNone(self.session.cache._terrain_states)


if __name__=='__main__':unittest.main()
