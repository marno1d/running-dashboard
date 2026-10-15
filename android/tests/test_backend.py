import importlib.util
import json
from pathlib import Path
import unittest
from datetime import date
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app/src/main/python"))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"common"))
from training import category, pace_seconds, work_intervals, session_average, normalized_runs, history_start
from unittest.mock import Mock, patch
from fit_fixture import recording

spec = importlib.util.spec_from_file_location('backend', Path(__file__).resolve().parents[1] / 'app/src/main/python/garmin_backend.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class BackendTest(unittest.TestCase):
    def test_last_seven_calendar_days_and_duplicate_filter(self):
        def run(identity, day, title='Morning run'):
            return {'activityId': identity, 'startTimeLocal': day + ' 06:30:00', 'activityName': title}
        result = backend.run_titles([run(1,'2026-10-01'),run(2,'2026-09-30'),run(3,'2026-10-06'),
                                     run(4,'2026-10-07'),run(3,'2026-10-06'),run(5,'garbled')], '2026-10-06')
        self.assertEqual(result['start'],'2026-09-30')
        self.assertEqual([run['id'] for run in result['runs']],['3','1','2'])

    def test_mfa_retry_and_password_removed(self):
        session = backend.Session()
        fake = Mock()
        fake.login.return_value = ('needs_mfa',None)
        with patch.object(backend,'Garmin',return_value=fake) as factory:
            self.assertTrue(session.login('me@example.com','secret')['needs_mfa'])
            factory.assert_called_once_with(email='me@example.com',password='secret',return_on_mfa=True,retry_attempts=1)
        self.assertIsNone(fake.password)
        fake.client.resume_login.side_effect = backend.GarminConnectAuthenticationError('bad code')
        with self.assertRaises(backend.GarminConnectAuthenticationError): session.verify('000000')
        self.assertIs(session.pending,fake)
        fake.client.resume_login.side_effect = None
        self.assertTrue(session.verify('123456')['authenticated'])
        self.assertIsNone(session.pending)

    def test_running_filter_and_empty_week(self):
        session = backend.Session()
        session.client = Mock()
        session.client.get_activities_by_date.return_value = []
        result = session.runs('2026-01-02')
        session.client.get_activities_by_date.assert_called_once_with('2025-12-27','2026-01-02',activitytype='running')
        self.assertEqual(result['runs'],[])

    def test_saved_state_contains_only_tokens(self):
        session = backend.Session()
        session.client = Mock()
        session.client.client.dumps.return_value = '{"di_token":"access","di_refresh_token":"refresh","di_client_id":"id"}'
        self.assertNotIn('password',session.tokens())
        session.logout()
        self.assertIsNone(session.tokens())

    def test_library_error_details_never_cross_bridge(self):
        with patch.object(backend._session,'login',side_effect=backend.GarminConnectConnectionError('ticket=SECRET')):
            result=json.loads(backend.call('login','me@example.com','password'))
        self.assertFalse(result['ok'])
        self.assertNotIn('SECRET',json.dumps(result))


class TrainingTest(unittest.TestCase):
    def test_title_classification_does_not_assume_5k_is_a_trial(self):
        self.assertEqual(category('NSM Easy 40'), 'easy')
        self.assertEqual(category('NSM Short intervals'), 'short')
        self.assertEqual(category('NSM Medium'), 'medium')
        self.assertEqual(category('Long intervals'), 'long')
        self.assertEqual(category('5k TT'), 'trial')
        self.assertEqual(category('5k time trial'), 'trial')
        self.assertEqual(category('City 5k run'), 'other')
        self.assertEqual(category('Long run'), 'other')

    def test_pace_units_and_invalid_data(self):
        self.assertEqual(pace_seconds({'duration':300,'distance':1000}),300)
        self.assertEqual(pace_seconds({'averageSpeed':4}),250)
        self.assertIsNone(pace_seconds({'distance':0,'duration':50}))
        self.assertIsNone(pace_seconds({'averageSpeed':float('nan')}))
        self.assertIsNone(pace_seconds({'averageSpeed':float('inf')}))

    def test_only_explicit_work_laps_and_weighted_session_pace(self):
        run={'id':'42','title':'Short intervals','category':'short','date':'2026-10-06'}
        laps={'lapDTOs':[
            {'intensityType':'WARMUP','distance':1000,'duration':400},
            {'intensityType':'ACTIVE','distance':200,'duration':40},
            {'intensityType':'REST','distance':100,'duration':80},
            {'intensityType':'ACTIVE','distance':400,'duration':100},
            {'intensityType':'COOLDOWN','distance':1000,'duration':400},
        ]}
        points=work_intervals(run,laps)
        self.assertEqual([p['lap'] for p in points],[2,4])
        self.assertEqual([p['pace'] for p in points],[200,250])
        self.assertAlmostEqual(session_average(points)[0]['pace'],140/600*1000)
        self.assertEqual(session_average(points)[0]['reps'],2)

    def test_unlabeled_laps_need_user_selection(self):
        run={'id':'42','title':'Short intervals','category':'short','date':'2026-10-06'}
        laps={'lapDTOs':[{'distance':200,'duration':40},{'distance':200,'duration':100}]}
        self.assertEqual(work_intervals(run,laps),[])
        self.assertEqual(work_intervals(run,laps,{0})[0]['pace'],200)

    def test_dashboard_separates_panels_and_reuses_splits(self):
        session=backend.Session();session.client=Mock()
        session.client.connectapi.side_effect=[[
            {'activityId':1,'activityName':'Easy run','startTimeLocal':'2026-10-06 06:00:00','distance':6000,'duration':2400},
            {'activityId':2,'activityName':'Short intervals','startTimeLocal':'2026-10-05 06:00:00','distance':6000,'duration':2400},
            {'activityId':3,'activityName':'5K TT','startTimeLocal':'2026-10-04 06:00:00','distance':5000,'duration':1200},
        ], []]
        session.client.get_activity_splits.return_value={'lapDTOs':[{'intensityType':'ACTIVE','distance':200,'duration':40}]}
        session.client.download_activity.return_value=recording([(0,0),(5000,1200)])
        result=session.dashboard('2026-10-06',90,'{}')
        self.assertEqual([p['id'] for p in result['run_points']],['1'])
        self.assertEqual([p['id'] for p in result['interval_points']],['2'])
        self.assertEqual([p['duration'] for p in result['trial_points']],[1200])
        session.dashboard('2026-10-06',90,'{}')
        self.assertEqual(session.client.connectapi.call_count,2)
        self.assertEqual(session.client.get_activity_splits.call_count,1)

    def test_trial_uses_fastest_recorded_5k_and_ignores_lap_override(self):
        session=backend.Session();session.client=Mock()
        session.client.connectapi.side_effect=[[dict(activityId=1,activityName='5K TT',startTimeLocal='2026-10-06 06:00:00',distance=8000,duration=2400)],[]]
        session.client.download_activity.return_value=recording([(0,0),(3000,1200),(8000,2400)])
        result=session.dashboard('2026-10-06',90,'{}')
        self.assertEqual(result['trial_points'][0]['duration'],1200)
        self.assertEqual(result['trial_points'][0]['distance'],5000)
        self.assertEqual(result['trial_points'][0]['start_distance'],3000)
        self.assertEqual(result['runs'][0]['duration'],2400)
        session.dashboard('2026-10-06',90,'{"laps":{"1":[0]}}')
        self.assertEqual(session.client.download_activity.call_count,1)
        session.client.get_activity_splits.assert_not_called()

    def test_trial_missing_recording_has_no_whole_activity_fallback(self):
        session=backend.Session();session.client=Mock()
        session.client.connectapi.side_effect=[[dict(activityId=1,activityName='5K TT',startTimeLocal='2026-10-06 06:00:00',distance=5000,duration=1200)],[]]
        session.client.download_activity.return_value=recording([(0,0),(4999,1200)])
        result=session.dashboard('2026-10-06',90,'{}')
        self.assertEqual(result['trial_points'],[])
        self.assertEqual(result['missing_trials'],1)
        self.assertIn('trial_error',result['runs'][0])
        session.client.download_activity.side_effect=backend.GarminConnectConnectionError('offline')
        session.client.connectapi.side_effect=[[dict(activityId=1,activityName='5K TT',startTimeLocal='2026-10-06 06:00:00')],[]]
        self.assertEqual(session.dashboard('2026-10-06',90,'{}',True)['missing_trials'],1)
        self.assertNotIn('1',session.efforts)

    def test_easy_hr_suggestions_borderline_hard_workouts_and_overrides(self):
        activities = [dict(activityId=i, activityName=title,
                           startTimeLocal='2026-10-06 06:00:00', averageHR=hr,
                           maxHR=150, distance=5000, duration=1800)
                      for i, title, hr in [(1, 'Morning Running', 133),
                          (2, 'Morning Running', 134), (3, 'Morning Running', None),
                          (4, 'Taper Intervals', 120), (5, 'Long intervals', 120),
                          (6, 'Morning Running', 140), (7, 'Morning Running', 120)]]
        rows = {r['id']: r for r in normalized_runs(activities, '2026-10-06', 90,
                                                  {'6': 'easy', '7': 'other'})['runs']}
        self.assertEqual([rows[str(i)]['category'] for i in range(1,8)],
                         ['easy','other','other','other','long','easy','other'])
        self.assertEqual(rows['1']['category_reason'], 'average_hr')
        self.assertEqual(rows['1']['max_hr'], 150)
        self.assertTrue(rows['1']['hr_below_target'])
        self.assertEqual(rows['6']['category_reason'], 'manual')

    def test_auto_laps_combine_within_a_repeat_but_recovery_separates(self):
        run = dict(id='1', title='Long intervals', date='2026-10-06', category='long')
        laps = {'lapDTOs': [dict(intensityType=t, distance=d, duration=s)
                 for t,d,s in [('WARMUP',1609,600),('ACTIVE',1609,400),
                              ('ACTIVE',700,175),('REST',100,60),
                              ('ACTIVE',1609,410),('ACTIVE',700,180)]]}
        points = work_intervals(run,laps)
        self.assertEqual(len(points),2)
        self.assertEqual(points[0]['distance'],2309)
        self.assertEqual(points[0]['duration'],575)
        self.assertEqual(points[0]['lap'],2)
        self.assertEqual(points[0]['last_lap'],3)
        self.assertEqual(len(work_intervals(run,laps,{1,2,4,5})),4)

    def test_refresh_progress_and_failed_download_preserves_cache(self):
        session=backend.Session(); session.client=Mock(); progress=Mock()
        row=dict(activityId=1,activityName='Easy run',startTimeLocal='2026-10-06 06:00:00',distance=5000,duration=1800)
        session.client.connectapi.side_effect=[[row],[]]
        session.dashboard('2026-10-06',90,'{}',True,progress)
        labels=[args.args[0] for args in progress.update.call_args_list]
        self.assertTrue(any('Checked 1 run summaries' in label for label in labels))
        self.assertTrue(labels[-1].startswith('Charts ready'))
        session.client.connectapi.side_effect=backend.GarminConnectConnectionError('offline')
        with self.assertRaises(backend.GarminConnectConnectionError):
            session.dashboard('2026-10-06',90,'{}',True,progress)
        self.assertEqual(session.dashboard('2026-10-06',90,'{}')['run_points'][0]['id'],'1')

    def test_sample_prioritizes_old_trial_within_year(self):
        session=backend.Session();session.client=Mock()
        rows=[dict(activityId=i,activityName='Running',startTimeLocal='2026-10-06 06:00:00') for i in range(30)]
        rows.append(dict(activityId=100,activityName='5K TT',startTimeLocal='2025-12-20 06:00:00'))
        session.client.get_activities_by_date.return_value=rows
        session.client.get_activity_splits.return_value={}
        sample=session.sample('2026-10-06')['sample']['runs']
        self.assertEqual(len(sample),20)
        self.assertIn('100',[r['id'] for r in sample])
        session.client.get_activities_by_date.assert_called_once_with('2025-10-07','2026-10-06',activitytype='running')

    def test_long_ranges_follow_calendar_months_and_filter_boundaries(self):
        self.assertEqual(history_start(date(2026,10,6),548),date(2025,4,7))
        self.assertEqual(history_start(date(2026,10,6),730),date(2024,10,7))
        self.assertEqual(history_start(date(2024,8,31),548),date(2023,3,1))
        rows=[dict(activityId=i,activityName='Easy run',startTimeLocal=stamp+' 06:00:00')
              for i,stamp in enumerate(['2024-10-06','2024-10-07','2025-04-06','2025-04-07'])]
        self.assertEqual(len(normalized_runs(rows,'2026-10-06',548,{})['runs']),1)
        self.assertEqual(len(normalized_runs(rows,'2026-10-06',730,{})['runs']),3)
        session=backend.Session();session.client=Mock()
        session.client.connectapi.side_effect=[rows,[]]
        result=session.dashboard('2026-10-06',730,'{}')
        self.assertEqual(result['start'],'2024-10-07')
        self.assertEqual(len(result['runs']),3)
        self.assertEqual(session.client.connectapi.call_args_list[0].kwargs['params']['startDate'],'2024-10-07')

    def test_sample_includes_only_safe_best_5k_summary(self):
        session=backend.Session();session.client=Mock()
        session.client.get_activities_by_date.return_value=[dict(activityId=1,activityName='5K TT',startTimeLocal='2025-12-01 06:00:00',distance=5060,duration=1125)]
        session.client.get_activity_splits.return_value={}
        session.client.download_activity.return_value=recording([(0,0),(5000,1100),(5060,1125)])
        sample=session.sample('2026-10-06')['sample']['runs'][0]
        self.assertEqual(sample['best_5k']['duration'],1100)
        self.assertEqual(set(sample['best_5k']),{'duration','distance','start_distance','end_distance','start_elapsed','end_elapsed','samples'})
        self.assertNotIn('timestamp',json.dumps(sample))
        self.assertNotIn('method',sample['best_5k'])

    def test_sample_excludes_sensitive_garmin_fields(self):
        session=backend.Session();session.client=Mock()
        session.client.get_activities_by_date.return_value=[{'activityId':1,'activityName':'Easy run','startTimeLocal':'2026-10-06 06:00:00','distance':5000,'duration':1500,'startLatitude':42,'averageHR':123}]
        session.client.get_activity_splits.return_value={'lapDTOs':[{'distance':5000,'duration':1500,'averageHR':123}]}
        sample=json.dumps(session.sample('2026-10-06')['sample'])
        self.assertNotIn('averageHR',sample)
        self.assertNotIn('average_hr',sample)
        self.assertNotIn('hr_target',sample)
        self.assertNotIn('Latitude',sample)
        self.assertNotIn('token',sample)
        self.assertNotIn('password',sample)

if __name__ == '__main__': unittest.main()
