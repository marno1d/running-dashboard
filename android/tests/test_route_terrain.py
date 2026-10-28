"""Downloaded terrain, winding retraces, loop averaging and relative course previews."""
import math
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from route_terrain import build,geometry,display_track,ready,retune
from route_workouts import average_rates
from garmin_backend import Session,InputError
from test_route_workouts import profile_fit
from terrain_fixture import elevations


def gps_path(vertices):
    points=[];distance=0
    for a,b in zip(vertices,vertices[1:]):
        length=math.dist(a,b);steps=max(1,math.ceil(length/20))
        for i in range(steps):
            f=i/steps;x=a[0]+(b[0]-a[0])*f;y=a[1]+(b[1]-a[1])*f
            points.append(dict(distanceMeters=distance+length*f,lat=40+y/111195,lng=-111+x/(111195*math.cos(math.radians(40)))))
        distance+=length
    x,y=vertices[-1];points.append(dict(distanceMeters=distance,lat=40+y/111195,lng=-111+x/(111195*math.cos(math.radians(40)))))
    return points


class RouteTerrainTest(unittest.TestCase):
    def test_downloaded_heights_preserve_shallow_hills_and_match_session_policy(self):
        route=gps_path([(0,0),(400,0)])
        points=[dict(distanceMeters=i*100,elevationMeters=h) for i,h in enumerate([100,102,100,102,100])]
        result=build(points,route,'opentopodata:ned10m,srtm30m')
        self.assertEqual(result['profile'][-1],[400,4,4]);self.assertTrue(ready(result))
        self.assertEqual(result['heights'],[[0,100],[100,102],[200,100],[300,102],[400,100]])
        self.assertFalse(ready(dict(profile_version=2,profile=result['profile'])))
        self.assertNotIn('lat',str(result));self.assertNotIn('lng',str(result))
    def test_incomplete_terrain_cannot_silently_fall_back_to_watch_or_bridge_a_gap(self):
        for heights in ([100,None,102],[None,None],[]):
            with self.subTest(heights=heights),self.assertRaises(ValueError):
                build([dict(distanceMeters=i*100,elevationMeters=h) for i,h in enumerate(heights)],[],'opentopodata:test')
    def test_winding_route_uses_retrace_instead_of_farthest_radial_point(self):
        outward=[(0,0),(1000,0),(1000,1000),(400,400)]
        points=gps_path(outward+list(reversed(outward[:-1])))
        result=geometry(points);half=points[-1]['distanceMeters']/2
        self.assertEqual(result['turn_confidence'],'retrace');self.assertAlmostEqual(result['suggested_turn'],half,delta=25)
        self.assertGreater(result['suggested_turn'],2000)
    def test_one_way_and_loop_paths_do_not_claim_a_verified_turnaround(self):
        loop=[(500*math.sin(i*math.pi/40),500*(1-math.cos(i*math.pi/40))) for i in range(81)]
        for vertices in ([(0,0),(3000,0)],loop):
            result=geometry(gps_path(vertices))
            self.assertIsNone(result['suggested_turn']);self.assertEqual(result['turn_confidence'],'review')
    def test_repeated_out_and_backs_choose_a_real_turn_not_the_return_to_start(self):
        result=geometry(gps_path([(0,0),(3000,0),(0,0),(3000,0),(0,0)]))
        self.assertAlmostEqual(result['suggested_turn'],3000,delta=25)
        self.assertAlmostEqual(result['suggested_reverse_turn'],3000,delta=25)
    def test_long_retrace_ranks_alignment_instead_of_earliest_within_tolerance(self):
        data=geometry(gps_path([(0,0),(7500,0),(0,0)]))
        self.assertAlmostEqual(data['suggested_turn'],7500,delta=1)
        # Simulate a v0.26.0 cache: refine locally, preserving all terrain samples.
        legacy=dict(data,geometry_version=1,suggested_turn=7460,profile=[[0,0,0],[15000,20,20]],heights=[[0,100],[15000,100]])
        legacy.pop('metres_per_unit')
        refined=retune(legacy)
        self.assertAlmostEqual(refined['suggested_turn'],7500,delta=1)
        self.assertIs(refined['profile'],legacy['profile']);self.assertIs(refined['heights'],legacy['heights'])
        self.assertEqual(legacy['suggested_turn'],7460)
        self.assertIs(retune(refined),refined)
    def test_relative_track_and_reverse_have_monotone_distances(self):
        result=geometry(gps_path([(0,0),(1000,0),(0,0)]));result['profile']=[[0,0,0],[2000,10,10]]
        for reverse in (False,True):
            track=display_track(result,reverse)
            self.assertEqual(track[0][0],0);self.assertEqual(track[-1][0],2000)
            self.assertTrue(all(0<=v<=1 for p in track for v in p[1:]))
            self.assertTrue(all(a[0]<b[0] for a,b in zip(track,track[1:])))
    def test_loop_averages_all_complete_laps_and_balances_closed_course(self):
        data=dict(profile=[[0,0,0],[1000,6,3],[2000,12,12],[3000,15,15],[3500,45,15]])
        result=average_rates(dict(shape='loop',extent=1000),data)
        rate=round(5/.3048/(1000/1609.344),1)
        self.assertEqual(result,dict(gain_per_mile=rate,loss_per_mile=rate))


