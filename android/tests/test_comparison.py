"""Offline snapshots, safe transfer, web comparisons, and the first-week regression."""
import copy
from datetime import date
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python'),str(ROOT/'android/scripts')]
from comparison_contract import sanitize_snapshot,validate_snapshot
from garmin_backend import Session
from compare_dashboard import compare
from web_sources import dashboard


def activity(identity=1,day='2026-10-12',name='Easy run'):
    return dict(activityId=identity,activityName=name,startTimeLocal=day+' 06:00:00',
                activityType='running',distance=6000,duration=1800,averageHR=125,
                startLatitude=40.1,startLongitude=-111.2,password='must not leave app')


def populated():
    session=Session()
    session.cache.save_window('2025-06-01','2026-10-15',[activity(),activity(2,'2026-10-11','Short intervals')])
    session.cache.save_detail('2','laps',{'lapDTOs':[dict(intensityType='ACTIVE',distance=1000,duration=240,averageHR=155)]})
    session.cache.save_detail('2','interval_fit_v1',dict(distanceMeters=1000,durationSec=240,count=1,source='fit_laps',avgHr=155,ascentMeters=0,descentMeters=0))
    session.cache.save_day('2026-10-12','rhr',dict(restingHeartRate=45))
    return session


class ComparisonTest(unittest.TestCase):
    def test_cached_dashboard_has_no_client_and_never_downloads(self):
        s=populated();self.addCleanup(s.cache.close)
        s.client=Mock()
        s.client.connectapi.side_effect=AssertionError('No network in cached mode')
        settings=dict(full_history=True,include_recovery=True,include_weather=True,include_station_weather=True,include_recordings=True,include_terrain=True)
        before=s.cache.db.total_changes
        result=s.cached_dashboard('2026-10-15',0,json.dumps(settings))
        self.assertEqual(s.cache.db.total_changes,before)
        self.assertEqual(len(result['runs']),2)
        self.assertTrue(result['cached_only'])
        self.assertTrue(result['cache_complete'])
        s.client.connectapi.assert_not_called()
        s.client.get_sleep_data.assert_not_called()
        s.client.get_activity_weather.assert_not_called()
        s.client.download_activity.assert_not_called()
        s.client=None
        self.assertEqual(len(s.cached_dashboard('2026-10-15',0,json.dumps(settings))['runs']),2)

    def test_snapshot_excludes_credentials_routes_and_arbitrary_fields(self):
        s=populated();self.addCleanup(s.cache.close)
        result=s.comparison('2026-10-15',0,json.dumps(dict(full_history=True,password='not exported')))['comparison']
        text=json.dumps(result)
        self.assertNotIn('password',text)
        self.assertNotIn('Latitude',text)
        self.assertNotIn('Longitude',text)
        self.assertNotIn('tokens',text)
        self.assertEqual(validate_snapshot(result),result)
        self.assertTrue(result['android']['cached_only'])
        self.assertEqual(result['activities'][0]['averageHR'],125)
        bad=copy.deepcopy(result);bad['activities'][0]['startLatitude']=40
        with self.assertRaises(ValueError):validate_snapshot(bad)
        bad=copy.deepcopy(result);bad['tokens']='secret'
        with self.assertRaises(ValueError):validate_snapshot(bad)
        bad=copy.deepcopy(result);bad['activities'][0]['distance']=float('nan')
        with self.assertRaises(ValueError):validate_snapshot(bad)

    def test_all_range_includes_first_calendar_week(self):
        s=populated();self.addCleanup(s.cache.close)
        result=s.cached_dashboard('2026-10-15',0,json.dumps(dict(full_history=True)))
        self.assertEqual(result['weeks'][0]['date'],'2025-05-26')
        # Rolling windows still exclude partial leading weeks, matching web filtering.
        rolled=s.cached_dashboard('2026-10-15',7,json.dumps(dict(full_history=True)))
        self.assertTrue(all(w['date']>=rolled['start'] for w in rolled['weeks']))

    def test_web_builder_accepts_saved_metrics_without_touching_fit_files(self):
        raw=activity(name='Short intervals')
        metrics={'1':{'interval_active_laps_v2':dict(distanceMeters=1000,durationSec=240,count=1,avgHr=155,ascentMeters=0,descentMeters=0,source='fit_laps')}}
        with patch.object(dashboard,'activity_file_map',side_effect=AssertionError('No filesystem lookup')):
            records=dashboard.build_records([raw],{}, {}, {}, {}, {},fit_metrics=metrics)
        self.assertEqual(records[0]['intervalAvgHr'],155)
        self.assertAlmostEqual(records[0]['intervalPaceSecPerMile'],round(240*1.609344,1))

    @unittest.skipUnless(shutil.which('node'),'Requires the actual web JavaScript')
    def test_real_web_and_native_replay_share_same_inputs(self):
        s=populated();self.addCleanup(s.cache.close)
        snapshot=s.comparison('2026-10-15',0,json.dumps(dict(full_history=True,classification_mode='web',interval_mode='session')))['comparison']
        report=compare(snapshot,matrix=True)
        self.assertEqual(report['activities'],2)
        self.assertEqual(report['cases'],9)
        self.assertEqual(report['counts']['different'],0,report['differences'])

    @unittest.skipUnless(shutil.which('node'),'Requires the actual web JavaScript')
    def test_decimal_measurements_missing_daily_hr_and_missing_fit_match_web(self):
        from datetime import timedelta
        s=Session();self.addCleanup(s.cache.close)
        activities=[]
        for i in range(18):
            day=(date(2026,9,1)+timedelta(days=i)).isoformat()
            kind='Short intervals' if i%5==0 else '5K time trial' if i in (9,17) else 'Easy run'
            raw=dict(activity(i+1,day,kind),distance=6000.123+i*21.8,duration=1800.4+i*13.27,
                     averageHR=150+i if kind=='Short intervals' else 120+i%9,
                     elevationGain=32.145+i,elevationLoss=25.752+i,activityTrainingLoad=71.345+i)
            activities.append(raw)
            identity=str(i+1)
            s.cache.save_detail(identity,'weather_v1',dict(temperature=68.23,dewPoint=57.491,humidity=52.83))
            s.cache.save_detail(identity,'terrain_v1',dict(status='ok',source='opentopodata:ned10m,srtm30m',elevation_gain=61.345+i,elevation_loss=52.779+i,work_gain=19.12 if i%10 else None,work_loss=12.44 if i%10 else None,samples=81))
            if kind=='Short intervals':
                s.cache.save_detail(identity,'laps',dict(lapDTOs=[dict(intensityType='ACTIVE',distance=1234.56,duration=321.23,averageHR=151.7,elevationGain=12.34,elevationLoss=5.67)]))
                raw['splitSummaries']=[dict(splitType='INTERVAL_ACTIVE',distance=1234.56,duration=321.23,noOfSplits=1)]
                # One session has laps but no FIT, so web mode must not substitute
                # lap HR/elevation for unavailable FIT-derived measurements.
                if i:
                    s.cache.save_detail(identity,'interval_fit_v1',dict(distanceMeters=1234.56,durationSec=321.23,count=1,avgHr=151.7+i,ascentMeters=12.34,descentMeters=5.67,source='fit_laps'))
            if kind=='5K time trial':
                s.cache.save_detail(identity,'effort_v1',dict(duration=1194.387-i,distance=5000,method='fit_rolling_5000m'))
            # Daily gaps exercise both same-week and median-of-weeks fallbacks.
            if 7<=i<14 and i!=10:
                s.cache.save_day(day,'rhr',dict(restingHeartRate=44+i%4))
                s.cache.save_day(day,'sleep',dict(sleepHours=7.23+i*.017))
                s.cache.save_day(day,'hrv',dict(hrvLastNightAvg=71+i))
        s.cache.save_window('2025-06-01','2026-09-18',activities)
        settings=dict(full_history=True,classification_mode='web',interval_mode='session',target_gain=140,target_loss=80,target_temperature=85,target_humidity=60)
        for enabled in (False,True):
            with self.subTest(terrain=enabled):
                settings['include_terrain']=enabled
                snapshot=s.comparison('2026-09-18',0,json.dumps(settings))['comparison']
                report=compare(snapshot,matrix=True)
                self.assertEqual(report['counts']['different'],0,report['differences'])
                self.assertEqual(len(snapshot['android']['runs']),18)
        # Precision changes are for calculated rows; saved downloads stay intact.
        self.assertEqual(s.cache.activities('2026-09-01','2026-09-01')[0]['distance'],6000.123)

    def test_legacy_sample_still_matches_receiver_allowlist(self):
        from receive_sample import ROW_FIELDS,LAP_FIELDS
        s=Session();self.addCleanup(s.cache.close);s.client=Mock()
        s.client.get_activities_by_date.return_value=[activity()]
        s.client.get_activity_splits.return_value={'lapDTOs':[]}
        sample=s.sample('2026-10-15')['sample']['runs'][0]
        self.assertFalse(set(sample)-ROW_FIELDS)
        self.assertTrue(all(not set(lap)-LAP_FIELDS for lap in sample['laps']))

    def test_prediction_comparison_preserves_multiple_sessions_on_same_day(self):
        from compare_dashboard import differences
        native=dict(summary={},runs=[],weeks=[],run_points=[],interval_points=[],trial_points=[],easy_prediction_points=[],targets={},
                    prediction_points=[dict(date='2026-10-15',duration=1200),dict(date='2026-10-15',duration=1210)])
        web=dict(native,records=[])
        self.assertEqual(differences(native,web,'same-day'),[])


