"""Check the native port against web mathematics and real cache boundaries."""
from datetime import date
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from dashboard_metrics import (elevation_delta, weather_reduction, vdot_from_5k, targets,
                               predictions, normalized_paces, weekly, parse_time, intensity)
from dashboard_sync import sync_extras
from garmin_backend import Session
from run_cache import RunCache
from recording_hr import heart_rate_histogram
from fitdecode.utils import compute_crc


def row(identity, day, kind='easy', pace=300, hr=125):
    return dict(id=str(identity),title='Synthetic session',started=day+' 06:00:00',date=day,
                category=kind,pace=pace,average_hr=hr,is_run=True,activity_type='running',
                duration=1800,distance=6000,training_load=80,
                work_pace=pace if kind in ('short','medium','long') else None,
                work_hr=hr if kind in ('short','medium','long') else None)


@unittest.skipUnless(shutil.which('node'),'Node is needed to compare against the web app')
class WebParityTest(unittest.TestCase):
    def web(self, expression, records=None, health=None):
        data=dict(records=records or [],weeks=[],meta=dict(maxHr=191),labels={})
        if health:
            for day,values in health.items():
                data['weeks'].append(dict(week=day,restingHrAvg=values['resting_hr']))
        script = '''const fs=require('fs'),vm=require('vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const source=fs.readFileSync(input.source,'utf8').split('\\nrenderMeta();')[0];
const context={window:{GARMIN_DASHBOARD_DATA:input.data},document:{querySelector:()=>null}};
vm.createContext(context);vm.runInContext(source,context);
process.stdout.write(JSON.stringify(vm.runInContext(input.expression,context)));
'''
        result=subprocess.run(['node','-e',script],input=json.dumps(dict(data=data,expression=expression,source=str(ROOT/'web_app/dashboard/app.js'))),text=True,capture_output=True,check=True)
        return json.loads(result.stdout)

    def test_fvdot_targets_and_equivalent_races_match_web(self):
        for seconds in (900,1200,1800,2400):
            native=targets([],[],dict(target_source='custom',target_time=f'{seconds//60}:00'))
            web=self.web(f'intervalTargetsFrom5k({seconds})')
            self.assertAlmostEqual(native['vdot'],web['vdot'],places=10)
            for first,second in zip(native['rows'],web['rows']):
                self.assertAlmostEqual(first['pace']*1.609344,second['paceSecPerMile'],places=8)
            web_races=self.web(f'racePredictionsFromVdot(vdotFromRace(5000,{seconds}))')
            for first,second in zip(native['races'],web_races):
                self.assertAlmostEqual(first['duration'],second['seconds'],places=8)

    def test_elevation_and_weather_match_web_over_mixed_conditions(self):
        for pace,distance,gain,loss in ((240,10000,100,100),(310,7000,200,20),(180,5000,0,100),(380,12000,500,400)):
            expected=self.web(f'norwegianElevationDeltaSecPerMile({pace*1.609344},{distance/1609.344},{gain/.3048},{loss/.3048})')
            self.assertAlmostEqual(elevation_delta(pace,distance,gain,loss)*1.609344,max(-120,min(180,expected)),places=7)
        for temp,dew in ((45,30),(60,54),(70,60),(90,75)):
            self.assertEqual(weather_reduction(temp,dew),self.web(f'nsmWeatherReductionFraction({temp},{dew})'))

    def test_interval_prediction_and_intensity_models_match_web(self):
        rows=[row(i,f'2026-09-{i+1:02d}',('short','medium','long')[i%3],250+i*2,150+i) for i in range(8)]
        rows.append(dict(row(20,'2026-09-10','trial'),best_5k={'duration':1150}))
        health={f'2026-09-{i+1:02d}':dict(resting_hr=45) for i in range(10)}
        records=[]
        for item in rows:
            records.append(dict(id=item['id'],date=item['date'],datetime=item['started'],
                                category=dict(short='short_interval',medium='medium_interval',long='long_interval',trial='5k_time_trial')[item['category']],
                                intervalPaceSecPerMile=(item['work_pace'] or 0)*1.609344,
                                intervalAvgHr=item['work_hr'],restingHr=45,
                                fastest5kSec=item.get('best_5k',{}).get('duration')))
        for mode in ('observed','intensity'):
            native,_=predictions(rows,dict(prediction_mode=mode),health)
            expected=self.web("buildPredicted5kSeries(DATA.records,DATA.records,'"+('hrAdjusted' if mode=='intensity' else 'pace')+"')",records)
            self.assertEqual(len(native),len(expected))
            for first,second in zip(native,expected):
                self.assertAlmostEqual(first['duration'],second['value'],places=6)

    def test_easy_predictions_with_trails_and_intensity_match_web(self):
        rows=[row(i,f'2026-09-{i+1:02d}',pace=310+i*2,hr=120+i) for i in range(12)]
        rows[4]['activity_type']='trail_running'
        rows[5]['activity_type']='treadmill_running'
        rows[6]['category']='easy_long'
        rows += [dict(row(20,'2026-09-09','trial'),best_5k={'duration':1150}),dict(row(21,'2026-09-13','trial'),best_5k={'duration':1140})]
        rows.sort(key=lambda r:r['started'])
        records=[dict(id=r['id'],date=r['date'],datetime=r['started'],type=r['activity_type'],category='5k_time_trial' if r['category']=='trial' else r['category'],paceSecPerMile=r['pace']*1.609344,avgHr=r['average_hr'],restingHr=45,fastest5kSec=r.get('best_5k',{}).get('duration')) for r in rows]
        health={r['date']:dict(resting_hr=45) for r in rows}
        for mode in ('observed','intensity'):
            actual=predictions(rows,dict(prediction_mode=mode),health)[1]
            expected=self.web("buildEasyPredicted5kSeries(DATA.records,DATA.records,'"+('hrAdjusted' if mode=='intensity' else 'pace')+"')",records)
            self.assertEqual(len(actual),len(expected))
            self.assertTrue(actual)
            for first,second in zip(actual,expected):
                self.assertAlmostEqual(first['duration'],second['value'],places=6)

    def test_easy_band_matches_web_quantiles_and_smoothing(self):
        from dashboard_metrics import rolling_easy_range
        rows=[row(i,f'2026-09-{i+1:02d}',pace=300+i*5) for i in range(12)]
        rows[6]['activity_type']='trail_running'
        records=[dict(date=r['date'],type=r['activity_type'],paceSecPerMile=r['pace']*1.609344) for r in rows]
        rolling_easy_range(rows)
        actual=[r for r in rows if 'range_lower' in r]
        expected=self.web('rollingEasyPaceRange(DATA.records.map(row=>({row,value:row.paceSecPerMile})))',records)
        self.assertEqual(len(actual),len(expected))
        for first,second in zip(actual,expected):
            self.assertAlmostEqual(first['range_lower']*1.609344,second['lower'],places=7)
            self.assertAlmostEqual(first['range_upper']*1.609344,second['upper'],places=7)

    def test_target_elevation_distance_basis_and_conditions_match_web(self):
        basis=dict(row(1,'2026-10-01','short'),work_distance=4000)
        settings=dict(target_source='custom',target_time='20:00',target_temperature=85,target_humidity=70,target_gain=200,target_loss=150)
        actual=targets([basis],[],settings)['rows'][0]['pace']*1.609344
        expression="adjustedTargetPace(intervalTargetsFrom5k(1200).rows[0].paceSecPerMile,{temperatureF:85,humidityPct:70,dewPointF:dewPointFromTemperatureHumidityF(85,70),elevationGainFeet:200,elevationLossFeet:150},{miles:4000/METERS_PER_MILE})"
        self.assertAlmostEqual(actual,self.web(expression),places=7)
        missing_basis=targets([],[],dict(target_source='custom',target_time='20:00',target_gain=200))
        self.assertEqual(missing_basis['rows'][0]['pace'],missing_basis['rows'][0]['base_pace'])


