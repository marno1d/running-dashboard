"""Failure/resume boundaries and terrain quotas, using synthetic service data."""
from datetime import datetime,timezone
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock,patch
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from garmin_backend import Session,InputError
from run_cache import RunCache
from sync_job import SyncJob,SyncPaused,TerrainRequests,TerrainDeferred
from fit_fixture import recording


def activity(identity,day):
    return dict(activityId=identity,activityName='Easy run',startTimeLocal=day+' 06:00:00',
                activityType='running',duration=1800,distance=6000,averageHR=125)


def populated():
    s=Session()
    s.cache.save_window('2026-10-01','2026-10-15',[activity(1,'2026-10-10'),activity(2,'2026-10-11')])
    s.client=Mock();s.client.download_activity.return_value=recording([(0,0),(6000,1800)])
    return s

TERRAIN=dict(status='ok',source='opentopodata:ned10m,srtm30m',elevation_gain=50,elevation_loss=40,work_gain=None,work_loss=None,samples=81)
SETTINGS=json.dumps(dict(classification_mode='web',interval_mode='session',include_recordings=True,include_recovery=True,include_weather=True,include_station_weather=True))


class SyncTest(unittest.TestCase):
    def test_pause_commits_current_route_and_resume_downloads_only_remaining(self):
        s=populated();self.addCleanup(s.cache.close)
        class Progress:
            paused=False
            def isCancelled(self):return self.paused
            def update(self,*args):self.paused=s.cache.detail('2','terrain_v1')[0]
        with patch('dashboard_sync.terrain_summary',return_value=TERRAIN),patch('dashboard_sync.time.sleep'):
            first=s.sync_terrain('2026-10-15',7,SETTINGS,Progress())
            self.assertTrue(first['sync_paused'])
            self.assertEqual(first['sync']['terrain']['done'],1)
            self.assertEqual(first['sync']['terrain']['pending'],1)
            self.assertEqual(s.client.download_activity.call_count,1)
            second=s.sync_terrain('2026-10-15',7,SETTINGS)
        self.assertEqual(second['sync']['terrain']['done'],2)
        self.assertEqual(second['sync']['terrain']['pending'],0)
        self.assertEqual([c.args[0] for c in s.client.download_activity.call_args_list],['2','1'])
        s.client.connectapi.assert_not_called()
        s.client.get_sleep_data.assert_not_called()
        s.client.get_activity_weather.assert_not_called()
        s.client.get_activity_splits.assert_not_called()

    def test_provider_cooldown_avoids_refetching_original_recordings(self):
        s=populated();self.addCleanup(s.cache.close)
        s.cache.save_meta('terrain_requests',dict(retry_after=time.time()+300))
        result=s.sync_terrain('2026-10-15',7,SETTINGS)
        self.assertTrue(result['terrain_downloads_paused'])
        self.assertEqual(result['sync']['terrain']['pending'],2)
        s.client.download_activity.assert_not_called()

    def test_no_route_is_cached_and_not_retried_on_every_resume(self):
        s=populated();self.addCleanup(s.cache.close)
        with patch('dashboard_sync.time.sleep'):
            first=s.sync_terrain('2026-10-15',7,SETTINGS)
            second=s.sync_terrain('2026-10-15',7,SETTINGS)
        self.assertEqual(s.client.download_activity.call_count,2)
        self.assertEqual(second['sync']['terrain']['skipped'],2)
        self.assertEqual(first['sync']['terrain']['pending'],0)
        self.assertEqual(second['sync']['terrain']['done'],0)

    def test_independent_parser_error_does_not_discard_terrain_from_same_download(self):
        s=populated();self.addCleanup(s.cache.close)
        with patch('dashboard_sync.heart_rate_histogram',side_effect=ValueError('private decoder detail')),patch('dashboard_sync.terrain_summary',return_value=TERRAIN),patch('dashboard_sync.time.sleep'):
            result=s.sync_terrain('2026-10-15',7,SETTINGS)
        self.assertEqual(result['sync']['terrain']['done'],2)
        self.assertEqual(result['sync']['hr_recordings']['pending'],2)
        self.assertNotIn('private decoder detail',str(result['warnings']))
        self.assertEqual(s.client.download_activity.call_count,2)

    def test_summary_windows_commit_before_later_connection_failure_and_resume(self):
        s=Session();self.addCleanup(s.cache.close);s.client=Mock()
        latest=activity(1,'2026-10-12');older=activity(2,'2026-05-01')
        def interrupted(*args,params):
            if params['endDate']<'2026-10-01':raise OSError('private connection detail')
            return [latest] if params['start']=='0' else []
        s.client.connectapi.side_effect=interrupted
        with patch.object(SyncJob,'wait'):
            result=s.dashboard('2026-10-15',180,'{}')
        self.assertTrue(result['sync_paused'])
        self.assertEqual([r['id'] for r in result['runs']],['1'])
        self.assertTrue(s.cache.missing(result['start'],result['end']))
        committed=s.cache.db.execute('SELECT start,end FROM coverage').fetchone()
        self.assertEqual(committed[1],'2026-10-15')
        self.assertNotIn('private connection detail',str(result['warnings']))
        s.client.connectapi.reset_mock()
        def remaining(*args,params):
            return [older] if params['start']=='0' and params['startDate']<=older['startTimeLocal'][:10]<=params['endDate'] else []
        s.client.connectapi.side_effect=remaining
        recovered=s.dashboard('2026-10-15',180,'{}')
        self.assertTrue(recovered['cache_complete'])
        self.assertTrue(all(c.kwargs['params']['endDate']<committed[0] for c in s.client.connectapi.call_args_list))

    def test_malformed_listing_never_replaces_a_complete_cached_window(self):
        s=populated();self.addCleanup(s.cache.close)
        s.client.connectapi.return_value=[None]
        with self.assertRaises(InputError):s.dashboard('2026-10-15',7,'{}',True)
        self.assertEqual(len(s.cache.activities('2026-10-01','2026-10-15')),2)

    def test_renaming_an_activity_keeps_terrain_but_changed_recording_invalidates_it(self):
        s=populated();self.addCleanup(s.cache.close)
        s.cache.save_detail('1','terrain_v1',TERRAIN)
        rows=s.cache.activities('2026-10-01','2026-10-15')
        next(r for r in rows if r['activityId']=='1')['activityName']='Recovery run'
        s.cache.save_window('2026-10-01','2026-10-15',rows)
        self.assertEqual(s.cache.detail('1','terrain_v1'),(True,TERRAIN))
        next(r for r in rows if r['activityId']=='1')['duration']=1900
        s.cache.save_window('2026-10-01','2026-10-15',rows)
        self.assertEqual(s.cache.detail('1','terrain_v1'),(False,None))


