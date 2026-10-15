import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/src/main/python'))
from best_effort import fastest_5k, best_from_original
from fit_fixture import recording


class BestEffortTest(unittest.TestCase):
    def test_warmup_and_cooldown_excluded(self):
        result=best_from_original(recording([(0,0),(2000,900),(7000,2000),(8000,2600)]))
        self.assertEqual(result['duration'],1100)
        self.assertEqual(result['start_distance'],2000)
        self.assertEqual(result['end_distance'],7000)

    def test_finish_aligned_window_requires_interpolated_start(self):
        result=fastest_5k([(0,0),(1000,500),(5500,1400),(6500,2400)])
        self.assertEqual(result['duration'],1150)
        self.assertEqual(result['start_distance'],500)
        self.assertEqual(result['start_elapsed'],250)

    def test_pauses_inside_count_and_boundary_pauses_do_not(self):
        result=fastest_5k([(0,0),(0,100),(2500,600),(2500,660),(5000,1160),(5000,1200)])
        self.assertEqual(result['duration'],1060)
        self.assertEqual(result['start_elapsed'],100)
        self.assertEqual(result['end_elapsed'],1160)

    def test_short_recording_not_extrapolated(self):
        self.assertIsNone(best_from_original(recording([(0,0),(4999,1000)])))
        self.assertIsNone(fastest_5k([]))

    def test_resets_not_stitched_into_false_5k(self):
        self.assertIsNone(fastest_5k([(0,0),(3000,600),(0,700),(3000,1300)]))
        self.assertIsNone(fastest_5k([(0,0),(3000,600),(4000,600),(6000,1200)]))

    def test_raw_fit_and_corruption(self):
        raw=recording([(0,0),(5000,1000)],False)
        self.assertEqual(best_from_original(raw)['duration'],1000)
        with self.assertRaises(Exception):best_from_original(raw[:-2]+b'\x00\x00')

    def test_exact_minimum_matches_dense_reference(self):
        samples=[(0,0),(400,200),(1900,550),(4900,1100),(6500,1800),(9000,2400)]
        result=fastest_5k(samples)
        def time_at(d):
            for (d0,t0),(d1,t1) in zip(samples,samples[1:]):
                if d0<=d<=d1:return t0+(t1-t0)*(d-d0)/(d1-d0)
        brute=min(time_at(x+5000)-time_at(x) for x in range(4001))
        self.assertAlmostEqual(result['duration'],brute)
