"""Route-review exports cover saved history and remain read-only and allowlisted."""
import copy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python'),str(ROOT/'android/scripts')]
import garmin_backend
from garmin_backend import Session
from route_review_contract import validate_review
from receive_route_review import Receiver
from review_routes import report


class RouteReviewTest(unittest.TestCase):
    def setUp(self):
        self.session=Session();self.addCleanup(self.session.cache.close)
        self.session.cache.save_window('2020-01-01','2026-10-23',[
            dict(activityId=1,activityName='Old reference',startTimeLocal='2020-01-02 06:00:00',activityType=dict(typeKey='running'),distance=1609.344,duration=600,elevationGain=30.48,elevationLoss=6.096),
            dict(activityId=2,activityName='Recent run',startTimeLocal='2026-10-22 06:00:00',distance=5000,duration=1800)])
        self.session.cache.save_meta('route_book_v2',[dict(id='test',name='Test loop',shape='loop',surface='road',reverse=False,extent=1609.344,
            reference=dict(id='1',title='Old reference',date='2020-01-02',distance=1609.344,duration=600,fingerprint='private'))])
        self.session.cache.save_detail('1','route_data_v1',dict(profile_version=2,profile=[[0,0,0],[1609.344,30.48,6.096]],laps=[],suggested_loop=1609.344,cells=[[40123,-111234]],tokens='secret'))
        self.session.cache.save_detail('1','terrain_v1',dict(status='ok',route=dict(profile_version=1,source='opentopodata:synthetic',profile=[[0,0,0],[1609.344,30.48,6.096]],suggested_loop=1609.344,track=[[0,0,0],[1609.344,1,.5]])))
        self.session.cache.save_detail('1','route_outline_v1',dict(segments=[[[0,0],[1,.5]]],latitude=40))
        self.session.cache.save_detail('2','laps',dict(lapDTOs=[dict(distance=1000,duration=300,password='secret')]))
        self.session.cache.save_detail('2','terrain_v1',dict(elevation_gain=50,elevation_loss=45,raw_gps='secret'))
        self.session.cache.save_day('2026-10-22','rhr',dict(restingHeartRate=45))
        self.settings=dict(custom_range=True,custom_start='2026-10-01',target_route_id='test',target_gain_per_mile='60.0',target_loss_per_mile='60.0',password='secret')
    def snapshot(self):
        return self.session.route_review('2026-10-23',json.dumps(self.settings),'0.25.0','miles')['route_review']
    def test_all_history_profile_units_and_no_writes_or_downloads(self):
        self.session.client=Mock();before=self.session.cache.db.total_changes
        payload=self.snapshot()
        self.assertEqual([row['activityId'] for row in payload['activities']],['2','1'])
        self.assertEqual(payload['activities'][1]['activityType'],'running')
        self.assertEqual(payload['reference_recordings']['1']['profile'][-1],[1609.344,30.48,6.096])
        self.assertEqual(payload['routes'][0]['reference']['gain'],100)
        self.assertEqual(payload['units']['profile_elevation'],'metres')
        self.assertEqual(payload['units']['reference_elevation'],'feet')
        self.assertEqual(self.session.cache.db.total_changes,before)
        self.assertEqual(self.session.client.mock_calls,[])
        self.assertEqual(validate_review(payload),payload)
    def test_credentials_geographic_cells_and_unrelated_health_are_excluded(self):
        payload=self.snapshot();text=json.dumps(payload)
        for key in ('password','tokens','secret','cells','latitude','fingerprint','raw_gps','restingHeartRate'):
            self.assertNotIn(key,text)
        self.assertEqual(payload['outlines']['1']['segments'],[[[0,0],[1,.5]]])
        self.assertEqual(payload['details']['laps']['2']['lapDTOs'][0]['duration'],300)
        self.assertEqual(payload['details']['terrain_v1']['2']['elevation_gain'],50)
    def test_bridge_and_missing_cached_profile_need_no_client(self):
        self.session.cache.db.execute("DELETE FROM details WHERE kind='terrain_v1'")
        with patch.object(garmin_backend,'_session',self.session):
            response=json.loads(garmin_backend.call('route_review','2026-10-23',json.dumps(self.settings)))
        self.assertTrue(response['ok']);self.assertEqual(response['route_review']['reference_recordings'],{})
        self.assertIn('no cached elevation profile',report(response['route_review']))
    def test_report_compares_rates_and_surfaces_mismatch(self):
        payload=self.snapshot();rendered=report(payload)
        self.assertIn('Expected route averages: +60.0 / −60.0 ft/mi.',rendered)
        self.assertNotIn('does not match',rendered)
        payload['settings']['target_gain_per_mile']='1.0'
        self.assertIn('saved target_gain_per_mile does not match',report(payload))
    def test_contract_rejects_unexpected_or_malformed_data(self):
        payload=self.snapshot()
        for change in (
            lambda p:p.update(tokens='secret'),
            lambda p:p['reference_recordings']['1'].update(cells=[[40,-111]]),
            lambda p:p['reference_recordings']['1'].update(profile=[[0,0,float('nan')]]),
            lambda p:p['reference_recordings']['1'].update(profile=[[0,0,'bad']]),
            lambda p:p['reference_recordings']['1'].update(profile=[[0,0,0]]*2501),
            lambda p:p['reference_recordings'].update(bad=None),
            lambda p:p['outlines']['1'].update(segments=[[[40,-111]]]),
            lambda p:p['outlines']['1'].update(segments=[[None]])):
            bad=copy.deepcopy(payload);change(bad)
            with self.subTest(bad=change),self.assertRaises(ValueError):validate_review(bad)
    def test_receiver_token_one_use_and_private_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            server=ThreadingHTTPServer(('127.0.0.1',0),Receiver);server.daemon_threads=True
            server.token='x'*32;server.state={};server.lock=threading.Lock();server.destination=Path(directory)/'snapshot.json'
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(method,path,body=None):
                connection=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                try:
                    connection.request(method,path,body,{'Content-Type':'application/json'})
                    response=connection.getresponse();status=response.status;data=response.read()
                    return status,data
                finally:connection.close()
            try:
                body=json.dumps(self.snapshot())
                self.assertEqual(request('POST','/route-review/wrong',body)[0],403)
                self.assertEqual(request('POST','/route-review/'+server.token,'{"tokens":"secret"}')[0],400)
                self.assertFalse(server.destination.exists())
                self.assertEqual(request('GET','/routes/'+server.token)[0],200)
                self.assertEqual(request('POST','/route-review/'+server.token,body)[0],200)
                self.assertEqual(validate_review(json.loads(server.destination.read_text())),json.loads(body))
                self.assertEqual(server.destination.stat().st_mode & 0o777,0o600)
                self.assertEqual(request('POST','/route-review/'+server.token,body)[0],409)
            finally:server.shutdown();thread.join();server.server_close()


if __name__=='__main__':unittest.main()
