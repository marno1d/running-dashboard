"""Spatial route projection, reference migration, workout inference and private profiles."""
import copy
import io
import json
import math
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import Mock
import zipfile
from fitdecode.utils import compute_crc

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from training_routes import recording_data
from route_workouts import RoutePath,phases_for,project,infer_workout,workout_definition,apply_route,WALKING_PACE
from garmin_backend import Session,InputError
from test_easy_targets import runs


def profile_fit():
    fields=[(253,4,0x86),(0,4,0x85),(1,4,0x85),(5,4,0x86),(2,2,0x84)]
    body=b'\x40\x00\x00'+struct.pack('<H',20)+bytes([len(fields)])+b''.join(bytes(f) for f in fields)
    for i,step in enumerate((0,1,2,3,2,1,0,1,2,3,2,1,0)):
        body+=b'\x00'+struct.pack('<IiiIH',900000000+i*300,round((40+step*.01)*2**31/180),round(-111*2**31/180),i*100000,round((100+step*100+500)*5))
    data=struct.pack('<BBHI4s',12,16,21171,len(body),b'.FIT')+body
    data+=struct.pack('<H',compute_crc(data))
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:archive.writestr('synthetic.fit',data)
    return out.getvalue()


class PathTest(unittest.TestCase):
    def setUp(self):self.profile=[[0,0,0],[1000,100,0],[2000,100,40],[4000,300,40]]
    def test_profile_retains_distance_and_ascent_descent_without_gps_track(self):
        data=recording_data(profile_fit())
        self.assertEqual(data['profile_version'],2)
        self.assertEqual(data['profile'][0],[0,0,0])
        self.assertEqual(data['profile'][-1],[12000,600,600])
        self.assertEqual(data['suggested_turn'],3000)
        self.assertEqual(data['suggested_loop'],6000)
        self.assertNotIn('timestamp',json.dumps(data))
    def test_shorter_out_and_back_uses_only_nearby_hills(self):
        path=RoutePath(self.profile,'out_back',4000,turn=1000)
        self.assertEqual(path.delta(0,1000),(100,0))
        self.assertEqual(path.delta(1000,2000),(0,100))
        self.assertEqual(path.delta(0,2000),(100,100))
        longer=RoutePath(self.profile,'out_back',4000,turn=3000)
        self.assertEqual(longer.delta(0,6000),(240,240))
    def test_repeated_loops_include_exact_fractional_lap(self):
        path=RoutePath(self.profile,'loop',2000)
        self.assertEqual(path.delta(0,5000),(300,80))
        self.assertFalse(path.beyond_reference(42195))
    def test_one_way_extrapolation_is_explicit(self):
        path=RoutePath(self.profile,'one_way',4000)
        self.assertEqual(path.delta(0,8000),(600,80))
        self.assertFalse(path.beyond_reference(3000));self.assertTrue(path.beyond_reference(8000))
    def test_out_and_back_extrapolation_mirrors_the_return(self):
        path=RoutePath(self.profile,'out_back',4000,turn=5000)
        self.assertEqual(path.delta(0,10000),(425,425))
        self.assertTrue(path.beyond_reference(10000))
    def test_reversing_reference_swaps_gain_and_loss(self):
        path=RoutePath(self.profile,'one_way',reverse=True)
        self.assertEqual(path.delta(0,4000),(40,300))
        self.assertEqual(path.delta(0,1000),(0,100))
    def test_invalid_profiles_are_rejected(self):
        for profile in ([],[[0,0,0]],[[0,0,0],[0,1,1]],[[0,0,0],[100,math.nan,0]],[[0,0,0],[100,-1,0]]):
            with self.subTest(profile=profile),self.assertRaises(ValueError):RoutePath(profile)