class ReceiverTest(unittest.TestCase):
    def setUp(self):
        import receive_comparison as module
        import threading
        from http.server import ThreadingHTTPServer
        self.module=module
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root_patch=patch.object(module,'ROOT',Path(self.directory.name));self.root_patch.start();self.addCleanup(self.root_patch.stop)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),module.Receiver)
        self.server.token='synthetic-capability';self.server.state={};self.server.lock=threading.Lock();self.server.daemon_threads=True
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def test_portal_requires_capability_and_does_not_cache_private_page(self):
        import urllib.request,urllib.error
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(self.url+'/compare/incorrect')
        self.assertEqual(error.exception.code,404);error.exception.close()
        with urllib.request.urlopen(self.url+'/compare/synthetic-capability') as response:
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertIn('Share saved dashboard',response.read().decode())

    def test_receiver_rejects_unknown_data_and_writes_owner_only_snapshot(self):
        import urllib.request,urllib.error
        session=populated();self.addCleanup(session.cache.close)
        payload=session.comparison('2026-10-15',0,'{}')['comparison']
        bad=dict(payload,tokens='do not receive')
        request=urllib.request.Request(self.url+'/comparison/synthetic-capability',data=json.dumps(bad).encode(),headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
        self.assertEqual(error.exception.code,400);error.exception.close()
        with patch.object(self.module.Receiver,'run_comparison') as run:
            request=urllib.request.Request(self.url+'/comparison/synthetic-capability',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:self.assertEqual(response.status,200)
        saved=Path(self.directory.name)/'.state/comparison-snapshot.json'
        self.assertEqual(saved.stat().st_mode&0o777,0o600)
        self.assertEqual(validate_snapshot(json.loads(saved.read_text())),payload)