class DashboardTest(unittest.TestCase):
    def test_weekly_load_cross_training_partial_weeks_and_missing_health(self):
        easy=row(1,'2026-10-06')
        cross=dict(row(2,'2026-10-07','cross_train'),is_run=False,distance=20000,duration=3600)
        interval=dict(row(3,'2026-10-08','short'),work_duration=600)
        health={'2026-10-06':dict(sleep_hours=8,resting_hr=45), '2026-10-07':dict(sleep_hours=None,hrv=60),
                '2026-10-05':dict(sleep_hours=1)}
        weeks=weekly([easy,cross,interval],health,'2026-10-06','2026-10-08')
        self.assertEqual(len(weeks),1)
        self.assertEqual(weeks[0]['total_minutes'],120)
        self.assertEqual(weeks[0]['run_minutes'],60)
        self.assertAlmostEqual(weeks[0]['run_miles'],12000/1609.344)
        self.assertAlmostEqual(weeks[0]['interval_percent'],600/7200*100)
        self.assertEqual(weeks[0]['sleep_hours'],8)
        self.assertEqual(weeks[0]['sleep_hours_days'],1)
        self.assertEqual(weeks[0]['hrv'],60)

    def test_missing_daily_resting_hr_preserves_workout_hr_and_uses_weekly_fallback(self):
        workout=row(1,'2026-10-06',hr=125)
        health={'2026-10-05':dict(resting_hr=45),'2026-10-07':dict(resting_hr=46)}
        self.assertAlmostEqual(intensity(workout,health,191,False),(125-46)/(191-46))
        # Without that week's recovery, use the median of rounded weekly means.
        health={'2026-09-21':dict(resting_hr=44),'2026-09-28':dict(resting_hr=45)}
        self.assertAlmostEqual(intensity(workout,health,191,False),(125-44.5)/(191-44.5))
        interval=dict(workout,category='short',work_hr=155)
        self.assertAlmostEqual(intensity(interval,health,191,True),(155-44.5)/(191-44.5))

    def test_custom_548_day_range_uses_exact_dates(self):
        session=Session();self.addCleanup(session.cache.close);session.client=Mock()
        session.client.connectapi.return_value=[]
        result=session.dashboard('2026-10-14',-1,json.dumps(dict(custom_start='2025-04-15',custom_end='2026-10-14')))
        self.assertEqual(result['start'],'2025-04-15')
        self.assertEqual(result['end'],'2026-10-14')
        self.assertNotIn('activityType',session.client.connectapi.call_args.kwargs['params'])

    def test_time_validation_and_target_weather_direction(self):
        self.assertEqual(parse_time('20:30'),1230)
        for invalid in ('20:70','-1:00','abc','00:00','1:2:3:4'):
            self.assertIsNone(parse_time(invalid))
        cool=targets([],[],dict(target_source='custom',target_time='20:00'))
        hot=targets([],[],dict(target_source='custom',target_time='20:00',target_temperature=90,target_humidity=80))
        self.assertGreater(hot['rows'][0]['pace'],cool['rows'][0]['pace'])
        self.assertEqual(targets([],[],{})['error'],'No interval prediction available yet.')

    def test_easy_estimate_requires_two_nearby_trials_and_excludes_treadmill(self):
        rows=[row(i,f'2026-09-{i+1:02d}',pace=320+i) for i in range(12)]
        trial=dict(row(20,'2026-09-07','trial'),best_5k={'duration':1150})
        rows.append(trial);rows.sort(key=lambda r:r['started'])
        self.assertEqual(predictions(rows,{},{} )[1],[])
        rows.append(dict(row(21,'2026-09-13','trial'),best_5k={'duration':1140}))
        self.assertTrue(predictions(rows,{},{} )[1])
        for item in rows:item['activity_type']='treadmill_running'
        self.assertEqual(predictions(rows,{},{} )[1],[])

    @patch('dashboard_sync.time.sleep')
    def test_sync_only_missing_health_kinds_and_retry_weather(self, sleep):
        cache=RunCache();self.addCleanup(cache.close);client=Mock()
        client.get_sleep_data.return_value={'dailySleepDTO':{'sleepTimeSeconds':28800}}
        client.get_rhr_day.return_value={'restingHeartRate':45}
        client.get_hrv_data.side_effect=[RuntimeError('secret ticket'),{'hrvSummary':{'lastNightAvg':60}}]
        client.get_activity_weather.side_effect=[RuntimeError('secret ticket'),{'temp':70,'relativeHumidity':40}]
        result=dict(start='2026-01-01',end='2026-01-01',runs=[row(1,'2026-01-01')])
        settings=dict(include_recovery=True,include_weather=True)
        health,weather,warnings=sync_extras(client,cache,result,settings,False,Mock())
        self.assertEqual(health['2026-01-01']['sleep_hours'],8)
        self.assertIsNone(health['2026-01-01']['hrv'])
        self.assertEqual(len(warnings),2)
        health,weather,warnings=sync_extras(client,cache,result,settings,False,Mock())
        self.assertEqual(health['2026-01-01']['hrv'],60)
        self.assertEqual(weather['1']['temperatureF'],70)
        self.assertEqual(client.get_sleep_data.call_count,1)
        self.assertEqual(client.get_hrv_data.call_count,2)
        self.assertEqual(warnings,[])
        cache.clear();self.assertEqual(cache.daily('2026-01-01','2026-01-01','sleep'),{})

    def test_hr_histogram_uses_recorded_time_and_caps_pauses(self):
        body=b'\x40\x00\x00'+struct.pack('<H',20)+b'\x02\xfd\x04\x86\x03\x01\x02'
        for seconds,hr in ((0,120),(5,150),(25,125),(30,125)):
            body+=b'\x00'+struct.pack('<IB',900000000+seconds,hr)
        data=struct.pack('<BBHI4s',12,16,21171,len(body),b'.FIT')+body
        data+=struct.pack('<H',compute_crc(data))
        self.assertEqual(heart_rate_histogram(data),{'120':5,'150':10,'125':5})

    def test_old_cache_migration_preserves_runs_and_refetches_all_activity_types(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'old.sqlite'
            cache=RunCache(path)
            cache.save_window('2026-01-01','2026-01-01',[dict(activityId=1,startTimeLocal='2026-01-01 06:00:00')])
            cache.db.execute('PRAGMA user_version=0');cache.close()
            upgraded=RunCache(path);self.addCleanup(upgraded.close)
            self.assertEqual(len(upgraded.activities('2026-01-01','2026-01-01')),1)
            self.assertEqual(upgraded.missing('2026-01-01','2026-01-01'),[('2026-01-01','2026-01-01')])
