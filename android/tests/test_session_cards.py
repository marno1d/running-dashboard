"""Whole-session and work paces stay separate when card adjustments change."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'android/app/src/main/python')]
from garmin_backend import Session


class SessionCardPaceTest(unittest.TestCase):
    def setUp(self):
        self.session = Session()
        self.addCleanup(self.session.cache.close)
        self.raw = [
            dict(activityId=1, activityName='Short intervals', activityType='running',
                 startTimeLocal='2026-10-19 06:00:00', distance=10000, duration=3600,
                 averageHR=140, elevationGain=200, elevationLoss=100,
                 splitSummaries=[dict(splitType='INTERVAL_ACTIVE', distance=3000, duration=720, noOfSplits=3)]),
            dict(activityId=2, activityName='5K time trial', activityType='running',
                 startTimeLocal='2026-10-18 06:00:00', distance=8000, duration=2800,
                 averageHR=145, elevationGain=80, elevationLoss=40),
            dict(activityId=3, activityName='Easy run', activityType='running',
                 startTimeLocal='2026-10-17 06:00:00', distance=6000, duration=1800,
                 averageHR=125),
            dict(activityId=4, activityName='Cycling', activityType='cycling',
                 startTimeLocal='2026-10-16 06:00:00', distance=10000, duration=3600,
                 averageHR=130, elevationGain=200, elevationLoss=100),
            dict(activityId=5, activityName='Strength', activityType='strength_training',
                 startTimeLocal='2026-10-15 06:00:00', duration=1800),
        ]
        self.session.cache.save_window('2026-10-01', '2026-10-20', self.raw)
        self.session.cache.save_detail('1', 'interval_fit_v1', dict(distanceMeters=3000, durationSec=720,
            count=3, avgHr=165, ascentMeters=90, descentMeters=30, source='fit_laps'))
        self.session.cache.save_detail('2', 'effort_v1', dict(duration=1200, distance=5000, method='fit_rolling_5000m'))
        for identity in ('1', '2', '4'):
            self.session.cache.save_detail(identity, 'weather_v1', dict(temperature=90, dewPoint=70))
        self.settings = dict(interval_mode='session', include_recovery=False, include_weather=True,
            include_station_weather=False, include_recordings=False,
            categories={'1': 'short', '2': 'trial', '3': 'easy', '4': 'cross_train', '5': 'strength'})

    def rows(self, **changes):
        settings = dict(self.settings, **changes)
        result = self.session.cached_dashboard('2026-10-20', 30, json.dumps(settings))
        return {r['id']: r for r in result['runs']}

    def test_recorded_card_paces_use_whole_activity_and_work_independently(self):
        rows = self.rows()
        interval, trial = rows['1'], rows['2']
        self.assertEqual(interval['display_overall_pace'], 360)
        self.assertEqual(interval['display_work_pace'], 240)
        self.assertEqual(interval['average_hr'], 140)
        self.assertEqual(interval['work_hr'], 165)
        self.assertEqual(trial['display_overall_pace'], 350)
        self.assertEqual(trial['best_5k']['duration'], 1200)
        self.assertIsNone(trial['display_work_pace'])
        self.assertIsNone(rows['3']['display_work_pace'])

    def test_both_and_individual_adjustments_use_the_correct_distance_and_elevation(self):
        recorded = self.rows()
        for elevation, weather in ((True, True), (True, False), (False, True)):
            with self.subTest(elevation=elevation, weather=weather):
                rows = self.rows(adjust_elevation=elevation, adjust_temperature=weather)
                work = rows['1']
                # Whole run: 27 sec/km elevation reduction; work: 34 sec/km.
                # Heat/dew point reduce their recorded paces by 4% independently.
                expected = {(True, True): (318.6, 196.4), (True, False): (333, 206),
                            (False, True): (345.6, 230.4)}[(elevation, weather)]
                self.assertAlmostEqual(work['display_overall_pace'], expected[0])
                self.assertAlmostEqual(work['display_work_pace'], expected[1])
                self.assertLess(work['display_overall_pace'], work['pace'])
                self.assertLess(work['display_work_pace'], work['work_pace'])
                for identity in ('1', '2', '3', '4', '5'):
                    for key in ('pace', 'work_pace', 'distance', 'duration', 'average_hr', 'work_hr',
                                'elevation_gain', 'elevation_loss', 'weather', 'best_5k'):
                        self.assertEqual(rows[identity].get(key), recorded[identity].get(key), key)
                # Non-running sessions keep their recorded pace, even with hot weather and hills.
                self.assertEqual(rows['4']['display_overall_pace'], recorded['4']['pace'])
                # Missing conditions cannot invent a pace adjustment or missing work data.
                self.assertEqual(rows['3']['display_overall_pace'], recorded['3']['pace'])
                self.assertIsNone(rows['5']['display_overall_pace'])
                self.assertIsNone(rows['5']['display_work_pace'])
        self.assertEqual(self.rows()['1']['display_overall_pace'], recorded['1']['pace'])
        self.assertEqual(self.rows()['1']['display_work_pace'], recorded['1']['work_pace'])
        self.assertEqual(self.session.cache.activities('2026-10-19', '2026-10-19')[0]['duration'], 3600)

    def test_hr_normalized_trend_modes_do_not_replace_condition_adjusted_card_paces(self):
        plain = self.rows(adjust_elevation=True, adjust_temperature=True)
        normalized = self.rows(adjust_elevation=True, adjust_temperature=True,
            easy_mode='intensity', interval_pace_mode='intensity', prediction_mode='intensity')
        for identity in plain:
            for key in ('display_overall_pace', 'display_work_pace'):
                self.assertEqual(plain[identity][key], normalized[identity][key])

    def test_card_paces_are_retained_by_saved_comparison_export(self):
        from comparison_contract import validate_snapshot
        result = self.session.comparison('2026-10-20', 30, json.dumps(self.settings))['comparison']
        validate_snapshot(result)
        interval = next(r for r in result['android']['runs'] if r['id'] == '1')
        self.assertEqual(interval['display_overall_pace'], 360)
        self.assertEqual(interval['display_work_pace'], 240)
