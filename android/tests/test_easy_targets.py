"""Empirical 128 bpm targets: separate surfaces, conditions, and sparse history."""
from datetime import date, timedelta
import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from dashboard_metrics import adjusted_pace, easy_targets, upcoming_pace
from garmin_backend import Session

TODAY = '2026-10-21'


def runs(surface='road',base=360,hrs=(120,124,128,132,136,126,130)):
    result=[]
    for i,hr in enumerate(hrs):
        day=(date.fromisoformat(TODAY)-timedelta(days=i*3)).isoformat()
        pace=base*math.exp(-.012*(hr-128))
        result.append(dict(id=str(i),date=day,started=day+' 06:00:00',category='easy',
                           activity_type='running' if surface=='road' else 'trail_running',
                           pace=pace,average_hr=hr,distance=6000,duration=pace*6,
                           elevation_gain=0,elevation_loss=0,weather={'temperatureF':45}))
    return result


class EasyTargetsTest(unittest.TestCase):
    def estimate(self,rows=None,settings=None):
        return easy_targets(runs() if rows is None else rows,settings or {},TODAY)

    def test_recovers_known_relationship_and_separates_surfaces(self):
        road,trail=self.estimate(runs()+runs('trail',450))
        self.assertAlmostEqual(road['pace'],360)
        self.assertAlmostEqual(trail['pace'],450)
        for result in (road,trail):
            self.assertEqual(result['target_hr'],128)
            self.assertEqual(result['method'],'hr_fit')
            self.assertEqual(result['samples'],7)
            self.assertLess(result['pace_low'],result['pace'])
            self.assertGreater(result['pace_high'],result['pace'])
        self.assertIn('error',self.estimate()[1])

    def test_future_conditions_apply_once_without_changing_fit(self):
        cool=self.estimate()[0]
        settings=dict(target_temperature=90,target_humidity=80,target_gain=300,target_loss=100)
        warm=self.estimate(settings=settings)[0]
        self.assertEqual(warm['base_pace'],cool['base_pace'])
        self.assertAlmostEqual(warm['pace'],upcoming_pace(360,6000,settings))
        self.assertGreater(warm['pace'],cool['pace'])
        downhill=self.estimate(settings=dict(target_loss=300))[0]
        self.assertLess(downhill['pace'],cool['pace'])

    def test_historical_weather_and_elevation_corrected_before_hr_fit(self):
        rows=runs()
        for row in rows:
            neutral=row['pace']
            row.update(elevation_gain=120,elevation_loss=100,weather=dict(temperatureF=90,humidity=70))
            low,high=neutral,neutral+200
            for _ in range(70):
                candidate=(low+high)/2
                if adjusted_pace(row,candidate,dict(adjust_elevation=True,adjust_temperature=True))<neutral:
                    low=candidate
                else:high=candidate
            row['pace']=(low+high)/2
        self.assertAlmostEqual(self.estimate(rows)[0]['pace'],360)

    def test_ignores_chart_and_5k_basis_controls(self):
        self.assertEqual(self.estimate(),self.estimate(settings=dict(adjust_elevation=True,
            adjust_temperature=True,prediction_mode='intensity',target_source='custom',target_time='15:00',
            target_prediction_adjust_elevation=False,target_prediction_adjust_temperature=False)))

    def test_outlier_has_limited_influence(self):
        rows=runs()
        rows[2]['pace']*=2
        self.assertAlmostEqual(self.estimate(rows)[0]['pace'],360)

    def test_nearby_consistent_hr_uses_local_observations(self):
        road=self.estimate(runs(hrs=(127,128,129,128,128)))[0]
        self.assertEqual(road['method'],'nearby_runs')
        self.assertAlmostEqual(road['pace'],360)

    def test_missing_hr_short_sessions_and_other_activity_types_excluded(self):
        for field,value in [('average_hr',None),('pace',float('nan')),('duration',300),
                            ('distance',0),('category','short'),('activity_type','treadmill_running'),
                            ('activity_type','virtual_run'),('average_hr',240)]:
            with self.subTest(field=field,value=value):
                rows=runs()
                for row in rows:row[field]=value
                self.assertIn('error',self.estimate(rows)[0])

    def test_stale_and_future_runs_do_not_support_current_prediction(self):
        rows=runs()
        for row in rows:row['date']='2026-01-01'
        self.assertEqual(self.estimate(rows)[0]['samples'],0)
        for row in rows:row['date']='2026-12-01'
        self.assertEqual(self.estimate(rows)[0]['samples'],0)

    def test_requires_sufficient_history_near_target_hr(self):
        self.assertIn('error',self.estimate(runs()[:4])[0])
        self.assertIn('error',self.estimate(runs(hrs=(145,148,152,156,160)))[0])
        self.assertIn('error',self.estimate(runs(hrs=(140,140,140,140,140)))[0])

    def test_rejects_positive_hr_pace_relationship_away_from_target(self):
        rows=runs(hrs=(130,134,138,142,146))
        for row in rows:row['pace']=360*math.exp(.01*(row['average_hr']-128))
        self.assertIn('error',self.estimate(rows)[0])

    def test_only_latest_24_runs_are_used(self):
        rows=runs(hrs=tuple(120+i%17 for i in range(30)))
        self.assertEqual(self.estimate(rows)[0]['samples'],24)

    def test_easy_predictions_available_without_interval_or_trial_history_and_exported(self):
        session=Session()
        self.addCleanup(session.cache.close)
        activities=[]
        for index,row in enumerate(runs()+runs('trail',450)):
            activities.append(dict(activityId=index+1,activityName='Easy run',
                activityType=row['activity_type'],startTimeLocal=row['started'],
                distance=row['distance'],duration=row['duration'],averageHR=row['average_hr'],
                elevationGain=0,elevationLoss=0))
        session.cache.save_window('2026-09-21',TODAY,activities)
        settings=dict(classification_mode='native',include_recordings=False,
            include_recovery=False,include_weather=False,include_station_weather=False,
            categories={str(index+1):'easy' for index in range(len(activities))})
        result=session.cached_dashboard(TODAY,30,json.dumps(settings))
        self.assertIn('error',result['targets'])
        self.assertAlmostEqual(result['targets']['easy'][0]['pace'],360)
        self.assertAlmostEqual(result['targets']['easy'][1]['pace'],450)
        from comparison_contract import validate_snapshot
        snapshot=session.comparison(TODAY,30,json.dumps(settings))['comparison']
        validate_snapshot(snapshot)
        self.assertEqual(snapshot['android']['targets']['easy'],result['targets']['easy'])


if __name__=='__main__':unittest.main()
