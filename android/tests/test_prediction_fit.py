"""Forecasts use only earlier trials and frozen, comparable workout effort."""
from datetime import date,timedelta
import math
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from dashboard_metrics import predictions


def workout(day,kind='short',pace=250,hr=160,hour='06',surface='running'):
    day=(date(2026,1,1)+timedelta(days=day)).isoformat()
    return dict(id=day+kind+hour,date=day,started=day+' '+hour+':00:00',category=kind,
                activity_type=surface,pace=pace,average_hr=hr,work_pace=pace,work_hr=hr,
                distance=6000,duration=pace*6)


def trial(day,seconds=1080):
    row=workout(day,'trial',seconds/5,175,hour='09')
    row['best_5k']=dict(duration=seconds)
    return row


class PredictionFitTest(unittest.TestCase):
    def history(self):
        return [workout(i) for i in (1,3,5)]+[trial(8)]+[workout(i) for i in (10,12,14)]

    def test_first_trial_anchors_the_estimate_and_latest_trial_replaces_it(self):
        rows=self.history()
        first=predictions(rows,{},{} )[0]
        self.assertEqual(first[0]['id'],rows[3]['id'])
        self.assertTrue(all(p['duration']==1080 for p in first))
        rows+=[trial(16,1140)]
        new=predictions(rows,{},{} )[0]
        self.assertEqual(new[:-1],first)
        self.assertEqual(new[-1]['duration'],1140)
        self.assertEqual(new[-1]['calibrations'],2)

    def test_future_trials_workouts_health_and_max_hr_cannot_rewrite_history(self):
        rows=self.history();old=predictions(rows,{},{} )
        future=[workout(17,pace=200,hr=150),workout(18,pace=400,hr=190),trial(20,900)]
        new=predictions(rows+future,dict(max_hr=183),{'2026-02-01':dict(resting_hr=99)})
        cutoff=rows[-1]['started']
        for before,after in zip(old,new):
            self.assertEqual(before,[p for p in after if p['started']<=cutoff])
        self.assertEqual(old,predictions(rows,dict(max_hr=191),{}))

    def test_lower_effort_and_proportionally_slower_pace_do_not_imply_lost_fitness(self):
        rows=self.history()[:4]+[workout(i,pace=250*math.exp(.0075*8),hr=152) for i in (10,12,14)]
        normalized=predictions(rows,{},{} )[0][-1]
        observed=predictions(rows,dict(prediction_mode='observed'),{} )[0][-1]
        self.assertAlmostEqual(normalized['duration'],1080)
        self.assertGreater(observed['duration'],1140)
        self.assertTrue(normalized['hr_normalized'])
        self.assertEqual(predictions(rows,{},{}),predictions(rows,dict(prediction_mode='intensity'),{}))

    def test_workout_types_are_compared_with_their_own_trial_baselines(self):
        rows=[workout(1,'short',250),workout(2,'long',290),trial(4)]
        rows += [workout(i,'short',250) for i in (10,20,30)]
        self.assertTrue(all(abs(p['duration']-1080)<1e-8 for p in predictions(rows,{},{} )[0]))

    def test_easy_uses_actual_road_runs_and_one_trial_with_four_nearby_runs(self):
        rows=[workout(i,'easy',320,128) for i in (1,2,3,4)]+[trial(5)]
        self.assertEqual(predictions(rows,{},{} )[1][-1]['duration'],1080)
        self.assertEqual(predictions([r for r in rows if r['date']!='2026-01-02'],{},{} )[1],[])
        for row in rows:row['activity_type']='trail_running'
        self.assertEqual(predictions(rows,{},{} )[1],[])

    def test_extreme_hr_extrapolation_is_excluded_and_missing_anchor_hr_is_labeled(self):
        rows=self.history()[:4]+[workout(i,pace=200,hr=110) for i in (10,12,14)]
        self.assertNotEqual(predictions(rows,{},{} )[0][-1]['id'],rows[-1]['id'])
        for row in rows:row['work_hr']=None
        self.assertFalse(predictions(rows,{},{} )[0][-1]['hr_normalized'])

    def test_same_day_workouts_after_a_trial_do_not_establish_its_baseline(self):
        rows=[workout(5,hour='10'),trial(5)]
        points=predictions(rows,{},{} )[0]
        self.assertEqual(len(points),1)
        self.assertEqual(points[0]['samples'],0)
        self.assertEqual(points[0]['duration'],1080)
        rows[0]['started']=rows[1]['started']
        self.assertEqual(predictions(rows,{},{} )[0][0]['samples'],0)

    def test_short_display_range_keeps_prior_anchor_and_reports_its_age(self):
        rows=self.history()+[workout(110)]
        latest=predictions([rows[-1]],{}, {},rows)[0]
        self.assertEqual(len(latest),1)
        self.assertEqual(latest[0]['anchor_age_days'],102)
        self.assertEqual(latest[0]['anchor_date'],rows[3]['date'])


if __name__=='__main__':unittest.main()
