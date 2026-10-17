"""Source, cache, and calibration parity; all service responses are synthetic."""
from datetime import date, datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from dashboard_sources import station_weather, terrain_summary, merge_weather
from dashboard_metrics import predictions, enrich, rolling_easy_range
from run_cache import RunCache
from garmin_backend import Session
from training import normalized_runs
from web_sources import dashboard, stations, terrain
from fit_fixture import recording


def activity(identity,day,title='Easy run',kind='running',**fields):
    return dict(activityId=identity,activityName=title,startTimeLocal=day+' 06:00:00',
                startTimeGMT=day+' 12:00:00',activityType={'typeKey':kind},distance=6000,
                duration=1800,averageHR=125,**fields)


def model_row(identity,day,kind,pace=250):
    return dict(id=str(identity),title='Synthetic',date=day,started=day+' 06:00:00',category=kind,
                pace=pace,duration=1800,distance=6000,work_pace=pace,work_hr=155,
                average_hr=125,activity_type='running')


class SourceParityTest(unittest.TestCase):
    def setUp(self):
        self.cache=RunCache();self.addCleanup(self.cache.close)
        self.day=date(2020,1,2)
        self.row=activity(1,self.day.isoformat(),startLatitude=40.2192,startLongitude=-111.7234)
        self.row['_station_match']=stations.nearest_station(self.row,15)
        self.csv='station,valid,tmpf,dwpf,relh,feel,metar\nPVU,2020-01-02 12:15,65,40,40,65,synthetic\n'

    def test_station_match_uses_web_midpoint_and_caches_history(self):
        with patch.object(stations,'fetch_station_csv',return_value=self.csv) as fetch:
            first,warnings=station_weather(self.cache,[self.row],Mock())
            second,_=station_weather(self.cache,[self.row],Mock())
        self.assertEqual(warnings,[]);fetch.assert_called_once()
        self.assertEqual(first,second)
        self.assertEqual(first['1']['station'],'KPVU')
        self.assertEqual(first['1']['temperature'],65)
        self.assertEqual(first['1']['observationOffsetMinutes'],0)
        self.assertEqual(merge_weather(dict(temperature=80,humidity=60),first['1'])['temperatureF'],65)

    def test_empty_responses_are_cached_and_transport_errors_are_not(self):
        empty='station,valid,tmpf,dwpf,relh,feel,metar\n'
        with patch.object(stations,'fetch_station_csv',return_value=empty) as fetch:
            self.assertEqual(station_weather(self.cache,[self.row],Mock())[0],{})
            station_weather(self.cache,[self.row],Mock());fetch.assert_called_once()
        self.cache.clear()
        with patch.object(stations,'fetch_station_csv',side_effect=OSError('private detail')):
            result,warnings=station_weather(self.cache,[self.row],Mock())
        self.assertEqual(result,{})
        self.assertNotIn('private detail',str(warnings))
        self.assertEqual(self.cache.daily('2020-01-02','2020-01-02','station:KPVU'),{})

    def test_current_day_empty_cache_expires_after_six_hours(self):
        now=datetime(2020,1,2,18,tzinfo=timezone.utc)
        with patch.object(stations,'fetch_station_csv',return_value='station,valid\n') as fetch:
            station_weather(self.cache,[self.row],Mock(),now)
            station_weather(self.cache,[self.row],Mock(),now+timedelta(hours=1))
            self.assertEqual(fetch.call_count,1)
            station_weather(self.cache,[self.row],Mock(),now+timedelta(hours=6))
            self.assertEqual(fetch.call_count,2)

    def test_weather_merges_each_field_with_garmin_fallback(self):
        station=dict(status='ok',temperature=60,dewPoint=None,humidity=None,source='iem-asos:KPVU',station='KPVU',stationName='Provo')
        result=merge_weather(dict(temperature=75,dewPoint=50,humidity=60),station)
        self.assertEqual((result['temperatureF'],result['dewPointF'],result['humidity']),(60,50,60))
        self.assertIn('KPVU',result['source'])
        self.assertIn('garmin',result['source'].lower())

    def test_terrain_uses_web_sampling_and_retains_only_aggregates(self):
        start=datetime(2026,10,1,12)
        route=[dict(timestamp=start+timedelta(seconds=i*10),lat=40+i*.0001,lng=-111,distanceMeters=i*100) for i in range(4)]
        def profile(samples,args):
            return [dict(p,elevationMeters=100+(i%3)*2) for i,p in enumerate(samples)]
        with patch.object(terrain,'route_points_from_fit',return_value=route),patch.object(terrain,'query_elevations',side_effect=profile) as query,patch.object(terrain,'active_lap_windows_from_fit',return_value=[(start,start+timedelta(seconds=30))]):
            result=terrain_summary(recording([(0,0),(5000,1200)]),self.row)
        self.assertEqual(result['status'],'ok')
        self.assertEqual(query.call_args.args[1].dataset,'ned10m,srtm30m')
        self.assertEqual(result['samples'],5)
        for banned in ('profile','lat','lng','position_lat','timestamp'):
            self.assertNotIn(banned,result)
        self.assertIsNotNone(result['work_gain'])

    def test_indoor_terrain_is_skipped_without_querying_coordinates(self):
        row=dict(self.row,activityType={'typeKey':'treadmill_running'})
        with patch.object(terrain,'route_points_from_fit') as parse:
            self.assertEqual(terrain_summary(b'not needed',row)['status'],'skipped')
            parse.assert_not_called()

    def test_cache_keeps_station_match_but_discards_coordinates(self):
        self.row['splitSummaries']=[dict(splitType='INTERVAL_ACTIVE',distance=1000,duration=200,startLatitude=40)]
        self.cache.save_window('2020-01-02','2020-01-02',[self.row])
        saved=self.cache.activities('2020-01-02','2020-01-02')[0]
        self.assertEqual(saved['_station_match']['station'],'KPVU')
        self.assertNotIn('startLatitude',json.dumps(saved))
        self.assertNotIn('startLongitude',json.dumps(saved))


