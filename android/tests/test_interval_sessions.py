"""Interval charts always use one weighted work average per session, including old settings."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'android/app/src/main/python')]
from garmin_backend import Session


class IntervalSessionsTest(unittest.TestCase):
    def setUp(self):
        self.session = Session()
        self.addCleanup(self.session.cache.close)
        self.session.cache.save_window('2026-09-21', '2026-10-20', [
            dict(activityId=1, activityName='Short intervals', activityType='running',
                 startTimeLocal='2026-10-19 06:00:00', distance=6000, duration=2400, averageHR=140),
            dict(activityId=2, activityName='Medium intervals', activityType='running',
                 startTimeLocal='2026-10-18 06:00:00', distance=7000, duration=2500, averageHR=145,
                 splitSummaries=[dict(splitType='INTERVAL_ACTIVE', distance=2000, duration=500, noOfSplits=5)]),
        ])
        self.session.cache.save_detail('1', 'laps', dict(lapDTOs=[
            dict(intensityType='ACTIVE', distance=1000, duration=300, averageHR=160),
            dict(intensityType='REST', distance=100, duration=80, averageHR=100),
            dict(intensityType='ACTIVE', distance=500, duration=180, averageHR=170),
            dict(intensityType='COOLDOWN', distance=1000, duration=500, averageHR=120),
        ]))
        self.session.cache.save_detail('2', 'interval_fit_v1', dict(distanceMeters=2000,
            durationSec=500, count=5, avgHr=155, source='fit_laps'))
        self.settings = dict(include_recovery=False, include_weather=False,
            include_station_weather=False, include_recordings=False,
            categories={'1': 'short', '2': 'medium'})

    def dashboard(self, **changes):
        return self.session.cached_dashboard('2026-10-20', 30, json.dumps(dict(self.settings, **changes)))

    def test_default_and_legacy_modes_emit_one_weighted_average_per_session(self):
        for changes in ({}, dict(interval_mode='rep'), dict(interval_mode='session')):
            with self.subTest(changes=changes):
                result = self.dashboard(**changes)
                points = {p['id']: p for p in result['interval_points']}
                self.assertEqual(len(result['interval_points']), 2)
                self.assertEqual(set(points), {'1', '2'})
                self.assertEqual((points['1']['distance'], points['1']['duration']), (1500, 480))
                self.assertEqual(points['1']['pace'], 320)  # Total work time / total work distance.
                self.assertEqual(points['1']['reps'], 2)
                self.assertAlmostEqual(points['1']['work_hr'], 163.75)
                self.assertEqual(points['2']['pace'], 250)
                self.assertEqual(points['2']['reps'], 5)
                self.assertTrue(all(p['lap'] == 0 for p in points.values()))

    def test_lap_corrections_change_the_session_average(self):
        result = self.dashboard(interval_mode='rep', laps={'1': [0]})
        point = next(p for p in result['interval_points'] if p['id'] == '1')
        self.assertEqual((point['pace'], point['distance'], point['duration'], point['reps'], point['lap']),
                         (300, 1000, 300, 1, 0))

    def test_adjusted_and_hr_normalized_charts_ignore_legacy_rep_setting(self):
        for mode in ('observed', 'intensity'):
            options = dict(interval_pace_mode=mode, adjust_elevation=True, adjust_temperature=True)
            expected = self.dashboard(interval_mode='session', **options)
            actual = self.dashboard(interval_mode='rep', **options)
            for key in ('runs', 'interval_points', 'prediction_points', 'targets'):
                self.assertEqual(actual[key], expected[key])

    def test_web_classification_also_emits_session_averages(self):
        result = self.dashboard(interval_mode='rep', classification_mode='web')
        points = {p['id']: p for p in result['interval_points']}
        self.assertEqual(len(result['interval_points']), 2)
        self.assertAlmostEqual(points['1']['pace'], round(320 * 1.609344, 1) / 1.609344)
        self.assertTrue(all(p['lap'] == 0 for p in points.values()))

    def test_sync_reuses_summary_without_downloading_rep_laps(self):
        self.session.client = Mock()
        result = self.session.dashboard('2026-10-20', 30, json.dumps(dict(self.settings, interval_mode='rep')))
        self.assertEqual(len(result['interval_points']), 2)
        self.session.client.get_activity_splits.assert_not_called()
        self.session.client.download_activity.assert_not_called()
        self.session.client.connectapi.assert_not_called()

    def test_comparison_exports_effective_session_mode(self):
        result = self.session.comparison('2026-10-20', 30, json.dumps(dict(self.settings, interval_mode='rep')))['comparison']
        self.assertEqual(result['selection']['settings']['interval_mode'], 'session')
        self.assertEqual(len(result['android']['interval_points']), 2)
        self.assertTrue(all(p['lap'] == 0 for p in result['android']['interval_points']))


if __name__ == '__main__':
    unittest.main()