class TerrainTransportTest(unittest.TestCase):
    def setUp(self):
        self.cache=RunCache();self.addCleanup(self.cache.close)
        self.job=SyncJob();self.job.wait=Mock()
        self.transport=TerrainRequests(self.cache,self.job)
        self.request=urllib.request.Request('https://example.invalid/elevation',data=b'not logged')
        self.response=Mock()
        self.response.__enter__=Mock(return_value=self.response)
        self.response.__exit__=Mock(return_value=False)
        self.response.read.return_value=b'{"status":"OK","results":[]}'

    def test_429_is_not_retried_and_cooldown_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            cache=RunCache(Path(directory)/'cache.sqlite')
            request=TerrainRequests(cache,self.job)
            error=urllib.error.HTTPError(self.request.full_url,429,'private response',{'Retry-After':'90'},io.BytesIO())
            with patch('sync_job.urllib.request.urlopen',side_effect=error) as fetch:
                with self.assertRaises(TerrainDeferred):request(self.request,25,None)
                fetch.assert_called_once()
            until=cache.meta('terrain_requests')['retry_after'];cache.close()
            resumed=RunCache(Path(directory)/'cache.sqlite');self.addCleanup(resumed.close)
            self.assertGreater(until,time.time()+80)
            with self.assertRaises(TerrainDeferred):TerrainRequests(resumed,self.job).ready()

    def test_daily_budget_stops_without_a_request_and_next_day_can_resume(self):
        today=datetime.now(timezone.utc).date().isoformat()
        self.cache.save_meta('terrain_requests',dict(day=today,used=900))
        with patch('sync_job.urllib.request.urlopen') as fetch:
            with self.assertRaises(TerrainDeferred):self.transport(self.request,25,None)
            fetch.assert_not_called()
        self.cache.save_meta('terrain_requests',dict(day='2000-01-01',used=900))
        with patch('sync_job.urllib.request.urlopen',return_value=self.response):self.transport(self.request,25,None)
        self.assertEqual(self.cache.meta('terrain_requests')['used'],1)

    def test_server_failure_retries_with_pacing_and_records_every_attempt(self):
        failure=urllib.error.HTTPError(self.request.full_url,503,'private',{},io.BytesIO())
        with patch('sync_job.urllib.request.urlopen',side_effect=[failure,self.response]) as fetch:
            self.assertEqual(self.transport(self.request,25,None)['status'],'OK')
        self.assertEqual(fetch.call_count,2)
        self.assertEqual(self.cache.meta('terrain_requests')['used'],2)
        self.assertTrue(any(c.args[0]>0 for c in self.job.wait.call_args_list))
        self.assertNotIn('not logged',str(self.cache.meta('terrain_requests')))

    def test_cancellation_during_backoff_prevents_the_next_request(self):
        self.job.wait.side_effect=SyncPaused('paused')
        with patch('sync_job.urllib.request.urlopen',side_effect=OSError('private')) as fetch:
            with self.assertRaises(SyncPaused):self.transport(self.request,25,None)
        # The first pacing checkpoint may cancel before any network operation.
        self.assertLessEqual(fetch.call_count,1)

    def test_exhausted_transport_pauses_instead_of_hammering_remaining_routes(self):
        with patch('sync_job.urllib.request.urlopen',side_effect=OSError('private')) as fetch:
            with self.assertRaises(TerrainDeferred):self.transport(self.request,25,None)
        self.assertEqual(fetch.call_count,3)
        self.assertGreater(self.cache.meta('terrain_requests')['retry_after'],time.time())

    def test_sign_out_clears_quota_metadata_along_with_user_data(self):
        self.cache.save_meta('terrain_requests',dict(day='2000-01-01',used=3))
        self.cache.clear()
        self.assertIsNone(self.cache.meta('terrain_requests'))