class NativeParityTest(unittest.TestCase):
    def test_web_classifier_injury_long_runs_and_manual_overrides(self):
        rows=[dict(activity(1,'2026-01-01','Morning running'),averageHR=150),
              activity(2,'2026-01-02','Base run',movingDuration=4000),
              activity(3,'2026-01-03','5k time trial'),activity(4,'2026-01-04','Medium intervals')]
        result=normalized_runs(rows,'2026-10-14',730,{},134,classification='web')
        by_id={r['id']:r for r in result['runs']}
        self.assertEqual([by_id[str(i)]['category'] for i in range(1,5)],['rebuild_run','easy_long','trial','medium'])
        self.assertAlmostEqual(by_id['2']['pace'],4000/6000*1000)
        result=normalized_runs(rows,'2026-10-14',730,{'1':'easy'},134,classification='web')
        self.assertEqual({r['id']:r for r in result['runs']}['1']['category'],'easy')

    def test_full_history_calibration_survives_a_short_display_range(self):
        history=[model_row(1,'2026-08-01','short'),dict(model_row(2,'2026-08-10','trial'),best_5k={'duration':1100}),model_row(3,'2026-10-01','short')]
        displayed=[history[-1]]
        expected=predictions(history,{},{} )[0][-1]['duration']
        result=predictions(displayed,{}, {},history)[0]
        self.assertEqual(len(result),1)
        self.assertAlmostEqual(result[0]['duration'],expected)
        self.assertEqual(result[0]['calibrations'],1)
        self.assertNotAlmostEqual(result[0]['duration'],1250,places=1)

    def test_backend_fetches_full_context_but_returns_only_visible_sessions(self):
        session=Session();self.addCleanup(session.cache.close);session.client=Mock()
        rows=[activity(1,'2025-07-01','Short intervals'),activity(2,'2025-07-10','5k time trial'),activity(3,'2026-10-12','Short intervals')]
        session.client.connectapi.side_effect=lambda *a,params:[r for r in rows if params['startDate']<=r['startTimeLocal'][:10]<=params['endDate']] if params['start']=='0' else []
        session.client.get_activity_splits.return_value={'lapDTOs':[dict(intensityType='ACTIVE',distance=1000,duration=240)]}
        session.client.download_activity.return_value=recording([(0,0),(5000,1100)])
        result=session.dashboard('2026-10-14',7,json.dumps(dict(full_history=True,classification_mode='web')))
        self.assertEqual([r['id'] for r in result['runs']],['3'])
        self.assertEqual(result['history_start'],'2025-06-01')
        self.assertEqual(result['prediction_points'][0]['calibrations'],1)
        self.assertEqual(result['targets']['source'],'predicted')
        self.assertEqual(min(c.kwargs['params']['startDate'] for c in session.client.connectapi.call_args_list),'2025-06-01')

    def test_full_context_fit_metrics_and_manual_lap_override(self):
        raw=activity(1,'2026-10-01','Short intervals',splitSummaries=[dict(splitType='INTERVAL_ACTIVE',distance=2000,duration=500,noOfSplits=5)])
        fit={'1':dict(distanceMeters=2100,durationSec=510,count=5,source='fit_laps',avgHr=155,ascentMeters=10,descentMeters=9)}
        def result():
            return dict(normalized_runs([raw],'2026-10-14',90,{}),interval_points=[],trial_points=[])
        first=result();enrich(first,[raw],{}, {},{},dict(interval_mode='session'),fit_intervals=fit)
        self.assertEqual(first['runs'][0]['work_duration'],500)
        self.assertEqual(first['runs'][0]['work_hr'],155)
        self.assertEqual(first['interval_points'][0]['pace'],250)
        split={'1':{'lapDTOs':[dict(intensityType='ACTIVE',distance=1000,duration=300,averageHR=140)]}}
        second=result();enrich(second,[raw],split,{}, {},dict(interval_mode='session',laps={'1':[0]}),fit_intervals=fit)
        self.assertEqual(second['runs'][0]['work_duration'],300)
        self.assertEqual(second['runs'][0]['work_hr'],140)

    def test_rolling_easy_band_excludes_trails_and_resets_after_gap(self):
        points=[dict(model_row(i,f'2026-08-{i+1:02d}','easy'),pace=300+i*10) for i in range(5)]
        trail=dict(model_row(50,'2026-08-06','easy'),activity_type='trail_running',pace=900)
        points.extend([trail,dict(model_row(51,'2026-10-01','easy'),pace=350)])
        rolling_easy_range(points)
        self.assertEqual(points[3]['range_lower'],307.5)
        self.assertEqual(points[3]['range_upper'],322.5)
        self.assertAlmostEqual(points[4]['range_lower'],308.375)
        self.assertNotIn('range_lower',trail)
        self.assertNotIn('range_lower',points[-1])

    def test_garmin_fastest_split_fallback_has_explicit_provenance(self):
        session=Session();self.addCleanup(session.cache.close);session.client=Mock()
        session.client.connectapi.side_effect=[[activity(1,'2026-10-12','5k time trial',fastestSplit_5000=1234)],[]]
        session.client.download_activity.side_effect=OSError('offline')
        result=session.dashboard('2026-10-14',7,json.dumps(dict(classification_mode='web')))
        self.assertEqual(result['trial_points'][0]['duration'],1234)
        self.assertEqual(result['runs'][0]['best_5k']['method'],'garmin_fastest_split')
        self.assertNotIn('start_distance',result['runs'][0]['best_5k'])

    @patch('dashboard_sync.time.sleep')
    def test_optional_rate_limit_keeps_cached_chart_inputs(self, sleep):
        from garminconnect.exceptions import GarminConnectTooManyRequestsError
        session=Session();self.addCleanup(session.cache.close);session.client=Mock()
        session.cache.save_window('2026-10-08','2026-10-14',[activity(1,'2026-10-12')])
        session.client.get_sleep_data.side_effect=GarminConnectTooManyRequestsError('private service detail')
        result=session.dashboard('2026-10-14',7,json.dumps(dict(include_recovery=True,include_recordings=True,include_weather=True)))
        self.assertEqual(len(result['run_points']),1)
        self.assertTrue(result['optional_downloads_paused'])
        self.assertNotIn('private service detail',str(result['warnings']))
        session.client.download_activity.assert_not_called()
        session.client.get_activity_weather.assert_not_called()
        self.assertEqual(session.client.get_sleep_data.call_count,1)