class WorkoutProjectionTest(unittest.TestCase):
    def setUp(self):self.flat=[[0,0,0],[10000,0,0]]
    def test_flat_easy_duration_and_distance_are_exact(self):
        phases=phases_for({},'easy',360)
        plan=project(self.flat,'out_back',5000,False,phases,{})
        self.assertAlmostEqual(plan['duration'],2700)
        self.assertAlmostEqual(plan['distance'],7500)
        self.assertAlmostEqual(plan['turnaround'],3750,delta=.25)
        self.assertAlmostEqual(plan['pace'],360)
    def test_timed_turnaround_matches_round_trip_time_on_a_hill(self):
        profile=[[0,0,0],[10000,1000,0]]
        plan=project(profile,'out_back',10000,False,phases_for({},'easy',360),{})
        self.assertAlmostEqual(plan['duration'],2700)
        self.assertAlmostEqual(plan['distance'],2*plan['turnaround'],delta=.5)
        self.assertAlmostEqual(plan['gain'],plan['loss'],delta=.2)
        # Uphill outward and downhill home do not consume equal time.
        path=RoutePath(profile,'out_back',10000,turn=plan['turnaround'])
        from route_workouts import simulate
        outward=simulate(path,[dict(kind='easy',duration=1e12,base_pace=360)],{},fixed_distance=plan['turnaround'])
        self.assertGreater(outward['duration'],1350)
    def test_interval_phases_include_walk_after_last_rep_and_use_easy_for_warmcool(self):
        settings=dict(workout_definitions=dict(short=dict(warmup=10,reps=3,work=3,cooldown=5)),target_walking_pace=800)
        phases=phases_for(settings,'short',400,300)
        self.assertEqual([p['kind'] for p in phases],['warmup','work','walk','work','walk','work','walk','cooldown'])
        self.assertEqual(phases[0]['base_pace'],400);self.assertEqual(phases[-1]['base_pace'],400)
        plan=project(self.flat,'loop',10000,False,phases,settings)
        self.assertAlmostEqual(plan['work_duration'],540)
        self.assertAlmostEqual(plan['work_distance'],1800)
        self.assertAlmostEqual(plan['work_pace'],300)
        self.assertAlmostEqual(plan['distance'],2250+1800+225)
        self.assertTrue(all(abs(p['duration']-60)<1e-7 for p in plan['phases'] if p['kind']=='walk'))
    def test_warmup_and_walking_move_work_to_different_hills(self):
        profile=[[0,0,0],[1000,100,0],[1200,100,0],[2000,200,0],[10000,200,0]]
        settings=dict(workout_definitions=dict(short=dict(warmup=0,reps=1,work=3,cooldown=0)),target_walking_pace=800)
        first=project(profile,'one_way',10000,False,phases_for(settings,'short',400,300),settings)
        second_settings=copy.deepcopy(settings);second_settings['workout_definitions']['short']['warmup']=8
        second=project(profile,'one_way',10000,False,phases_for(second_settings,'short',400,300),second_settings)
        self.assertNotAlmostEqual(first['work_gain'],second['work_gain'])
        self.assertNotAlmostEqual(first['work_pace'],second['work_pace'])
        self.assertGreater(second['gain'],second['work_gain'])
    def test_work_gain_excludes_walking_and_cooldown(self):
        profile=[[0,0,0],[10000,1000,0]]
        settings=dict(workout_definitions=dict(short=dict(warmup=1,reps=2,work=1,cooldown=1)))
        plan=project(profile,'loop',10000,False,phases_for(settings,'short',360,300),settings)
        work=[p for p in plan['phases'] if p['kind']=='work']
        self.assertAlmostEqual(plan['work_gain'],sum(p['gain'] for p in work))
        self.assertLess(plan['work_gain'],plan['gain'])
    def test_fixed_marathon_repeats_a_loop_and_uses_its_own_distance(self):
        profile=[[0,0,0],[1000,20,0],[2000,20,20]]
        phases=[dict(kind='race',duration=1e12,base_pace=300)]
        plan=project(profile,'loop',2000,False,phases,{},42195)
        self.assertAlmostEqual(plan['distance'],42195)
        self.assertAlmostEqual(plan['gain'],(21*20+.195*20)/.3048)
        self.assertFalse(plan['extrapolated'])
    def test_walking_speed_remains_configured_on_hills(self):
        plan=project([[0,0,0],[1000,100,0]],'one_way',1000,False,[dict(kind='walk',duration=60,base_pace=750)],{})
        self.assertAlmostEqual(plan['distance'],80)
    def test_weather_is_applied_once_and_manual_rates_do_not_leak_into_route_mode(self):
        settings=dict(target_temperature=90,target_humidity=80,target_gain_per_mile=999,target_loss_per_mile=999)
        plan=project(self.flat,'one_way',10000,False,[dict(kind='race',duration=1e12,base_pace=300)],settings,6000)
        self.assertAlmostEqual(plan['pace'],300/.96)
        self.assertEqual(plan['gain'],0)
    def test_missing_128_model_does_not_invent_a_pace(self):
        with self.assertRaises(ValueError):phases_for({},'short',None,300)
    def test_no_easy_model_is_needed_when_both_warmup_and_cooldown_are_zero(self):
        phases=phases_for(dict(workout_definitions=dict(short=dict(warmup=0,reps=1,work=3,cooldown=0))),'short',None,300)
        self.assertEqual([p['kind'] for p in phases],['work','walk'])
    def test_invalid_definitions_and_excessive_durations_rejected(self):
        for patch in ({'reps':0},{'reps':1.5},{'warmup':-1},{'work':0},{'reps':40,'work':60}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):workout_definition(dict(workout_definitions=dict(short=patch)),'short')


