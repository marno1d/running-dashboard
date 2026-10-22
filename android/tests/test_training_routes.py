"""Reference route configuration and density-based targets using synthetic recordings."""
import io
import json
from pathlib import Path
import shutil
import struct
import sys
import unittest
from unittest.mock import Mock
import zipfile
from fitdecode.utils import compute_crc

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from garmin_backend import Session,InputError
from training_routes import recording_data,gps_overlap,reference,selection
from dashboard_metrics import MILE,upcoming_pace,targets,target_workout


def reference_fit():
    body=b'\x40\x00\x00'+struct.pack('<H',20)+b'\x03\xfd\x04\x86\x00\x04\x85\x01\x04\x85'
    for i in range(6):body+=b'\x00'+struct.pack('<Iii',900000000+i*10,round((40+i*.001)*2**31/180),round(-111*2**31/180))
    fields=[(2,4,0x86),(253,4,0x86),(9,4,0x86),(8,4,0x86),(21,2,0x84),(22,2,0x84),(23,1,0)]
    body+=b'\x41\x00\x00'+struct.pack('<H',19)+bytes([len(fields)])+b''.join(bytes(field) for field in fields)
    for i,(intensity,gain,loss) in enumerate([(2,50,30),(0,20,10),(1,80,60),(0,30,15)]):
        body+=b'\x01'+struct.pack('<IIIIHHB',900000000+i*300,900000300+i*300,100000,300000,gain,loss,intensity)
    data=struct.pack('<BBHI4s',12,16,21171,len(body),b'.FIT')+body
    data+=struct.pack('<H',compute_crc(data))
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:archive.writestr('synthetic.fit',data)
    return out.getvalue()


