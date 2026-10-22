"""Target basis choices stay independent of chart modes and future conditions."""
from itertools import product
import json
from pathlib import Path
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'common'), str(ROOT/'android/app/src/main/python')]
from dashboard_metrics import adjusted_trial, predictions, target_basis_settings
from garmin_backend import Session


class TargetBasisTest(unittest.TestCase):
    def setUp(self):
        self.session = Session()
        self.addCleanup(self.session.cache.close)
        activities=[]
        for i,(day,pace,hr,gain,temp) in enumerate([
            ('2026-10-01',250,155,10,65), ('2026-10-03',260,165,60,70),
            ('2026-10-05',255,150,20,60), ('2026-10-07',245,170,50,85),
            ('2026-10-09',270,160,100,90),
        ],1):
            activities.append(dict(activityId=i,activityName='Short intervals',activityType='running',
                startTimeLocal=day+' 06:00:00',distance=7000,duration=2500,averageHR=140,
                elevationGain=gain*2,elevationLoss=gain))
            self.session.cache.save_detail(str(i),'interval_fit_v1',dict(distanceMeters=3000,
                durationSec=pace*3,count=3,avgHr=hr,ascentMeters=gain,descentMeters=gain/2,source='fit_laps'))
            self.session.cache.save_detail(str(i),'weather_v1',dict(temperature=temp,dewPoint=temp-10))
            self.session.cache.save_day(day,'rhr',dict(restingHeartRate=45+i%3))
        activities.append(dict(activityId=10,activityName='5K time trial',activityType='running',
            startTimeLocal='2026-10-04 06:00:00',distance=6000,duration=1600,averageHR=170,
            elevationGain=90,elevationLoss=40))
        self.session.cache.save_detail('10','effort_v1',dict(duration=1250,distance=5000,method='fit_rolling_5000m'))
        self.session.cache.save_detail('10','weather_v1',dict(temperature=75,dewPoint=65))
        self.session.cache.save_window('2026-09-11','2026-10-10',activities)
        self.settings=dict(classification_mode='native',include_recordings=False,
            include_recovery=True,include_weather=True,include_station_weather=False,
            adjust_elevation=False,adjust_temperature=False,prediction_mode='observed',
            categories={**{str(i):'short' for i in range(1,6)},'10':'trial'})
        self.health={row['startTimeLocal'][:10]:dict(resting_hr=45+row['activityId']%3)
                     for row in activities if row['activityId']!=10}

    def dashboard(self,**changes):
        return self.session.cached_dashboard('2026-10-10',30,json.dumps(dict(self.settings,**changes)))

    def test_predicted_defaults_are_adjusted_with_hr_normalization_off(self):
        result=self.dashboard()
        target=result['targets']
        self.assertTrue(target['basis_adjust_elevation'])
        self.assertTrue(target['basis_adjust_temperature'])
        self.assertEqual(target['basis_prediction_mode'],'observed')
        rows=sorted(result['runs'],key=lambda row:row['started'])
        expected=predictions(rows,dict(self.settings,adjust_elevation=True,adjust_temperature=True),self.health)[0][-1]
        self.assertAlmostEqual(target['seconds'],expected['duration'])
        self.assertEqual(target['basis_date'],'2026-10-09')
        self.assertNotEqual(target['seconds'],result['prediction_points'][-1]['duration'])

    def test_all_target_basis_combinations_use_their_own_prediction_and_calibration(self):
        values=[]
        for elevation,weather,hr in product((False,True),repeat=3):
            with self.subTest(elevation=elevation,weather=weather,hr=hr):
                mode='intensity' if hr else 'observed'
                result=self.dashboard(target_prediction_adjust_elevation=elevation,
                    target_prediction_adjust_temperature=weather,target_prediction_mode=mode)
                rows=sorted(result['runs'],key=lambda row:row['started'])
                expected=predictions(rows,dict(self.settings,adjust_elevation=elevation,
                    adjust_temperature=weather,prediction_mode=mode),self.health)[0][-1]['duration']
                self.assertAlmostEqual(result['targets']['seconds'],expected)
                self.assertEqual(result['targets']['basis_prediction_mode'],mode)
                values.append(expected)
        self.assertGreater(len(set(round(value,3) for value in values)),4)

    def test_changing_trends_preserves_target_paces_and_basis(self):
        options=dict(target_prediction_adjust_elevation=True,target_prediction_adjust_temperature=False,
                     target_prediction_mode='intensity')
        first=self.dashboard(**options)
        second=self.dashboard(**options,adjust_elevation=True,adjust_temperature=True,
                              prediction_mode='intensity',interval_pace_mode='intensity',easy_mode='intensity')
        self.assertEqual(first['targets'],second['targets'])
        self.assertNotEqual(first['prediction_points'],second['prediction_points'])

    def test_changing_target_basis_preserves_trends_and_cards(self):
        first=self.dashboard(target_prediction_adjust_elevation=False,target_prediction_adjust_temperature=False)
        second=self.dashboard(target_prediction_adjust_elevation=True,target_prediction_adjust_temperature=True,
                              target_prediction_mode='intensity')
        self.assertNotEqual(first['targets']['seconds'],second['targets']['seconds'])
        for key in ('runs','prediction_points','interval_points','run_points','trial_points'):
            self.assertEqual(first[key],second[key],key)

    def test_trial_uses_its_own_adjustments_and_ignores_estimate_hr_mode(self):
        raw=self.dashboard(target_source='latest',target_prediction_mode='intensity')
        self.assertEqual(raw['targets']['seconds'],1250)
        self.assertEqual(raw['targets']['basis_prediction_mode'],'observed')
        options=dict(target_source='latest',target_trial_adjust_elevation=True,target_trial_adjust_temperature=True)
        adjusted=self.dashboard(**options)
        trial=next(row for row in adjusted['runs'] if row['id']=='10')
        self.assertAlmostEqual(adjusted['targets']['seconds'],adjusted_trial(trial,
            dict(self.settings,adjust_elevation=True,adjust_temperature=True)))
        self.assertLess(adjusted['targets']['seconds'],1250)
        self.assertEqual(adjusted['targets'],self.dashboard(**options,prediction_mode='intensity',
            adjust_elevation=True,target_prediction_mode='intensity')['targets'])

    def test_custom_time_is_direct_and_future_conditions_are_applied_separately(self):
        options=dict(target_source='custom',target_time='20:00',target_prediction_mode='intensity',
                     target_prediction_adjust_elevation=True,target_prediction_adjust_temperature=True,
                     target_trial_adjust_elevation=True,target_trial_adjust_temperature=True)
        cool=self.dashboard(**options)['targets']
        hot=self.dashboard(**options,target_temperature=90,target_humidity=80,target_gain=150)['targets']
        self.assertEqual(cool['seconds'],1200)
        self.assertEqual(hot['seconds'],1200)
        self.assertEqual(cool['vdot'],hot['vdot'])
        self.assertFalse(cool['basis_adjust_elevation'])
        self.assertFalse(cool['basis_adjust_temperature'])
        self.assertEqual(cool['basis_prediction_mode'],'observed')
        self.assertGreater(hot['rows'][0]['pace'],cool['rows'][0]['pace'])
        self.assertEqual(hot['rows'][0]['base_pace'],cool['rows'][0]['base_pace'])

    def test_predicted_upcoming_conditions_do_not_change_the_historical_basis(self):
        cool=self.dashboard()['targets']
        hot=self.dashboard(target_temperature=90,target_humidity=80,target_gain=150)['targets']
        self.assertEqual(cool['seconds'],hot['seconds'])
        self.assertGreater(hot['rows'][0]['pace'],cool['rows'][0]['pace'])

    def test_comparison_retains_target_choices_and_basis_metadata(self):
        from comparison_contract import validate_snapshot
        settings=dict(self.settings,target_prediction_adjust_elevation=False,
                      target_prediction_adjust_temperature=True,target_prediction_mode='intensity',
                      target_trial_adjust_elevation=True,target_trial_adjust_temperature=False)
        snapshot=self.session.comparison('2026-10-10',30,json.dumps(settings))['comparison']
        validate_snapshot(snapshot)
        for key in settings:
            if key.startswith('target_'):self.assertEqual(snapshot['selection']['settings'][key],settings[key])
        self.assertFalse(snapshot['android']['targets']['basis_adjust_elevation'])
        self.assertTrue(snapshot['android']['targets']['basis_adjust_temperature'])
        self.assertEqual(snapshot['android']['targets']['basis_prediction_mode'],'intensity')

    def test_missing_independent_settings_do_not_fall_back_to_chart_flags(self):
        first=target_basis_settings(dict(adjust_elevation=False,adjust_temperature=False,prediction_mode='observed'))
        second=target_basis_settings(dict(adjust_elevation=True,adjust_temperature=True,prediction_mode='intensity'))
        for key in ('adjust_elevation','adjust_temperature','prediction_mode'):
            self.assertEqual(first[key],second[key])

    @unittest.skipUnless(shutil.which('node'),'Requires the actual web JavaScript')
    def test_independent_target_choices_match_web_math_for_all_sources(self):
        sys.path.insert(0,str(ROOT/'android/scripts'))
        from compare_dashboard import compare
        for source in ('predicted','latest','custom'):
            with self.subTest(source=source):
                settings=dict(self.settings,classification_mode='web',full_history=True,target_source=source,target_time='20:00',
                    target_prediction_adjust_elevation=True,target_prediction_adjust_temperature=False,
                    target_prediction_mode='intensity',target_trial_adjust_elevation=False,
                    target_trial_adjust_temperature=True,target_temperature=85,target_humidity=60)
                snapshot=self.session.comparison('2026-10-10',30,json.dumps(settings))['comparison']
                report=compare(snapshot,matrix=True)
                self.assertEqual(report['counts']['different'],0,report['differences'])


if __name__=='__main__':
    unittest.main()
