"""Recovery batching preserves daily values, cache boundaries and pause behavior."""
from datetime import date, timedelta
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from dashboard_sync import sync_extras
from garminconnect.exceptions import GarminConnectTooManyRequestsError, GarminConnectNotFoundError, GarminConnectConnectionError
from run_cache import RunCache
from sync_job import SyncJob, SyncPaused


class RecoverySyncTest(unittest.TestCase):
    def setUp(self):
        self.cache = RunCache()
        self.addCleanup(self.cache.close)
        self.end = date.today()
        self.start = self.end-timedelta(days=55)
        self.stamps = [(self.start+timedelta(days=i)).isoformat() for i in range(56)]
        self.client = Mock()
        self.client.get_sleep_data.return_value = {'dailySleepDTO':{'sleepTimeSeconds':28800,'sleepScore':82}}
        self.client.get_rhr_day.return_value = {'restingHeartRate':45}
        self.client.get_hrv_data.return_value = {'hrvSummary':{'lastNightAvg':60}}
        self.client.get_sleep_daily.side_effect = lambda first,last: [
            dict(calendarDate=s,values=dict(totalSleepTimeInSeconds=28800,sleepScore=82))
            for s in self.stamps if first<=s<=last]
        self.client.get_rhr_daily.side_effect = lambda first,last: [
            dict(calendarDate=s,value=45) for s in self.stamps if first<=s<=last]
        self.client.get_hrv_data_range.side_effect = lambda first,last: dict(hrvSummaries=[
            dict(calendarDate=s,lastNightAvg=60) for s in self.stamps if first<=s<=last])
        self.result = dict(start=self.start.isoformat(),end=self.end.isoformat(),runs=[])
        self.settings = dict(include_recovery=True)
        sleeper = patch('dashboard_sync.time.sleep')
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def sync(self, refresh=False, job=None):
        return sync_extras(self.client,self.cache,self.result,self.settings,refresh,Mock(),job=job)

    def test_56_days_use_six_requests_with_identical_values_to_168_daily_requests(self):
        bulk = self.sync()[0]
        self.assertEqual(len(bulk),56)
        for method in ('get_sleep_daily','get_rhr_daily','get_hrv_data_range'):
            self.assertEqual(getattr(self.client,method).call_count,2)
        for method in ('get_sleep_data','get_rhr_day','get_hrv_data'):
            getattr(self.client,method).assert_not_called()
        self.cache.clear()
        self.client.get_sleep_daily = None
        self.client.get_rhr_daily = None
        self.client.get_hrv_data_range = None
        daily = self.sync()[0]
        self.assertEqual(bulk,daily)
        for method in ('get_sleep_data','get_rhr_day','get_hrv_data'):
            self.assertEqual(getattr(self.client,method).call_count,56)

    def test_saved_days_are_skipped_and_refresh_only_batches_recent_three_days(self):
        self.sync()
        self.client.reset_mock()
        self.sync()
        self.assertEqual(self.client.mock_calls,[])
        self.sync(refresh=True)
        for method in ('get_sleep_daily','get_rhr_daily','get_hrv_data_range'):
            getattr(self.client,method).assert_called_once_with(
                (self.end-timedelta(days=2)).isoformat(),self.end.isoformat())
        self.client.get_sleep_data.assert_not_called()

    def test_partial_range_uses_daily_fallback_only_for_the_missing_metric(self):
        missing = self.stamps[-4]
        self.client.get_rhr_daily.side_effect = lambda first,last: [
            dict(calendarDate=s,value=45) for s in self.stamps if first<=s<=last and s!=missing]
        health,_,warnings = self.sync()
        self.client.get_rhr_day.assert_called_once_with(missing)
        self.client.get_sleep_data.assert_not_called()
        self.client.get_hrv_data.assert_not_called()
        self.assertEqual(health[missing]['resting_hr'],45)
        self.assertEqual(warnings,[])

    def test_bad_range_dates_fall_back_without_committing_any_batch_rows(self):
        self.client.get_sleep_daily.side_effect = lambda first,last: [
            dict(calendarDate=last,values=dict(totalSleepTimeInSeconds=3600)),
            dict(calendarDate='private invalid date',values=dict(totalSleepTimeInSeconds=3600))]
        health,_,warnings = self.sync()
        self.client.get_sleep_daily.assert_called_once()
        self.assertEqual(self.client.get_sleep_data.call_count,56)
        self.assertTrue(all(day['sleep_hours']==8 for day in health.values()))
        self.assertEqual(warnings,[])

    def test_empty_ranges_use_daily_readers_and_cache_confirmed_empty_days(self):
        self.client.get_sleep_daily.side_effect = lambda first,last: []
        self.client.get_sleep_data.return_value = None
        health,_,warnings = self.sync()
        self.assertTrue(all(day['sleep_hours'] is None for day in health.values()))
        self.assertEqual(self.client.get_sleep_data.call_count,56)
        self.client.reset_mock()
        self.sync()
        self.assertEqual(self.client.mock_calls,[])
        self.assertEqual(warnings,[])

    def test_range_does_not_overwrite_a_saved_day_between_two_missing_dates(self):
        saved = self.stamps[-2]
        self.cache.save_day(saved,'rhr',dict(restingHeartRate=47))
        health,_,_ = self.sync()
        self.assertEqual(health[saved]['resting_hr'],47)

    def test_rate_limit_stops_daily_fallback_and_other_garmin_downloads(self):
        self.client.get_sleep_daily.side_effect = GarminConnectTooManyRequestsError('private response')
        _,_,warnings = self.sync()
        self.assertTrue(self.result['optional_downloads_paused'])
        self.client.get_rhr_daily.assert_not_called()
        self.client.get_sleep_data.assert_not_called()
        self.assertNotIn('private response',str(warnings))

    def test_unsupported_range_uses_daily_fallback_without_connection_retries(self):
        self.client.get_sleep_daily.side_effect = GarminConnectNotFoundError('private response')
        job = SyncJob()
        job.wait = Mock()
        health,_,warnings = self.sync(job=job)
        self.client.get_sleep_daily.assert_called_once()
        self.assertEqual(self.client.get_sleep_data.call_count,56)
        self.assertTrue(all(day['sleep_hours']==8 for day in health.values()))
        job.wait.assert_not_called()
        self.assertEqual(warnings,[])

    def test_failed_connection_retries_then_pauses_without_requesting_other_metrics(self):
        self.client.get_sleep_daily.side_effect = GarminConnectConnectionError('private connection')
        job = SyncJob()
        job.wait = Mock()
        _,_,warnings = self.sync(job=job)
        self.assertEqual(self.client.get_sleep_daily.call_count,3)
        self.client.get_sleep_data.assert_not_called()
        self.client.get_rhr_daily.assert_not_called()
        self.assertTrue(self.result['optional_downloads_paused'])
        self.assertNotIn('private connection',str(warnings))

    def test_invalid_numeric_rows_are_retried_daily_instead_of_cached_as_missing(self):
        self.client.get_rhr_daily.side_effect = lambda first,last: [
            dict(calendarDate=s,value='invalid') for s in self.stamps if first<=s<=last]
        health,_,warnings = self.sync()
        self.assertEqual(self.client.get_rhr_day.call_count,56)
        self.assertTrue(all(day['resting_hr']==45 for day in health.values()))
        self.assertEqual(warnings,[])

    def test_pause_keeps_completed_rows_and_resume_downloads_only_remaining_dates(self):
        cache = self.cache
        class Progress:
            def isCancelled(self):return bool(cache.daily(self.start,self.end,'sleep'))
            def update(self,*args):pass
        progress = Progress()
        progress.start,progress.end = self.result['start'],self.result['end']
        with self.assertRaises(SyncPaused):self.sync(job=SyncJob(progress))
        committed = self.cache.daily(progress.start,progress.end,'sleep')
        self.assertEqual(len(committed),1)
        saved = next(iter(committed))
        self.client.get_sleep_daily.reset_mock()
        self.sync()
        for call in self.client.get_sleep_daily.call_args_list:
            self.assertFalse(call.args[0]<=saved<=call.args[1])
        self.assertEqual(len(self.cache.daily(progress.start,progress.end,'sleep')),56)