class ReferenceRouteTest(unittest.TestCase):
    def setUp(self):
        self.session=Session();self.addCleanup(self.session.cache.close)
        self.activities=[dict(activityId=i,activityName='Easy run '+str(i),activityType='running',
            startTimeLocal=f'2026-10-{i:02d} 06:00:00',distance=6000,duration=1800,averageHR=125,
            elevationGain=120,elevationLoss=90) for i in range(1,9)]
        self.session.cache.save_window('2026-10-01','2026-10-21',self.activities)
        self.session.client=Mock();self.session.client.download_activity.return_value=reference_fit()
        self.settings=dict(classification_mode='native',include_recovery=False,include_recordings=False,
            include_weather=False,include_station_weather=False,target_source='custom',target_time='20:00')
    def config(self,**changes):return json.dumps(dict(self.settings,**changes))
    def assign(self,kind='easy',identity='1',**changes):
        return self.session.route_assign('liberty',kind,identity,'2026-10-21',self.config(**changes))

    def test_four_seed_routes_and_explicit_reference_slots(self):
        routes=self.session.routes(self.config())['routes']
        self.assertEqual(len(routes),4)
        self.assertTrue(all(not route['references'] for route in routes))
        with self.assertRaises(InputError):self.session.route_selection('liberty','easy_long',self.config())
        self.assign()
        with self.assertRaises(InputError):self.session.route_selection('liberty','easy_long',self.config())

    def test_read_recording_and_exclude_warmup_and_recoveries(self):
        data=recording_data(reference_fit())
        self.assertGreater(len(data['cells']),2)
        self.assertEqual([lap['active'] for lap in data['laps']],[False,True,False,True])
        self.assign('intervals')
        selected=self.session.route_selection('liberty','intervals',self.config())['selection']
        ref=selected['reference']
        self.assertEqual(ref['distance'],2000);self.assertEqual(ref['duration'],600)
        self.assertAlmostEqual(ref['gain'],50/.3048);self.assertAlmostEqual(ref['loss'],25/.3048)
        self.assertAlmostEqual(ref['gain_per_mile'],50/.3048/(2000/MILE))
        self.assertEqual(set(selected['interval_rates']),{'short','medium','long'})

    def test_manual_work_laps_and_optional_overrides(self):
        self.assign('intervals')
        changed=dict(laps={'2':[3]})
        self.assign('short','2',**changed)
        selected=self.session.route_selection('liberty','intervals',self.config(**changed))['selection']
        self.assertEqual(selected['interval_rates']['short']['distance'],1000)
        self.assertEqual(selected['interval_rates']['medium']['distance'],2000)
        self.assertAlmostEqual(selected['interval_rates']['short']['gain_per_mile'],30/.3048/(1000/MILE))

    def test_interval_reference_rejects_missing_or_empty_work_laps(self):
        with self.assertRaises(InputError):self.assign('intervals',laps={'1':[]})
        data=recording_data(reference_fit());data['laps'][1]['gain']=None
        self.session.cache.save_detail('1','route_data_v1',data)
        with self.assertRaises(InputError):self.assign('intervals')

    def test_easy_uses_whole_session_elevation_and_reuses_download(self):
        self.assign('easy');self.assign('easy_long')
        selected=self.session.route_selection('liberty','easy_long',self.config())['selection']
        self.assertEqual(selected['reference']['distance'],6000)
        self.assertAlmostEqual(selected['reference']['gain'],120/.3048)
        self.assertFalse(selected['interval_rates'])
        self.session.client.download_activity.assert_called_once()

    def test_saved_recordings_allow_reference_assignment_offline(self):
        self.session.cache.save_detail('1','route_data_v1',recording_data(reference_fit()))
        self.session.client=None
        self.assign('easy')
        self.assertEqual(self.session.route_selection('liberty','easy',self.config())['selection']['reference']['distance'],6000)

    def test_work_lap_and_session_edits_mark_references_stale(self):
        self.assign('intervals')
        with self.assertRaises(InputError):self.session.route_selection('liberty','intervals',self.config(laps={'1':[1]}))
        updated=[dict(row,distance=7000) if row['activityId']==1 else row for row in self.activities]
        self.session.cache.save_window('2026-10-01','2026-10-21',updated)
        with self.assertRaises(InputError):self.session.route_selection('liberty','intervals',self.config())

    def test_stale_optional_override_uses_shared_reference_distance_and_rates(self):
        self.assign('intervals');self.assign('short','2')
        chosen=self.session.route_selection('liberty','intervals',self.config(laps={'2':[3]}))['selection']
        self.assertEqual(chosen['interval_rates']['short'],chosen['interval_rates']['medium'])

    def test_gps_suggestions_use_actual_location_and_bounded_scans(self):
        self.assign()
        self.session.cache.save_detail('2','route_data_v1',recording_data(reference_fit()))
        self.session.cache.save_detail('3','route_data_v1',dict(cells=[[1000,1000],[1001,1001]],laps=[]))
        result=self.session.route_candidates('liberty','easy_long','2026-10-21',self.config())
        rows={row['id']:row for row in result['candidates']}
        self.assertGreater(rows['2']['overlap'],.9);self.assertEqual(rows['3']['overlap'],0)
        before=self.session.client.download_activity.call_count
        result=self.session.route_candidates('liberty','easy_long','2026-10-21',self.config(),100)
        self.assertEqual(self.session.client.download_activity.call_count-before,5)
        self.assertEqual(result['remaining'],0)
        before=self.session.client.download_activity.call_count
        self.session.route_candidates('liberty','easy','2026-10-21',self.config(),5)
        self.assertEqual(self.session.client.download_activity.call_count,before)
        self.assertNotIn('cells',json.dumps(result['candidates']))

    def test_scan_failure_preserves_prior_checks_and_can_retry(self):
        self.assign();self.session.client.download_activity.side_effect=OSError('private error')
        result=self.session.route_candidates('liberty','easy','2026-10-21',self.config(),5)
        self.assertIsNotNone(result['scan_error']);self.assertNotIn('private error',result['scan_error'])
        self.assertTrue(self.session.cache.detail('1','route_data_v1')[0])
        self.session.client.download_activity.side_effect=None
        self.assertIsNone(self.session.route_candidates('liberty','easy','2026-10-21',self.config(),5)['scan_error'])

    def test_rename_clear_and_logout(self):
        self.assign()
        self.session.route_rename('liberty','My park laps',self.config())
        self.assertEqual(self.session.route_selection('liberty','easy',self.config())['selection']['name'],'My park laps')
        self.assign(identity='')
        with self.assertRaises(InputError):self.session.route_selection('liberty','easy',self.config())
        self.session.logout()
        self.assertTrue(all(not route['references'] for route in self.session.routes(self.config())['routes']))

    def test_comparison_excludes_route_configuration_and_gps_cells(self):
        self.assign()
        settings=dict(self.settings,target_gain_per_mile=40,target_loss_per_mile=30,
            target_route_id='liberty',target_route_name='Liberty Park',target_workout_kind='easy',
            target_route_reference=dict(distance=6000,duration=1800,base_pace=300,surface='road'))
        snapshot=self.session.comparison('2026-10-21',0,json.dumps(settings))['comparison']
        from comparison_contract import validate_snapshot
        validate_snapshot(snapshot)
        encoded=json.dumps(snapshot)
        self.assertNotIn('route_data_v1',encoded);self.assertNotIn('training_routes_v1',encoded)
        self.assertEqual(snapshot['selection']['settings']['target_gain_per_mile'],40)
        self.assertIn('workout',snapshot['android']['targets'])

    @unittest.skipUnless(shutil.which('node'),'Requires web math')
    def test_density_and_interval_override_math_match_web(self):
        sys.path.insert(0,str(ROOT/'android/scripts'))
        from compare_dashboard import compare
        settings=dict(self.settings,classification_mode='web',full_history=True,target_gain_per_mile=80,target_loss_per_mile=20,
            target_temperature=85,target_humidity=70,target_interval_rates=dict(short=dict(gain_per_mile=160,loss_per_mile=40,distance=3000,duration=900)))
        snapshot=self.session.comparison('2026-10-21',30,json.dumps(settings))['comparison']
        report=compare(snapshot)
        target_differences=[item for item in report['differences'] if item['metric'].startswith('targets.') and item['status']=='different']
        self.assertEqual(target_differences,[])


