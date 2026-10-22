"""Synthetic GPS only: projection, recording gaps, caching, and export boundaries."""
import io
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import Mock
import zipfile
from fitdecode.utils import compute_crc

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from route_preview import project_route,route_from_original,thumbnail_route
from garmin_backend import Session
from fit_fixture import recording


def gps_recording(points,zipped=True):
    # FIT record with timestamp and signed semicircle latitude/longitude.
    body=b'\x40\x00\x00'+struct.pack('<H',20)+b'\x03\xfd\x04\x86\x00\x04\x85\x01\x04\x85'
    for i,point in enumerate(points):
        lat,lon=(0x7fffffff,0x7fffffff) if point is None else (round(point[0]*2**31/180),round(point[1]*2**31/180))
        body+=b'\x00'+struct.pack('<Iii',900000000+i*10,lat,lon)
    data=struct.pack('<BBHI4s',12,16,21171,len(body),b'.FIT')+body
    data+=struct.pack('<H',compute_crc(data))
    if not zipped:return data
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:archive.writestr('synthetic.fit',data)
    return out.getvalue()


class RoutePreviewTest(unittest.TestCase):
    def test_raw_and_zipped_fit_match_with_north_up_and_aspect_preserved(self):
        points=[(40,-111),(40.001,-111),(40.001,-110.999)]
        first=route_from_original(gps_recording(points))
        self.assertEqual(first,route_from_original(gps_recording(points,False)))
        a,b,c=first['segments'][0]
        self.assertGreater(a[1],b[1])
        self.assertGreater(c[0],b[0])
        self.assertAlmostEqual(c[0]-b[0],.766,places=3)
        self.assertEqual(set(first),{'segments'})
        self.assertTrue(all(0<=value<=1 for point in first['segments'][0] for value in point))

    def test_missing_gps_creates_separate_paths(self):
        points=[(40,-111),(40.001,-111),None,(40.002,-111),(40.003,-111)]
        self.assertEqual(len(route_from_original(gps_recording(points))['segments']),2)

    def test_indoor_empty_and_stationary_recordings_have_no_outline(self):
        self.assertEqual(route_from_original(recording([(0,0),(1000,300)])),{'segments':[]})
        self.assertEqual(route_from_original(gps_recording([(40,-111)]*4)),{'segments':[]})
        self.assertEqual(project_route([]),{'segments':[]})

    def test_dateline_crossing_keeps_a_local_route(self):
        outline=project_route([[(0,179.99),(.01,-179.99)]])['segments'][0]
        self.assertAlmostEqual(outline[-1][0]-outline[0][0],1)
        self.assertAlmostEqual(outline[0][1]-outline[-1][1],.5,places=3)

    def test_preview_is_bounded_and_preserves_endpoints(self):
        points=[(40+i*.000001,-111+i*.000001) for i in range(10000)]
        outline=project_route([points])['segments'][0]
        self.assertLessEqual(len(outline),1000)
        self.assertAlmostEqual(outline[0][1],1)
        self.assertAlmostEqual(outline[-1][1],0)

    def test_list_thumbnail_keeps_gaps_endpoints_and_bounded_relative_points(self):
        source=dict(segments=[[[i/999,1-i/999] for i in range(1000)],[[.2,.3],[.4,.5]]])
        outline=thumbnail_route(source)
        self.assertEqual(len(outline['segments']),2)
        self.assertLessEqual(sum(map(len,outline['segments'])),100)
        for before,after in zip(source['segments'],outline['segments']):
            self.assertEqual(before[0],after[0]);self.assertEqual(before[-1],after[-1])
        self.assertEqual(len(source['segments'][0]),1000)
        self.assertEqual(thumbnail_route(None),dict(segments=[]))

    def test_corrupt_recording_raises_without_caching_an_empty_route(self):
        session=Session();self.addCleanup(session.cache.close);session.client=Mock()
        session.client.download_activity.return_value=b'not a recording'
        with self.assertRaises(Exception):session.route('1')
        self.assertFalse(session.cache.detail('1','route_outline_v1')[0])

    def test_route_cache_supports_offline_reopen_and_logout_clears_it(self):
        session=Session();self.addCleanup(session.cache.close);session.client=Mock()
        session.client.download_activity.return_value=gps_recording([(40,-111),(40.001,-111)])
        expected=session.route('1')['route']
        session.client.download_activity.assert_called_once()
        session.client=None
        self.assertEqual(session.route('1')['route'],expected)
        self.assertNotIn('111',json.dumps(expected))
        session.logout()
        self.assertFalse(session.cache.detail('1','route_outline_v1')[0])

    def test_no_gps_result_is_cached_without_repeat_downloads(self):
        session=Session();self.addCleanup(session.cache.close);session.client=Mock()
        session.client.download_activity.return_value=recording([(0,0),(1000,300)])
        for _ in range(2):self.assertEqual(session.route('1')['route'],{'segments':[]})
        session.client.download_activity.assert_called_once()

    def test_outlines_are_excluded_from_comparison_exports(self):
        from comparison_contract import sanitize_snapshot
        result=sanitize_snapshot(dict(schema=1,activities=[],android={},selection=dict(today='2026-10-21',settings={}),
            details=dict(route_outline_v1={'1':{'segments':[[[0,1],[1,0]]]}})))
        self.assertNotIn('route_outline_v1',result.get('details',{}))


if __name__=='__main__':unittest.main()