class RouteBackendV2Test(unittest.TestCase):
    def setUp(self):
        self.session=Session();self.addCleanup(self.session.cache.close)
        activities=[]
        for i,row in enumerate(runs(),1):activities.append(dict(activityId=i,activityName='Easy '+str(i),activityType='running',startTimeLocal=row['started'],distance=row['distance'],duration=row['duration'],averageHR=row['average_hr'],elevationGain=0,elevationLoss=0))
        self.session.cache.save_window('2026-09-01','2026-10-21',activities)
        self.settings=dict(classification_mode='native',include_recovery=False,include_recordings=False,include_weather=False,include_station_weather=False,
            target_source='custom',target_time='20:00',target_gain_per_mile=0,target_loss_per_mile=0,target_route_id='liberty',target_route_engine=2,
            categories={str(i):'easy' for i in range(1,8)})
        self.session.client=Mock();self.session.client.download_activity.return_value=profile_fit()
    def config(self,**changes):return json.dumps(dict(self.settings,**changes))
    def assign(self):return self.session.route_reference('liberty','1','2026-10-21',self.config())
    def test_one_reference_shape_surface_and_longer_gps_suggestions(self):
        self.assign()
        book=self.session.route_book(self.config())['routes'];route=next(r for r in book if r['id']=='liberty')
        self.assertTrue(route['profile_ready']);self.assertEqual(route['extent'],6000)
        self.session.route_configure('liberty',json.dumps(dict(shape='out_back',surface='trail',reverse=True)),self.config())
        selected=self.session.route_use('liberty',self.config())['selection']
        self.assertEqual(selected['extent'],3000);self.assertEqual(selected['surface'],'trail');self.assertTrue(selected['reverse'])
        self.assertNotIn('profile',selected)
        candidates=self.session.route_candidates_v2('liberty','2026-10-21',self.config())['candidates']
        self.assertNotIn('cells',json.dumps(candidates))
    def candidate_history(self):
        distances={1:6000,2:12000,3:18000,4:4000,5:10000,6:14000,7:8000}
        activities=[dict(activityId=i,activityName='Reference '+str(i),activityType='running',
            startTimeLocal=f'2026-10-21 {23-i:02d}:00:00',distance=distance,duration=distance*.3,averageHR=128)
            for i,distance in distances.items()]
        self.session.cache.save_window('2026-09-01','2026-10-21',activities)
        for i,distance in distances.items():
            data=dict(profile_version=2,profile=[[0,0,0],[distance,10,10]],cells=[[10,10],[11,11]])
            if i==3:data['cells']=[[1000,1000],[1001,1001]]
            self.session.cache.save_detail(str(i),'route_data_v1',data)
            self.session.cache.save_detail(str(i),'route_outline_v1',dict(segments=[[[0,1],[1,0]]]))
        return distances
    def test_reference_browser_is_newest_first_even_for_longer_gps_matches(self):
        self.candidate_history();self.assign()
        result=self.session.route_candidates_v2('liberty','2026-10-21',self.config())
        rows=result['candidates']
        self.assertEqual([r['id'] for r in rows],list(map(str,range(1,8))))
        self.assertTrue(rows[1]['longer']);self.assertGreater(rows[1]['overlap'],.9)
        self.assertTrue(all('category' in r and 'needs_review' in r and r['outline']['segments'] for r in rows))
        self.session.client.download_activity.assert_not_called()
    def test_comparison_uses_prospective_reference_and_never_saves_it(self):
        self.candidate_history();self.session.route_reference('liberty','3','2026-10-21',self.config())
        before=self.session.cache.meta('route_book_v2')
        self.session.client=None
        result=self.session.route_matches('liberty','1','2026-10-21',self.config())
        self.assertEqual(result['original']['id'],'1')
        self.assertEqual([r['id'] for r in result['candidates']],['6','2','5','7'])
        self.assertEqual(result['remaining'],0);self.assertEqual(result['checked'],5)
        self.assertEqual(self.session.cache.meta('route_book_v2'),before)
        self.assertNotIn('cells',json.dumps(result));self.assertNotIn('profile_version',json.dumps(result))
    def test_much_longer_run_matches_by_covering_original_path_not_by_equal_size(self):
        self.candidate_history()
        for identity,cells in [('1',[[i,10] for i in range(100)]),('2',[[i,10] for i in range(300)]),('3',[[50,i] for i in range(300)])]:
            data=self.session.cache.detail(identity,'route_data_v1')[1];data['cells']=cells
            self.session.cache.save_detail(identity,'route_data_v1',data)
        result=self.session.route_matches('liberty','1','2026-10-21',self.config())
        self.assertEqual([r['id'] for r in result['candidates']],['2'])
        self.assertEqual(result['candidates'][0]['overlap'],1)
        self.session.client.download_activity.assert_not_called()
    def test_keep_original_and_use_longer_are_explicit_reference_assignments(self):
        self.candidate_history()
        result=self.session.route_matches('liberty','1','2026-10-21',self.config())
        self.assertIsNone(self.session.cache.meta('route_book_v2'))
        self.session.route_reference('liberty',result['original']['id'],'2026-10-21',self.config())
        self.assertEqual(self.session.route_use('liberty',self.config())['selection']['id'],'liberty')
        first=next(r for r in self.session.route_book(self.config())['routes'] if r['id']=='liberty')
        self.assertEqual(first['reference']['id'],'1')
        self.session.route_reference('liberty',result['candidates'][0]['id'],'2026-10-21',self.config())
        second=next(r for r in self.session.route_book(self.config())['routes'] if r['id']=='liberty')
        self.assertEqual(second['reference']['id'],'6');self.assertEqual(second['reference']['distance'],14000)
    def test_longer_scan_checks_largest_first_and_reuses_completed_recordings(self):
        self.candidate_history()
        self.session.cache.db.execute("DELETE FROM details WHERE id!='1'");self.session.cache.db.commit()
        result=self.session.route_matches('liberty','1','2026-10-21',self.config(),2)
        calls=self.session.client.download_activity.call_args_list
        self.assertEqual([call.args[0] for call in calls],['3','6'])
        self.assertEqual(result['remaining'],3)
        result=self.session.route_matches('liberty','1','2026-10-21',self.config(),100)
        self.assertEqual([call.args[0] for call in self.session.client.download_activity.call_args_list],['3','6','2','5','7'])
        self.assertEqual(result['remaining'],0)
        before=self.session.client.download_activity.call_count
        self.session.route_matches('liberty','1','2026-10-21',self.config(),5)
        self.assertEqual(self.session.client.download_activity.call_count,before)
    def test_failed_longer_scan_preserves_original_choice_and_can_retry(self):
        self.candidate_history();self.assign()
        self.session.cache.db.execute("DELETE FROM details WHERE id!='1'");self.session.cache.db.commit()
        before=self.session.cache.meta('route_book_v2');self.session.client.download_activity.side_effect=OSError('private')
        result=self.session.route_matches('liberty','1','2026-10-21',self.config(),5)
        self.assertIsNotNone(result['scan_error']);self.assertNotIn('private',json.dumps(result))
        self.assertEqual(result['original']['id'],'1');self.assertEqual(result['remaining'],5)
        self.assertEqual(self.session.cache.meta('route_book_v2'),before)
        self.session.client.download_activity.side_effect=None
        self.assertIsNone(self.session.route_matches('liberty','1','2026-10-21',self.config(),5)['scan_error'])
    def test_browser_needs_review_follows_each_sessions_category_and_work_data(self):
        self.candidate_history()
        settings=self.config(categories={'1':'short','2':'medium','3':'long','4':'easy','5':'easy_long','6':'other','7':'trial'})
        rows={r['id']:r for r in self.session.route_candidates_v2('liberty','2026-10-21',settings)['candidates']}
        self.assertTrue(all(rows[i]['needs_review'] for i in ('1','2','3','6','7')))
        self.assertFalse(rows['4']['needs_review']);self.assertFalse(rows['5']['needs_review'])
    def test_all_workouts_and_races_project_without_network_and_export_no_profiles(self):
        self.assign();self.session.client=None
        before=self.session.cache.db.total_changes
        data=self.session.cached_dashboard('2026-10-21',30,self.config())
        target=data['targets'];self.assertEqual(target['route_engine'],2)
        self.assertTrue(all(not p.get('error') for p in target['route_plans']))
        self.assertEqual(len(target['route_plans']),5)
        self.assertTrue(all(p['pace'] for p in target['rows']))
        self.assertGreater(target['races'][-1]['gain'],target['races'][0]['gain'])
        self.assertEqual(self.session.cache.db.total_changes,before)
        snapshot=self.session.comparison('2026-10-21',30,self.config())['comparison']
        from comparison_contract import validate_snapshot
        validate_snapshot(snapshot)
        encoded=json.dumps(snapshot)
        for banned in ('route_data_v1','route_book_v2','profile_version','"profile"','"cells"'):self.assertNotIn(banned,encoded)
        self.assertEqual(len(snapshot['android']['targets']['route_plans']),5)
    def test_route_surface_controls_128_model_and_missing_surface_is_explicit(self):
        self.assign();self.session.route_configure('liberty',json.dumps(dict(surface='trail')),self.config())
        target=self.session.cached_dashboard('2026-10-21',30,self.config())['targets']
        self.assertTrue(all(p.get('error') for p in target['route_plans']))
        self.assertTrue(all(p['pace'] is None for p in target['rows']))
        self.assertTrue(target['races'][0]['pace'])
    def test_missing_profile_requests_explicit_reload_instead_of_density_fallback(self):
        self.assign();self.session.cache.save_detail('1','route_data_v1',dict(cells=[[1,1],[2,2]],laps=[]))
        result=self.session.cached_dashboard('2026-10-21',30,self.config())['targets']
        self.assertIn('route_error',result);self.assertTrue(all(row['pace'] is None for row in result['rows']))
        before=self.session.client.download_activity.call_count
        self.session.route_use('liberty',self.config())
        self.assertEqual(self.session.client.download_activity.call_count,before+1)
    def test_legacy_reference_migrates_to_one_route_and_signout_clears_it(self):
        self.session.route_assign('liberty','easy','1','2026-10-21',self.config())
        route=next(r for r in self.session.route_book(self.config())['routes'] if r['id']=='liberty')
        self.assertEqual(route['reference']['id'],'1')
        self.session.logout()
        self.assertTrue(all(r['reference'] is None for r in self.session.route_book(self.config())['routes']))
    def test_legacy_work_only_reference_migrates_to_whole_reference_length_and_time(self):
        old=dict(id='1',title='Old work reference',date='2026-10-21',distance=2000,duration=600,interval=True,gain=0,loss=0,fingerprint=self.session.cache.db.execute("SELECT fingerprint FROM runs WHERE id='1'").fetchone()[0])
        from training_routes import configuration
        routes=configuration(self.session.cache);next(r for r in routes if r['id']=='liberty')['references']['intervals']=old
        self.session.cache.save_meta('training_routes_v1',routes)
        migrated=next(r for r in self.session.route_book(self.config())['routes'] if r['id']=='liberty')['reference']
        self.assertEqual(migrated['distance'],6000);self.assertGreater(migrated['duration'],600)
    def test_latest_workout_is_an_explicit_copy_from_the_latest_matching_session(self):
        data=recording_data(profile_fit())
        data['laps']=[dict(duration=600,distance=1500,active=False,intensity='warmup'),dict(duration=180,distance=600,active=True,intensity='active'),dict(duration=60,distance=75,active=False,intensity='rest'),dict(duration=180,distance=600,active=True,intensity='active'),dict(duration=360,distance=900,active=False,intensity='cooldown')]
        self.session.cache.save_detail('1','route_data_v1',data)
        settings=json.loads(self.config());settings['categories']['1']='short';settings['categories']['2']='short'
        before=copy.deepcopy(settings)
        result=self.session.workout_latest('short','2026-10-21',json.dumps(settings))
        self.assertEqual(result['source']['id'],'1');self.assertEqual(result['definition'],dict(warmup=10,cooldown=5,reps=2,work=3))
        self.assertEqual(result['walking_pace'],800);self.assertEqual(before,settings)
        self.assertEqual(self.session.workout_latest('walking','2026-10-21',json.dumps(settings))['walking_pace'],800)
        self.session.client.download_activity.assert_not_called()
    def test_latest_easy_duration_and_missing_type(self):
        result=self.session.workout_latest('easy','2026-10-21',self.config())
        self.assertEqual(result['source']['id'],'1');self.assertGreater(result['minutes'],5)
        with self.assertRaises(InputError):self.session.workout_latest('long','2026-10-21',self.config())
    def test_stale_reference_is_rejected_without_automatic_download(self):
        self.assign();self.session.cache.db.execute("UPDATE runs SET fingerprint='changed' WHERE id='1'")
        before=self.session.client.download_activity.call_count
        with self.assertRaises(InputError):self.session.route_use('liberty',self.config())
        target=self.session.cached_dashboard('2026-10-21',30,self.config())['targets']
        self.assertIn('route_error',target);self.assertEqual(self.session.client.download_activity.call_count,before)
    def test_one_way_recording_can_supply_a_complete_outward_leg(self):
        extent=self.session._route_extent(dict(shape='out_back'),dict(profile=[[0,0,0],[5000,100,0]],suggested_turn=5000))
        self.assertEqual(extent,5000)


