"""Linked route/terrain scrubbing agrees with the actual timed workout model."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from route_workouts import project,phases_for,course_profile
from workout_trace import trace
from garmin_backend import InputError
import test_dashboard_memory


class WorkoutTraceTest(unittest.TestCase):
    def setUp(self):
        self.data=dict(source='opentopodata:synthetic',profile_version=1,
            profile=[[0,0,0],[1000,80,0],[2000,80,80],[3000,100,80],[4000,100,100]],
            heights=[[0,100],[1000,180],[2000,100],[3000,120],[4000,100]],
            track=[[0,0,0],[1000,1,0],[2000,1,1],[3000,0,1],[4000,0,0]])
        self.route=dict(shape='out_back',extent=4000,reverse=False)
    def make(self,kind='easy',settings=None):
        settings=settings or {};phases=phases_for(settings,kind,360,250)
        profile=course_profile(self.route,self.data)
        plan=project(profile,self.route['shape'],self.route['extent'],self.route['reverse'] if self.route['shape']!='loop' else False,phases,settings)
        return plan,trace(self.route,self.data,plan)
    def check_paces(self,plan,result):
        by_phase=[0]*len(plan['phases'])
        for start,end,pace,index in result['paces']:by_phase[index]+=(end-start)/1000*pace
        for index,phase in enumerate(plan['phases']):self.assertAlmostEqual(by_phase[index],phase['duration'],delta=.02)
    def test_early_turn_retraces_gps_and_elevation_and_closes_at_start(self):
        plan,result=self.make(settings=dict(target_easy_minutes=10))
        turn=plan['turnaround'];self.assertLess(turn,4000)
        at=next(row for row in result['nodes'] if abs(row[0]-turn)<.001)
        self.assertGreater(at[1],0)
        self.assertAlmostEqual(result['nodes'][-1][1],0,delta=.001)
        self.assertAlmostEqual(result['nodes'][0][3],result['nodes'][-1][3],delta=.05)
        self.check_paces(plan,result)
    def test_interval_sections_include_walks_and_weight_to_exact_phase_totals(self):
        plan,result=self.make('short',dict(target_temperature=85,target_humidity=60))
        self.check_paces(plan,result)
        for _,_,pace,index in result['paces']:
            phase=plan['phases'][index]
            if phase['kind']=='walk':self.assertAlmostEqual(pace,phase['base_pace'],delta=.001)
        for phase in plan['phases']:
            self.assertTrue(any(abs(point[0]-phase['start'])<.001 for point in result['nodes']))
        self.assertGreater(len({pace for _,_,pace,_ in result['paces']}),4)
    def test_repeated_loops_use_same_gps_positions_and_closed_representative_height(self):
        self.route['shape']='loop'
        plan,result=self.make(settings=dict(target_easy_minutes=80))
        laps=[row for row in result['nodes'] if abs(row[0]%4000)<.001]
        self.assertGreaterEqual(len(laps),3)
        for row in laps:self.assertEqual(row[1:],result['nodes'][0][1:])
        self.check_paces(plan,result)
    def test_reverse_route_starts_at_original_endpoint(self):
        self.route.update(shape='one_way',reverse=True)
        self.data['track'][-1]=[4000,.25,.75];self.data['heights'][-1][1]=140
        plan,result=self.make(settings=dict(target_easy_minutes=10))
        self.assertEqual(result['nodes'][0][1:3],[.25,.75])
        self.assertAlmostEqual(result['nodes'][0][3],140/.3048,delta=.001)
        self.check_paces(plan,result)
    def test_extrapolation_has_terrain_but_no_invented_gps(self):
        self.route.update(shape='one_way',extent=2000)
        plan,result=self.make(settings=dict(target_easy_minutes=80))
        self.assertTrue(plan['extrapolated']);self.assertGreater(plan['distance'],2000)
        for distance,x,y,height in result['nodes']:
            if distance>2000:self.assertIsNone(x);self.assertIsNone(y)
            self.assertIsInstance(height,(int,float))
        self.check_paces(plan,result)
    def test_payload_bounded_and_cache_not_changed(self):
        before=copy.deepcopy(self.data)
        plan,result=self.make(settings=dict(target_easy_minutes=360))
        self.assertLess(len(result['nodes']),1800)
        self.assertLess(len(json.dumps(result)),250_000)
        self.assertEqual(before,self.data)
        for bad in (dict(distance=float('inf'),phases=[{}]),dict(distance=1,phases=[])):
            with self.assertRaises(ValueError):trace(self.route,self.data,bad)


class TraceEndpointTest(unittest.TestCase):
    def test_only_opened_card_loads_trace_offline_and_route_changes_are_rejected(self):
        fixture=test_dashboard_memory.DashboardMemoryTest();fixture.setUp()
        self.addCleanup(fixture.doCleanups);session=fixture.session
        with patch('requests.sessions.Session.request',side_effect=AssertionError('Network download')):
            dashboard=session.cached_dashboard('2026-10-21',30,fixture.settings)
            self.assertNotIn('nodes',json.dumps(dashboard))
            plan=next(p for p in dashboard['targets']['route_plans'] if p['kind']=='easy')
            result=session.workout_trace(json.dumps(plan),fixture.settings)['trace']
            self.assertGreater(len(result['nodes']),2);self.assertLess(len(json.dumps(result)),250_000)
            self.assertNotIn('trace',dashboard['targets'])
            plan['reference_id']='other'
            with self.assertRaisesRegex(InputError,'route changed'):session.workout_trace(json.dumps(plan),fixture.settings)


if __name__=='__main__':unittest.main()
