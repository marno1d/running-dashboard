"""Route averages summarize a course; predictions follow its actual terrain."""
import json
from pathlib import Path
import sys
import unittest
import shutil

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from route_workouts import average_rates
from dashboard_metrics import MILE,upcoming_pace
from garmin_backend import Session
from test_easy_targets import runs


class AverageRatesTest(unittest.TestCase):
    profile=dict(profile=[[0,0,0],[MILE,100*.3048,20*.3048],[2*MILE,400*.3048,100*.3048]])
    def rates(self,shape,extent=None,reverse=False):
        return average_rates(dict(shape=shape,extent=extent,reverse=reverse),self.profile)
    def test_one_way_averages_entire_course_and_reversing_swaps_gain_loss(self):
        self.assertEqual(self.rates('one_way'),dict(gain_per_mile=200,loss_per_mile=50))
        self.assertEqual(self.rates('one_way',reverse=True),dict(gain_per_mile=50,loss_per_mile=200))
    def test_loop_uses_selected_lap_length(self):
        self.assertEqual(self.rates('loop',MILE),dict(gain_per_mile=125,loss_per_mile=125))
    def test_out_and_back_includes_reversed_return(self):
        self.assertEqual(self.rates('out_back',MILE),dict(gain_per_mile=60,loss_per_mile=60))
    def test_fractional_rates_keep_one_decimal(self):
        rates=average_rates(dict(shape='one_way'),dict(profile=[[0,0,0],[MILE,12.34,5.67]]))
        self.assertEqual(rates,dict(gain_per_mile=40.5,loss_per_mile=18.6))


