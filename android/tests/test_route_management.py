"""Custom routes and starter-route deletion persist without changing saved sessions."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
import garmin_backend
from garmin_backend import Session,InputError
from test_route_workouts import profile_fit


class RouteManagementTest(unittest.TestCase):
    def setUp(self):
        self.session=Session();self.addCleanup(self.session.cache.close)
        from terrain_fixture import elevations
        provider=patch('dashboard_sources.terrain.query_elevations',side_effect=elevations);provider.start();self.addCleanup(provider.stop)
        self.settings=json.dumps(dict(classification_mode='native',include_recovery=False,include_recordings=False,
            include_weather=False,include_station_weather=False,target_source='custom',target_time='20:00'))
        self.session.cache.save_window('2026-10-01','2026-10-21',[
            dict(activityId=1,activityName='Easy route reference',activityType='running',startTimeLocal='2026-10-20 06:00:00',distance=6000,duration=1800,averageHR=128),
            dict(activityId=2,activityName='Short intervals',activityType='running',startTimeLocal='2026-10-19 06:00:00',distance=8000,duration=2400,averageHR=145)])
        from dashboard_sources import terrain_summary
        self.session.cache.save_detail('1','terrain_v1',terrain_summary(profile_fit(),dict(activityType='running')))
    def create(self,name='Neighborhood loop'):
        return self.session.route_create(name,self.settings)['created_route_id']
    def book(self):return self.session.route_book(self.settings)['routes']
    def test_add_offline_keeps_starter_routes_and_gives_custom_route_independent_settings(self):
        identity=self.create('  Neighborhood loop  ')
        self.assertEqual(len(self.book()),5)
        route=next(r for r in self.book() if r['id']==identity)
        self.assertEqual(route['name'],'Neighborhood loop');self.assertEqual(route['shape'],'out_back')
        self.assertEqual(route['surface'],'road');self.assertFalse(route['reverse']);self.assertIsNone(route['reference'])
        self.session.route_configure(identity,json.dumps(dict(name='Trail loop',shape='loop',surface='trail')),self.settings)
        route=next(r for r in self.book() if r['id']==identity)
        self.assertEqual((route['name'],route['shape'],route['surface']),('Trail loop','loop','trail'))
        self.assertEqual(next(r for r in self.book() if r['id']=='liberty')['name'],'Liberty Park · SLC')
    def test_names_are_validated_and_duplicate_names_have_separate_ids(self):
        before=self.session.cache.db.total_changes
        for name in ('','  ','a'*101):
            with self.subTest(name=name),self.assertRaises(InputError):self.create(name)
        self.assertEqual(self.session.cache.db.total_changes,before)
        first=self.create();second=self.create()
        self.assertNotEqual(first,second)
        self.assertEqual(len([r for r in self.book() if r['name']=='Neighborhood loop']),2)
    def test_custom_route_browses_sessions_checks_matches_and_accepts_a_reference(self):
        identity=self.create()
        candidates=self.session.route_candidates_v2(identity,'2026-10-21',self.settings)['candidates']
        self.assertEqual([r['id'] for r in candidates],['1','2'])
        self.session.client=Mock();self.session.client.download_activity.return_value=profile_fit()
        self.session.route_reference(identity,'1','2026-10-21',self.settings)
        matches=self.session.route_matches(identity,'1','2026-10-21',self.settings)
        self.assertEqual(matches['original']['id'],'1');self.assertEqual(matches['remaining'],1)
        selected=self.session.route_use(identity,self.settings)['selection']
        self.assertEqual(selected['id'],identity);self.assertIn('gain_per_mile',selected)
        self.session.client.download_activity.assert_called_once()
    def test_deleting_route_keeps_its_reference_recording_and_shared_gps_index(self):
        first=self.create('First');second=self.create('Second')
        self.session.client=Mock();self.session.client.download_activity.return_value=profile_fit()
        for identity in (first,second):self.session.route_reference(identity,'1','2026-10-21',self.settings)
        self.session.cache.save_detail('1','route_match_v1',dict(cells=[[1,2],[2,3]],outline=dict(segments=[])))
        activities=self.session.cache.activities('2026-10-01','2026-10-21')
        details=list(self.session.cache.db.execute('SELECT id,kind,body FROM details ORDER BY id,kind'))
        result=self.session.route_delete(first,self.settings)
        self.assertEqual(result['deleted_route_id'],first)
        self.assertFalse(any(r['id']==first for r in result['routes']))
        self.assertEqual(self.session.cache.activities('2026-10-01','2026-10-21'),activities)
        self.assertEqual(list(self.session.cache.db.execute('SELECT id,kind,body FROM details ORDER BY id,kind')),details)
        self.assertEqual(self.session.route_use(second,self.settings)['selection']['id'],second)
    def test_deleting_all_routes_stays_empty_after_reopen_and_can_add_again(self):
        for route in self.book():self.session.route_delete(route['id'],self.settings)
        self.assertEqual(self.book(),[]);self.assertEqual(self.session.cache.meta('route_book_v2'),[])
        reopened=Session();self.addCleanup(reopened.cache.close);self.session.cache.db.backup(reopened.cache.db)
        self.assertEqual(reopened.route_book(self.settings)['routes'],[])
        added=reopened.route_create('New start',self.settings)
        self.assertEqual(len(added['routes']),1);self.assertEqual(added['routes'][0]['name'],'New start')
    def test_deleted_starter_routes_are_unavailable_to_picker_and_matching(self):
        self.session.route_delete('liberty',self.settings)
        with self.assertRaises(InputError):self.session.route_candidates_v2('liberty','2026-10-21',self.settings)
        with self.assertRaises(InputError):self.session.route_matches('liberty','1','2026-10-21',self.settings)
        with self.assertRaises(InputError):self.session.route_configure('liberty','{}',self.settings)
        with self.assertRaises(InputError):self.session.route_use('liberty',self.settings)
        before=self.session.cache.db.total_changes
        with self.assertRaises(InputError):self.session.route_delete('missing',self.settings)
        self.assertEqual(self.session.cache.db.total_changes,before)
    def test_create_and_delete_are_available_through_android_bridge(self):
        with patch.object(garmin_backend,'_session',self.session):
            added=json.loads(garmin_backend.call('route_create','Bridge route',self.settings))
            self.assertTrue(added['ok'])
            deleted=json.loads(garmin_backend.call('route_delete',added['created_route_id'],self.settings))
            self.assertTrue(deleted['ok']);self.assertEqual(len(deleted['routes']),4)


if __name__=='__main__':unittest.main()