class DensityTargetsTest(unittest.TestCase):
    def test_density_is_distance_independent_and_applies_without_history(self):
        settings=dict(target_gain_per_mile=40,target_loss_per_mile=40)
        for distance in (None,1000,6000,42195):self.assertEqual(upcoming_pace(300,distance,settings),upcoming_pace(300,MILE,settings))
        self.assertGreater(upcoming_pace(300,None,settings),300)
        self.assertEqual(upcoming_pace(300,None,dict(target_gain=200)),300)

    def test_marathon_scales_same_terrain_density_as_one_mile(self):
        result=targets([],[],dict(target_source='custom',target_time='20:00',target_gain_per_mile=40,target_loss_per_mile=40))
        self.assertTrue(all(row['pace']>row['base_pace'] for row in result['rows']))
        for race,distance in zip(result['races'],(MILE,5000,10000,21097.5,42195)):
            base_pace=race['base_duration']/distance*1000
            expected=upcoming_pace(base_pace,distance,dict(target_gain_per_mile=40,target_loss_per_mile=40))
            self.assertGreater(race['duration'],race['base_duration'])
            self.assertAlmostEqual(race['duration'],expected*distance/1000)

    def test_workout_duration_and_total_elevation_scale_proportionally(self):
        ref=dict(base_pace=300,surface='road',distance=6000,duration=1800)
        settings=dict(target_route_reference=ref,target_gain_per_mile=40,target_loss_per_mile=30,target_easy_minutes=45,target_easy_long_minutes=80)
        easy=target_workout({},settings)
        long=target_workout({},dict(settings,target_workout_kind='easy_long'))
        self.assertAlmostEqual(long['distance']/easy['distance'],80/45)
        self.assertAlmostEqual(long['gain']/easy['gain'],80/45)
        self.assertAlmostEqual(easy['gain'],40*easy['distance']/MILE)
        work=target_workout({},dict(settings,target_workout_kind='intervals'))
        self.assertEqual(work['distance'],6000);self.assertEqual(work['duration'],1800)

    def test_gps_matching_does_not_match_identical_shapes_at_different_locations(self):
        a=[[40000,-111000],[40001,-111000],[40002,-111000]]
        self.assertEqual(gps_overlap(a,a),1)
        self.assertEqual(gps_overlap(a,[[41000,-112000],[41001,-112000]]),0)
        self.assertEqual(gps_overlap(a,[]),0)


if __name__=='__main__':unittest.main()