class AverageTargetsTest(unittest.TestCase):
    def setUp(self):
        self.session=Session();self.addCleanup(self.session.cache.close)
        activities=[dict(activityId=i,activityName='Easy '+str(i),activityType='running',startTimeLocal=row['started'],
            distance=row['distance'],duration=row['duration'],averageHR=row['average_hr'],elevationGain=0,elevationLoss=0)
            for i,row in enumerate(runs(),1)]
        self.session.cache.save_window('2026-09-01','2026-10-21',activities)
        fingerprint=self.session.cache.db.execute("SELECT fingerprint FROM runs WHERE id='1'").fetchone()[0]
        self.route=dict(id='liberty',name='Liberty Park',shape='out_back',surface='road',extent=3000,reverse=False,extent_version=1,
            reference=dict(id='1',title='Reference',date='2026-10-20',distance=6000,duration=2400,fingerprint=fingerprint))
        self.terrain=dict(source='opentopodata:synthetic',profile_version=1,profile=[[0,0,0],[1000,100,0],[2000,100,30],[3000,300,30],[6000,330,330]])
        self.session.cache.save_meta('route_book_v2',[self.route]);self.session.cache.save_detail('1','terrain_v1',dict(status='ok',source='opentopodata:synthetic',elevation_gain=330,elevation_loss=330,route=self.terrain))
        self.settings=dict(classification_mode='native',include_recovery=False,include_recordings=False,
            include_weather=False,include_station_weather=False,target_source='custom',target_time='20:00',
            target_route_engine=3,target_route_source='opentopodata:synthetic',target_route_id='liberty',target_route_name='Liberty Park',target_route_surface='road',
            target_route_shape='loop',target_gain_per_mile='54.3',target_loss_per_mile='42.1',target_temperature=80,target_humidity=50,
            categories={str(i):'easy' for i in range(1,8)})
    def targets(self,**changes):
        return self.session.cached_dashboard('2026-10-21',30,json.dumps(dict(self.settings,**changes)))['targets']
    def test_interval_paces_follow_work_segments_and_fields_only_summarize_course(self):
        target=self.targets()
        self.assertEqual(target['route_engine'],4)
        rates=average_rates(self.route,self.terrain)
        self.assertEqual(target['route_gain_per_mile'],rates['gain_per_mile']);self.assertEqual(target['route_loss_per_mile'],rates['loss_per_mile'])
        plans={p['kind']:p for p in target['route_plans']}
        for row in target['rows']:
            plan=plans[row['category']]
            self.assertAlmostEqual(row['pace'],plan['work_duration']/plan['work_distance']*1000)
        short=[p['pace'] for p in plans['short']['phases'] if p['kind']=='work']
        self.assertGreater(max(short)-min(short),1)
        self.assertTrue(all(not p.get('error') for p in target['route_plans']))
    def test_easy_durations_work_defs_and_walking_are_preserved(self):
        target=self.targets(target_easy_minutes=50,target_easy_long_minutes=90,
            workout_definitions=dict(short=dict(warmup=5,reps=4,work=2.5,cooldown=7)),target_walking_pace=800)
        plans={p['kind']:p for p in target['route_plans']}
        self.assertAlmostEqual(plans['easy']['duration'],50*60);self.assertAlmostEqual(plans['easy_long']['duration'],90*60)
        phases=plans['short']['phases'];self.assertEqual(sum(p['kind']=='work' for p in phases),4)
        walks=[p for p in phases if p['kind']=='walk'];self.assertEqual(len(walks),4)
        self.assertTrue(all(abs((p['end']-p['start'])-75)<1e-6 for p in walks))
    def test_route_ignores_manual_rate_edits_until_route_is_cleared_and_export_stays_private(self):
        first=self.targets();second=self.targets(target_gain_per_mile='100.5')
        self.assertEqual(second['rows'][0]['pace'],first['rows'][0]['pace'])
        manual=self.targets(target_route_id='',target_gain_per_mile='100.5')
        baseline=self.targets(target_route_id='',target_gain_per_mile='54.3')
        self.assertGreater(manual['rows'][0]['pace'],baseline['rows'][0]['pace'])
        snapshot=self.session.comparison('2026-10-21',30,json.dumps(self.settings))['comparison']
        from comparison_contract import validate_snapshot
        validate_snapshot(snapshot)
        self.assertEqual(snapshot['selection']['settings']['target_route_surface'],'road')
        self.assertEqual(snapshot['android']['targets']['route_gain_per_mile'],average_rates(self.route,self.terrain)['gain_per_mile'])
        self.assertNotIn('"profile"',json.dumps(snapshot));self.assertNotIn('"cells"',json.dumps(snapshot))
    def test_route_rates_survive_offline_without_loading_reference_again(self):
        before=self.session.cache.db.total_changes
        self.assertEqual(self.targets()['route_name'],'Liberty Park')
        self.assertEqual(self.session.cache.db.total_changes,before)
    def test_manual_easy_and_easy_long_have_separate_road_and_trail_plans(self):
        targets=self.targets(target_route_id='')
        easy=[p for p in targets['route_plans'] if p['kind'] in ('easy','easy_long')]
        self.assertEqual({(p['kind'],p['surface']) for p in easy},{('easy','road'),('easy','trail'),('easy_long','road'),('easy_long','trail')})
        road=next(p for p in easy if p['kind']=='easy' and p['surface']=='road')
        long=next(p for p in easy if p['kind']=='easy_long' and p['surface']=='road')
        self.assertAlmostEqual(road['duration'],45*60);self.assertAlmostEqual(long['duration'],80*60)
        self.assertGreater(len(long['splits']),len(road['splits']))
    @unittest.skipUnless(shutil.which('node'),'Requires actual web target math')
    def test_cleared_route_manual_predictions_keep_web_pace_parity(self):
        sys.path.insert(0,str(ROOT/'android/scripts'))
        from compare_dashboard import compare
        snapshot=self.session.comparison('2026-10-21',30,json.dumps(dict(self.settings,classification_mode='web',target_route_id='')))['comparison']
        differences=compare(snapshot)['differences']
        self.assertEqual([d for d in differences if d['metric'].startswith('targets.') and d['status']=='different'],[])


if __name__=='__main__':unittest.main()
