"""Fast discovery uses bounded GPS JSON; chosen elevation references still use FIT."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from garmin_backend import Session
from garminconnect.exceptions import GarminConnectTooManyRequestsError
from route_matching import from_details
from route_preview import project_route
from test_route_workouts import profile_fit


def details(length=30):
    return dict(geoPolylineDTO=dict(polyline=[dict(lat=40+i*.001,lon=-111) for i in range(length)]))


class PolylineIndexTest(unittest.TestCase):
    def test_relative_outline_and_coarse_cells_only(self):
        result=from_details(details())
        self.assertEqual(set(result),{'cells','outline'})
        self.assertEqual(len(result['cells']),30)
        self.assertTrue(result['outline']['segments'])
        self.assertNotIn('lat',json.dumps(result));self.assertNotIn('lon',json.dumps(result))
    def test_gaps_are_preserved_and_cells_are_bounded(self):
        body=details(4000)
        body['geoPolylineDTO']['polyline'][100]=None
        result=from_details(body)
        self.assertEqual(len(result['cells']),2000)
        self.assertEqual(len(result['outline']['segments']),2)
    def test_empty_no_gps_is_distinct_from_malformed_or_pending(self):
        for body in [dict(geoPolylineDTO=dict(polyline=[])),dict(geoPolylineDTO=None)]:
            self.assertEqual(from_details(body),dict(cells=[],outline=dict(segments=[])))
        for body in [{},None,dict(geoPolylineDTO=None,pendingData=True),dict(geoPolylineDTO=dict(polyline='encoded')),
                     dict(geoPolylineDTO=dict(polyline=[dict(lat=400,lon=200)])),
                     dict(geoPolylineDTO=dict(polyline=[dict(lat=True,lon=-111)]))]:
            with self.subTest(body=body),self.assertRaises(ValueError):from_details(body)


class FastRouteScanTest(unittest.TestCase):
    def setUp(self):
        self.session=Session();self.addCleanup(self.session.cache.close);self.session.client=Mock()
        self.activities=[dict(activityId=i,activityName='Easy '+str(i),activityType='running',
            startTimeLocal=f'2026-10-{i:02d} 06:00:00',distance=5000+i*1000,duration=1800+i*100) for i in range(1,10)]
        self.session.cache.save_window('2026-10-01','2026-10-21',self.activities)
        points=[(40+i*.001,-111) for i in range(10)]
        self.session.cache.save_detail('1','route_data_v1',dict(profile_version=2,profile=[[0,0,0],[6000,40,20]],
            cells=[[round(lat*1000),round(lon*1000)] for lat,lon in points]))
        self.session.cache.save_detail('1','route_outline_v1',project_route([points]))
        self.session.client.get_activity_details.return_value=details()
        self.session.client.download_activity.return_value=profile_fit()
        self.config=json.dumps(dict(classification_mode='native',include_recovery=False,include_recordings=False,
            include_weather=False,include_station_weather=False,target_source='custom',target_time='20:00'))
    def scan(self,progress=None,route='liberty'):
        return self.session.route_scan(route,'1','2026-10-21',self.config,progress)
    def test_scan_all_checks_more_than_five_using_only_small_details_requests(self):
        with patch.object(self.session,'_route_rows',wraps=self.session._route_rows) as catalog:
            result=self.scan()
        self.assertEqual(catalog.call_count,1)
        self.assertEqual(result['checked'],8);self.assertEqual(result['remaining'],0)
        self.assertEqual([r['id'] for r in result['candidates']],list(map(str,range(9,1,-1))))
        self.assertEqual([call.args[0] for call in self.session.client.get_activity_details.call_args_list],list(map(str,range(9,1,-1))))
        self.assertTrue(all(call.kwargs==dict(maxchart=1,maxpoly=2000) for call in self.session.client.get_activity_details.call_args_list))
        self.session.client.download_activity.assert_not_called()
        self.assertIsNone(self.session.cache.meta('route_book_v2'))
        for banned in ('"cells"','"profile"','"polyline"'):self.assertNotIn(banned,json.dumps(result))
    def test_progress_pause_and_resume_keeps_each_completed_check(self):
        class Progress:
            def __init__(self):self.checked=0;self.snapshots=[]
            def update(self,label,checked,total,result):
                self.checked=checked
                if result:self.snapshots.append(json.loads(result))
            def isCancelled(self):return self.checked>=3
        progress=Progress();result=self.scan(progress)
        self.assertTrue(result['paused']);self.assertEqual(result['checked'],3);self.assertEqual(result['remaining'],5)
        self.assertTrue(progress.snapshots)
        before=self.session.client.get_activity_details.call_count
        result=self.scan();self.assertEqual(result['remaining'],0)
        self.assertEqual(self.session.client.get_activity_details.call_count-before,5)
    def test_cancel_before_scanning_does_not_request_any_more_data(self):
        progress=Mock();progress.isCancelled.return_value=True
        result=self.scan(progress)
        self.assertTrue(result['paused']);self.session.client.get_activity_details.assert_not_called()
    def test_cached_checks_are_shared_between_routes_and_survive_a_new_session(self):
        self.scan();before=self.session.client.get_activity_details.call_count
        self.scan(route='bonneville');self.assertEqual(self.session.client.get_activity_details.call_count,before)
        second=Session();self.addCleanup(second.cache.close)
        self.session.cache.db.backup(second.cache.db)
        second.client=None
        result=second.route_matches('lakeview','1','2026-10-21',self.config)
        self.assertEqual(result['remaining'],0);self.assertEqual(len(result['candidates']),8)
    def test_connection_or_rate_limit_stops_and_keeps_successes(self):
        for error in (OSError('private'),GarminConnectTooManyRequestsError('private')):
            with self.subTest(error=type(error)):
                self.session.cache.db.execute("DELETE FROM details WHERE id!='1'");self.session.cache.db.commit()
                self.session.client.get_activity_details.side_effect=[details(),error]
                result=self.scan()
                self.assertEqual(result['checked'],1);self.assertEqual(result['remaining'],7)
                self.assertIsNotNone(result['scan_error']);self.assertNotIn('private',json.dumps(result))
        self.session.client.get_activity_details.side_effect=None
        self.assertEqual(self.scan()['remaining'],0)
    def test_thumbnail_and_reference_selection_never_download_terrain_or_full_fit(self):
        self.assertTrue(self.session.route_thumbnail('2')['route']['segments'])
        self.assertFalse(self.session.cache.detail('2','route_data_v1')[0])
        self.session.client.download_activity.assert_not_called()
        self.session.route_thumbnail('2');self.session.client.get_activity_details.assert_called_once()
        self.session.route_reference('liberty','2','2026-10-21',self.config)
        route=next(r for r in self.session.route_book(self.config)['routes'] if r['id']=='liberty')
        self.assertEqual(route['reference']['id'],'2');self.assertFalse(route['profile_ready'])
        from garmin_backend import InputError
        with self.assertRaisesRegex(InputError,'Sync now'):self.session.route_use('liberty',self.config)
        self.session.client.download_activity.assert_not_called()
    def test_no_gps_results_are_saved_but_malformed_responses_remain_retryable(self):
        self.session.client.get_activity_details.return_value=dict(geoPolylineDTO=dict(polyline=[]))
        self.assertEqual(self.scan()['remaining'],0)
        self.assertFalse(self.scan()['candidates'])
        self.session.cache.db.execute("DELETE FROM details WHERE id!='1'");self.session.cache.db.commit()
        self.session.client.get_activity_details.return_value={}
        result=self.scan();self.assertEqual(result['remaining'],8)
        self.assertFalse(self.session.cache.detail('9','route_match_v1')[0])
    def test_changed_recordings_invalidate_index_and_signout_clears_it(self):
        self.scan();changed=copy.deepcopy(self.activities);changed[-1]['distance']+=1000
        self.session.cache.save_window('2026-10-01','2026-10-21',changed)
        self.assertFalse(self.session.cache.detail('9','route_match_v1')[0])
        self.session.logout();self.assertFalse(self.session.cache.all_details('route_match_v1'))
    def test_reusable_gps_indexes_do_not_enter_comparison_exports(self):
        self.scan()
        encoded=json.dumps(self.session.comparison('2026-10-21',30,self.config)['comparison'])
        for banned in ('route_match_v1','"cells"','geoPolylineDTO','"outline"','"polyline"'):
            self.assertNotIn(banned,encoded)
    def test_live_updates_keep_small_payloads_and_final_result_contains_every_match(self):
        activities=[dict(activityId=i,activityName='Easy '+str(i),activityType='running',
            startTimeLocal=f'2026-10-{i:02d} 06:00:00',distance=5000+i*1000,duration=1800+i*100) for i in range(1,21)]
        self.session.cache.save_window('2026-10-01','2026-10-21',activities)
        class Progress:
            def __init__(self):self.snapshots=[]
            def update(self,label,checked,total,result):
                if result:self.snapshots.append(json.loads(result))
            def isCancelled(self):return False
        progress=Progress();result=self.scan(progress)
        self.assertEqual(result['match_count'],19);self.assertEqual(len(result['candidates']),19)
        self.assertTrue(all(len(item['candidates'])<=10 for item in progress.snapshots))
        self.assertGreater(progress.snapshots[-1]['match_count'],10)


if __name__=='__main__':unittest.main()
