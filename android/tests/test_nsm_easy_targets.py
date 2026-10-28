"""70%-speed easy targets keep historical trail calibration independent."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from dashboard_metrics import adjusted_pace,nsm_easy_targets,nsm_easy_target,targets,upcoming_pace,target_surface,target_workout
from route_workouts import apply_manual_plans
from test_easy_targets import runs,TODAY

BASE_PACE=1080/5/.70


class NsmEasyTargetsTest(unittest.TestCase):
    def estimates(self,rows=None,settings=None):
        settings=dict(target_source='custom',target_time='18:00',target_gain_per_mile=0,
                      target_loss_per_mile=0,**(settings or {}))
        target=targets([],[],settings)
        target['easy']=nsm_easy_targets(runs()+runs('trail',450) if rows is None else rows,settings,TODAY,target)
        return target,settings

    def test_speed_fraction_is_exact_smooth_and_not_limited_to_the_table(self):
        for time in (840,919,920,1020,1080,1090,1200,1500,1800,1801,2100):
            with self.subTest(time=time):
                pace=nsm_easy_target(time,{})['base_pace']
                self.assertAlmostEqual(1000/pace,(5000/time)*.70)
        self.assertEqual(round(nsm_easy_target(1080,{})['base_pace']*1.609344),497)
        self.assertEqual(round(nsm_easy_target(1200,{})['base_pace']*1.609344),552)
        self.assertAlmostEqual(nsm_easy_target(1090,{})['base_pace']-BASE_PACE,10/3.5)
        for invalid in (None,0,-1,float('nan'),float('inf')):
            self.assertIn('error',nsm_easy_target(invalid,{}))

    def test_all_basis_sources_drive_the_same_speed_fraction_without_a_new_hr_target(self):
        trial=dict(date=TODAY,category='trial',distance=5000,best_5k=dict(duration=1080))
        for source in ('custom','latest','predicted'):
            settings=dict(target_source=source,target_time='18:00',
                          target_trial_adjust_elevation=False,target_trial_adjust_temperature=False)
            target=targets([trial],[dict(duration=1080,date=TODAY)],settings)
            road,trail=nsm_easy_targets([],settings,TODAY,target)
            self.assertAlmostEqual(road['base_pace'],BASE_PACE)
            self.assertNotIn('target_hr',road)
            self.assertEqual(trail['surface_factor'],1)
            self.assertIn('insufficient history',trail['surface_note'])

    def test_history_changes_only_trail_ratio_not_the_absolute_road_pace(self):
        target,_=self.estimates()
        road,trail=target['easy']
        self.assertAlmostEqual(road['base_pace'],BASE_PACE)
        self.assertAlmostEqual(trail['surface_factor'],1.25)
        self.assertAlmostEqual(trail['base_pace'],BASE_PACE*1.25)
        faster,_=self.estimates(runs(base=288)+runs('trail',360))
        self.assertEqual(target['easy'],faster['easy'])

    def test_historical_hills_and_heat_are_removed_before_estimating_trail_ratio(self):
        rows=runs()+runs('trail',450)
        for row in rows:
            if row['activity_type']!='trail_running':continue
            neutral=row['pace']
            row.update(elevation_gain=120,elevation_loss=100,weather=dict(temperatureF=90,humidity=70))
            low,high=neutral,neutral+300
            for _ in range(70):
                pace=(low+high)/2
                if adjusted_pace(row,pace,dict(adjust_elevation=True,adjust_temperature=True))<neutral:low=pace
                else:high=pace
            row['pace']=(low+high)/2
        target,settings=self.estimates(rows,dict(target_temperature=90,target_humidity=80))
        trail=target['easy'][1]
        self.assertAlmostEqual(trail['surface_factor'],1.25)
        self.assertAlmostEqual(trail['pace'],upcoming_pace(BASE_PACE*1.25,5000,settings))

    def test_missing_or_faster_trail_history_uses_explicit_terrain_only_fallback(self):
        for rows in ([],runs(),runs()+runs('trail',300)):
            target,_=self.estimates(rows)
            road,trail=target['easy']
            self.assertEqual(road['base_pace'],trail['base_pace'])
            self.assertIn('Terrain only',trail['surface_note'])
        target=dict(error='No 5K trial available.')
        self.assertTrue(all(row.get('error') for row in nsm_easy_targets(runs(),{},TODAY,target)))

    def test_workout_splits_and_interval_warmup_use_surface_pace_once(self):
        target,settings=self.estimates(settings=dict(target_temperature=90,target_humidity=80))
        apply_manual_plans(target,settings)
        plans={(p['kind'],p['surface']):p for p in target['route_plans']}
        for kind,minutes in [('easy',45),('easy_long',80)]:
            road,trail=plans[kind,'road'],plans[kind,'trail']
            self.assertAlmostEqual(road['duration'],minutes*60)
            self.assertAlmostEqual(trail['duration'],minutes*60)
            self.assertAlmostEqual(trail['pace']/road['pace'],1.25)
            self.assertAlmostEqual(sum(s['duration'] for s in trail['splits']),minutes*60)
        warmup=plans['short','road']['phases'][0]
        self.assertAlmostEqual(warmup['base_pace'],BASE_PACE)
        self.assertAlmostEqual(warmup['pace'],BASE_PACE/.96)

    def test_route_surface_overrides_manual_choice_and_road_is_the_default(self):
        self.assertEqual(target_surface({}),'road')
        self.assertEqual(target_surface(dict(target_surface='trail')),'trail')
        self.assertEqual(target_surface(dict(target_surface='unknown')),'road')
        self.assertEqual(target_surface(dict(target_surface='road',target_route_id='route',target_route_surface='trail')),'trail')
        self.assertEqual(target_surface(dict(target_surface='trail',target_route_id='route',target_route_surface='road')),'road')
        self.assertEqual(target_surface(dict(target_surface='trail',target_route_id='',target_route_surface='road')),'trail')

    def test_manual_trail_selection_controls_summary_and_interval_easy_phases(self):
        target,settings=self.estimates(settings=dict(target_surface='trail'))
        summary=target_workout(target,settings)
        self.assertAlmostEqual(summary['distance'],45*60/(BASE_PACE*1.25)*1000)
        apply_manual_plans(target,settings)
        short=next(p for p in target['route_plans'] if p['kind']=='short')
        self.assertEqual(short['surface'],'trail')
        self.assertAlmostEqual(short['phases'][0]['base_pace'],BASE_PACE*1.25)
        self.assertAlmostEqual(short['phases'][-1]['base_pace'],BASE_PACE*1.25)
        self.assertAlmostEqual(short['work_pace'],target['rows'][0]['base_pace'])


if __name__=='__main__':unittest.main()