class TerrainReferenceCacheTest(unittest.TestCase):
    def setUp(self):
        self.session=Session();self.addCleanup(self.session.cache.close)
        self.session.cache.save_window('2026-10-01','2026-10-23',[dict(activityId=1,activityName='Reference',startTimeLocal='2026-10-22 06:00:00',activityType='running',distance=12000,duration=3600)])
        fingerprint=self.session.cache.db.execute("SELECT fingerprint FROM runs WHERE id='1'").fetchone()[0]
        self.route=dict(id='lakeview',name='Lakeview',shape='out_back',surface='road',reverse=False,extent=4000,
            reference=dict(id='1',title='Reference',date='2026-10-22',distance=12000,duration=3600,fingerprint=fingerprint))
        self.session.cache.save_meta('route_book_v2',[self.route]);self.settings='{}'
        # Deliberately unrelated watch totals must never reach route conditions.
        self.session.cache.save_detail('1','route_data_v1',dict(profile_version=2,profile=[[0,0,0],[12000,9999,9999]],cells=[[1,1],[2,2]]))
        self.session.cache.save_detail('1','terrain_v1',dict(status='ok',source='opentopodata:synthetic',elevation_gain=17,elevation_loss=18))
        self.session.client=Mock();self.session.client.download_activity.return_value=profile_fit()
        self.provider=patch('dashboard_sources.terrain.query_elevations',side_effect=elevations).start();self.addCleanup(patch.stopall)
    def test_old_totals_rebuild_once_and_reopen_reuses_complete_terrain_without_network(self):
        self.assertFalse(self.session.route_book(self.settings)['routes'][0]['profile_ready'])
        self.session.sync_terrain('2026-10-23',30,self.settings)
        first=self.session.route_use('lakeview',self.settings)['selection']
        self.assertEqual(first['extent'],3000);self.assertTrue(first['elevation_source'].startswith('opentopodata:'))
        self.assertLess(first['gain_per_mile'],1000)
        self.session.client.download_activity.assert_called_once()
        calls=self.provider.call_count;self.assertGreater(calls,0)
        reopened=Session();self.addCleanup(reopened.cache.close);self.session.cache.db.backup(reopened.cache.db)
        self.assertEqual(reopened.route_use('lakeview',self.settings)['selection'],first)
        self.assertEqual(self.provider.call_count,calls)
        data=reopened.cache.detail('1','terrain_v1')[1]['route']
        self.assertTrue(data['heights']);self.assertTrue(data['track'])
        self.assertNotIn('lat',str(data));self.assertNotIn('lng',str(data))
    def test_failed_terrain_keeps_existing_totals_and_configuration_and_rejects_watch_fallback(self):
        before=self.session.cache.meta('route_book_v2');self.provider.side_effect=OSError('private provider details')
        self.session.sync_terrain('2026-10-23',30,self.settings)
        with self.assertRaisesRegex(InputError,'Sync now'):
            self.session.route_use('lakeview',self.settings)
        self.assertEqual(self.session.cache.meta('route_book_v2'),before)
        self.assertEqual(self.session.cache.detail('1','terrain_v1')[1],dict(status='ok',source='opentopodata:synthetic',elevation_gain=17,elevation_loss=18))
        self.assertFalse(self.session.route_book(self.settings)['routes'][0]['profile_ready'])
    def test_explicit_turnaround_survives_reopen_and_suggestion_changes(self):
        self.session.sync_terrain('2026-10-23',30,self.settings)
        self.session.route_configure('lakeview',json.dumps(dict(extent=4500)),self.settings)
        cached=self.session.cache.detail('1','terrain_v1')[1];cached['route']['suggested_turn']=2500
        self.session.cache.save_detail('1','terrain_v1',cached)
        selected=self.session.route_use('lakeview',self.settings)['selection']
        self.assertEqual(selected['extent'],4500)
        self.session.client.download_activity.assert_called_once()
    def test_pending_reference_can_be_selected_but_routes_never_start_downloads(self):
        self.session.route_reference('lakeview','1','2026-10-23',self.settings)
        route=self.session.route_book(self.settings)['routes'][0]
        self.assertFalse(route['profile_ready']);self.assertEqual(route['reference']['id'],'1')
        with self.assertRaisesRegex(InputError,'Sync now'):self.session.route_use('lakeview',self.settings)
        self.session.client.download_activity.assert_not_called();self.provider.assert_not_called()
    def test_old_applied_watch_rates_are_blocked_until_route_is_selected_again(self):
        settings=dict(target_route_id='lakeview',target_route_engine=3,target_gain_per_mile=900,target_loss_per_mile=900,
            include_recovery=False,include_recordings=False,include_weather=False,include_station_weather=False)
        targets=self.session.cached_dashboard('2026-10-23',30,json.dumps(settings))['targets']
        self.assertIn('load downloaded terrain',targets['route_error'])
        self.session.client.download_activity.assert_not_called()


if __name__=='__main__':unittest.main()