class WorkoutInferenceTest(unittest.TestCase):
    def test_uses_selected_work_and_deducts_final_minute_from_cooldown(self):
        laps=[dict(duration=600,distance=1500,active=False,intensity='warmup'),dict(duration=180,distance=600,active=True,intensity='active'),dict(duration=60,distance=75,active=False,intensity='rest'),dict(duration=180,distance=600,active=True,intensity='active'),dict(duration=60,distance=75,active=False,intensity='rest'),dict(duration=300,distance=750,active=False,intensity='cooldown')]
        definition,walking=infer_workout(dict(laps=laps),'short',{},'1')
        self.assertEqual(definition,dict(warmup=10,cooldown=5,reps=2,work=3))
        self.assertEqual(walking,800)
        changed,_=infer_workout(dict(laps=laps),'short',dict(laps={'1':[3]}),'1')
        self.assertEqual(changed['reps'],1);self.assertEqual(changed['warmup'],14)
    def test_unmoving_recoveries_do_not_produce_walking_speed(self):
        laps=[dict(duration=180,distance=600,active=True,intensity='active'),dict(duration=60,distance=0,active=False,intensity='rest')]
        definition,walking=infer_workout(dict(laps=laps),'short',{},'1')
        self.assertIsNone(walking);self.assertEqual(definition['cooldown'],0)
    def test_no_work_laps_requires_manual_definition(self):
        with self.assertRaises(ValueError):infer_workout(dict(laps=[]),'short',{},'1')


if __name__=='__main__':unittest.main()
