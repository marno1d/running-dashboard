import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/src/main/python'))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"common"))
from run_cache import RunCache
from garmin_backend import Session
from fit_fixture import recording


def run(identity,day,title='Short intervals',duration=2000):
    return dict(activityId=identity,activityName=title,startTimeLocal=day+' 06:00:00',distance=6000,duration=duration,averageHR=125)


def client(rows):
    fake=Mock();fake.connectapi.side_effect=[rows,[]]
    fake.get_activity_splits.return_value={'lapDTOs':[dict(intensityType='ACTIVE',distance=1000,duration=200)]}
    fake.download_activity.return_value=recording([(0,0),(5000,1100)])
    return fake


class RunCacheTest(unittest.TestCase):
    def test_repeat_refresh_only_checks_recent_and_reuses_laps_and_5k(self):
        session=Session();self.addCleanup(session.cache.close)
        rows=[run(1,'2026-10-06'),run(2,'2026-10-05','5K TT')]
        session.client=client(rows);session.dashboard('2026-10-06',90,'{}',True)
        session.client.connectapi.side_effect=[rows,[]]
        session.dashboard('2026-10-06',90,'{}',True)
        self.assertEqual(session.client.get_activity_splits.call_count,1)
        self.assertEqual(session.client.download_activity.call_count,1)
        self.assertEqual(session.client.connectapi.call_args_list[2].kwargs['params']['startDate'],'2026-10-04')
        self.assertEqual(len(session.activities),2)

    def test_restart_reads_persistent_data_with_no_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'runs.sqlite'
            first=Session(path);first.client=client([run(1,'2026-10-06'),run(2,'2026-10-05','5K TT')])
            result=first.dashboard('2026-10-06',90,'{}',True)
            first.cache.close()
            second=Session(path);self.addCleanup(second.cache.close);second.client=Mock()
            saved=second.dashboard('2026-10-06',90,'{}')
            self.assertEqual(saved['interval_points'],result['interval_points'])
            self.assertEqual(saved['trial_points'],result['trial_points'])
            second.client.connectapi.assert_not_called()
            second.client.get_activity_splits.assert_not_called()
            second.client.download_activity.assert_not_called()

    def test_new_activity_downloads_only_its_laps(self):
        session=Session();self.addCleanup(session.cache.close)
        old=run(1,'2026-10-05');session.client=client([old])
        session.dashboard('2026-10-06',90,'{}',True)
        session.client.connectapi.side_effect=[[run(2,'2026-10-07'),old],[]]
        result=session.dashboard('2026-10-07',90,'{}',True)
        self.assertEqual(session.client.get_activity_splits.call_count,2)
        self.assertEqual(session.client.get_activity_splits.call_args.args,('2',))
        self.assertEqual(len(result['interval_points']),2)

    def test_updated_run_invalidates_only_its_download(self):
        session=Session();self.addCleanup(session.cache.close)
        first=run(1,'2026-10-06');second=run(2,'2026-10-05','5K TT')
        session.client=client([first,second]);session.dashboard('2026-10-06',90,'{}',True)
        session.client.connectapi.side_effect=[[run(1,'2026-10-06',duration=2100),second],[]]
        session.dashboard('2026-10-06',90,'{}',True)
        self.assertEqual(session.client.get_activity_splits.call_count,2)
        self.assertEqual(session.client.download_activity.call_count,1)

    def test_extending_range_downloads_only_missing_dates(self):
        session=Session();self.addCleanup(session.cache.close);session.client=client([run(1,'2026-10-06')])
        session.dashboard('2026-10-06',7,'{}')
        session.client.connectapi.side_effect=[[run(2,'2026-09-20')],[]]
        result=session.dashboard('2026-10-06',30,'{}')
        params=session.client.connectapi.call_args_list[2].kwargs['params']
        self.assertEqual((params['startDate'],params['endDate']),('2026-09-07','2026-09-29'))
        self.assertEqual(len(result['runs']),2)
        self.assertEqual(session.client.get_activity_splits.call_count,2)
        session.dashboard('2026-10-06',7,'{}')
        self.assertEqual(session.client.connectapi.call_count,4)

    def test_partial_listing_failure_leaves_cache_and_coverage_intact(self):
        session=Session();self.addCleanup(session.cache.close);session.client=client([run(1,'2026-10-06')])
        session.dashboard('2026-10-06',90,'{}')
        session.client.connectapi.side_effect=[[run(2,'2026-10-06')],RuntimeError('offline')]
        with self.assertRaises(RuntimeError):session.dashboard('2026-10-06',90,'{}',True)
        self.assertEqual([r['id'] for r in session.dashboard('2026-10-06',90,'{}')['runs']],['1'])
        self.assertEqual(session.client.get_activity_splits.call_count,1)

    def test_deleted_run_is_removed_from_successfully_checked_window(self):
        session=Session();self.addCleanup(session.cache.close);session.client=client([run(1,'2026-10-06')])
        session.dashboard('2026-10-06',90,'{}')
        session.client.connectapi.side_effect=[[]]
        self.assertEqual(session.dashboard('2026-10-06',90,'{}',True)['runs'],[])
        self.assertEqual(session.cache.detail('1','laps'),(False,None))

    def test_signout_clears_persistent_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'runs.sqlite'
            session=Session(path);session.client=client([run(1,'2026-10-06')])
            session.dashboard('2026-10-06',90,'{}');session.logout();session.cache.close()
            saved=RunCache(path);self.addCleanup(saved.close)
            self.assertEqual(saved.activities('2026-01-01','2026-12-31'),[])
            self.assertEqual(saved.detail('1','laps'),(False,None))
            self.assertEqual(saved.missing('2026-10-01','2026-10-06'),[('2026-10-01','2026-10-06')])

    def test_local_storage_excludes_gps_and_tokens(self):
        cache=RunCache();self.addCleanup(cache.close)
        row=dict(run(1,'2026-10-06'),startLatitude=40,endLongitude=-111,token='SECRET')
        cache.save_window('2026-10-01','2026-10-06',[row])
        text=json.dumps(cache.activities('2026-10-01','2026-10-06'))
        self.assertNotIn('Latitude',text);self.assertNotIn('Longitude',text);self.assertNotIn('SECRET',text)

    def test_null_effort_cached_and_failed_download_retried(self):
        session=Session();self.addCleanup(session.cache.close);session.client=Mock()
        session.client.download_activity.return_value=recording([(0,0),(4900,1000)])
        self.assertIsNone(session._effort('1'));self.assertIsNone(session._effort('1'))
        self.assertEqual(session.client.download_activity.call_count,1)
        session.client.download_activity.side_effect=[RuntimeError('offline'),recording([(0,0),(5000,1100)])]
        with self.assertRaises(RuntimeError):session._effort('2')
        self.assertEqual(session._effort('2')['duration'],1100)
