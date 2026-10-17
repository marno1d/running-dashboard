"""Garmin work runs inside the APK's Python runtime, off Android's UI thread."""
from datetime import date, timedelta
import json
import logging
from training import positive, normalized_runs, work_intervals, session_average, lap_choices, INTERVALS, history_start

from run_cache import RunCache
from dashboard_metrics import enrich, number
from dashboard_sync import sync_extras
from sync_job import SyncJob,SyncPaused
from sync_coverage import coverage
from web_sources import stations, dashboard as web_dashboard
from best_effort import best_from_original
from garminconnect import Garmin
from garminconnect.exceptions import (
    GarminConnectAuthenticationError, GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

# Library failures can contain session tickets or credentials; don't send them to Logcat.
logging.getLogger('garminconnect').disabled = True
logging.getLogger('garminconnect.client').disabled = True
logging.getLogger('curl_cffi').disabled = True
logging.getLogger('urllib3').disabled = True


def run_titles(activities, today):
    end = date.fromisoformat(today)
    start = end - timedelta(days=6)
    runs, seen = [], set()
    for activity in activities:
        stamp = activity.get('startTimeLocal') or ''
        try:
            day = date.fromisoformat(stamp[:10])
        except (TypeError, ValueError):
            continue
        if not start <= day <= end:
            continue
        identity = str(activity.get('activityId', stamp))
        if identity in seen:
            continue
        seen.add(identity)
        runs.append({'id': identity, 'title': activity.get('activityName') or 'Untitled run',
                     'started': stamp})
    return {'start': start.isoformat(), 'end': end.isoformat(),
            'runs': sorted(runs, key=lambda run: run['started'], reverse=True)}


class InputError(ValueError):
    pass


class Session:
    def __init__(self, cache_path=None):
        self.cache = RunCache(cache_path)
        self.client = None
        self.pending = None
        self.activities = None
        self.activity_window = None
        self.splits = self.cache.all_details("laps")
        self.efforts = self.cache.all_details("effort_v1")

    def configure_cache(self, path):
        if self.client or self.pending:
            return self.status()
        self.cache.db.close()
        self.cache = RunCache(path)
        self.splits = self.cache.all_details("laps")
        self.efforts = self.cache.all_details("effort_v1")
        return self.status()

    def status(self):
        return {'authenticated': self.client is not None, 'needs_mfa': self.pending is not None}

    def tokens(self):
        if self.client is None:
            return None
        return json.loads(self.client.client.dumps())

    def restore(self, tokens):
        if self.client or self.pending:
            return self.status()
        if tokens:
            client = Garmin(return_on_mfa=True, retry_attempts=1)
            # Load token state without downloading unrelated profile/settings data.
            client.client.loads(tokens)
            self.client = client
        return self.status()

    def login(self, email, password):
        self.logout()
        if not email.strip() or not password:
            raise InputError('Enter your Garmin email and password.')
        client = Garmin(email=email.strip(), password=password, return_on_mfa=True, retry_attempts=1)
        try:
            result = client.login()
        finally:
            # Garmin's MFA early-return can retain the password; we don't need it.
            client.password = None
        if result and result[0] == 'needs_mfa':
            self.pending = client
        else:
            self.client = client
        return self.status()

    def verify(self, code):
        if self.pending is None:
            raise InputError('Your sign-in expired. Start sign-in again.')
        if not code.strip():
            raise InputError('Enter the verification code from Garmin.')
        # Preserve the pending client on a wrong code, so retry remains possible.
        self.pending.client.resume_login(None, code.strip())
        self.client, self.pending = self.pending, None
        return self.status()

    def runs(self, today):
        if self.client is None:
            raise InputError('Sign in to Garmin first.')
        end = date.fromisoformat(today)
        start = end - timedelta(days=6)
        activities = self.client.get_activities_by_date(
            start.isoformat(), end.isoformat(), activitytype='running')
        return dict(self.status(), **run_titles(activities, today))

    def dashboard(self, today, days, settings_json, refresh=False, progress=None, offline=False, terrain_only=False):
        job=SyncJob(progress)
        try:
            return self._dashboard(today,days,settings_json,refresh,job,offline,terrain_only)
        except (SyncPaused,GarminConnectConnectionError,GarminConnectTooManyRequestsError,GarminConnectAuthenticationError,OSError) as error:
            # Every completed listing window/metric was already committed. Build
            # from saved inputs without issuing another request after a pause.
            saved=self._dashboard(today,days,settings_json,False,SyncJob(),True,False)
            if not saved['has_saved_data'] and not isinstance(error,SyncPaused):raise
            if isinstance(error,SyncPaused):notice=str(error)
            elif isinstance(error,GarminConnectTooManyRequestsError):notice='Garmin is limiting downloads. Completed data is saved; resume in a few minutes.'
            elif isinstance(error,GarminConnectAuthenticationError):notice='Garmin needs you to reconnect in Profile. Saved charts remain available.'
            else:notice='Connection interrupted. Completed data is saved; resume when connected.'
            saved['warnings']=[notice]
            saved['sync_paused']=True
            return saved

    def _dashboard(self, today, days, settings_json, refresh, job, offline, terrain_only):
        if self.client is None and not offline:
            raise InputError('Sign in to Garmin first.')
        days = int(days)
        if days not in (-1, 0, 7, 30, 45, 90, 180, 365, 548, 730):
            raise InputError('Choose a supported date range.')
        settings = json.loads(settings_json)
        if not isinstance(settings, dict):
            raise InputError('Invalid training settings.')
        settings['custom_range'] = days == -1
        settings['all_range'] = days == 0
        easy_hr = int(settings.get('easy_hr', 134))
        if not 40 <= easy_hr <= 240:
            raise InputError('Enter a heart-rate target between 40 and 240 bpm.')
        report=job
        current_today = today
        end = date.fromisoformat(today)
        custom_start = None
        if days == -1:
            try:
                end = date.fromisoformat(settings.get('custom_end',''))
                custom_start = date.fromisoformat(settings.get('custom_start',''))
            except (ValueError,TypeError):
                raise InputError('Choose valid start and end dates.')
            if custom_start > end or end > date.fromisoformat(today) or (end-custom_start).days > 3652:
                raise InputError('Choose a date range of up to ten years, ending today or earlier.')
            days = (end-custom_start).days+1
        start = custom_start if custom_start is not None else history_start(end, days)
        today = end.isoformat()
        window = (start.isoformat(), end.isoformat())
        sync_start,sync_end = start,end
        if settings.get('full_history'):
            sync_start = min(start,date(2025,6,1))
            sync_end = max(end,date.fromisoformat(current_today))
        sync_window = (sync_start.isoformat(),sync_end.isoformat())
        missing = self.cache.missing(*sync_window)
        gaps = [] if offline or terrain_only else list(missing)
        had_history = bool(list(self.cache.db.execute('SELECT 1 FROM coverage LIMIT 1')))
        # Recent overlap catches late uploads, edits and deletions without
        # repeatedly fetching years of already-saved history.
        if refresh and had_history and not offline and not terrain_only:
            recent = (max(sync_start, sync_end - timedelta(days=2)).isoformat(), sync_end.isoformat())
            gaps.append(recent)
        merged=[]
        for first, final in sorted(gaps):
            if merged and date.fromisoformat(first) <= date.fromisoformat(merged[-1][1]) + timedelta(days=1):
                merged[-1]=(merged[-1][0],max(merged[-1][1],final))
            else:merged.append((first,final))
        # Bounded listing windows make long history downloads restartable.
        windows=[]
        for first,final in merged:
            cursor=date.fromisoformat(first);last=date.fromisoformat(final)
            while cursor<=last:
                stop=min(last,cursor+timedelta(days=89))
                windows.append((cursor.isoformat(),stop.isoformat()));cursor=stop+timedelta(days=1)
        checked = 0
        for first, final in reversed(windows):
            report(('Checking recent runs' if had_history and first >= (end-timedelta(days=2)).isoformat() else 'Downloading missing history') +
                   ' · ' + first + ' to ' + final)
            downloaded = []
            for page in range(500):
                batch = job.request(lambda:self.client.connectapi(self.client.garmin_connect_activities, params={
                    'startDate': first, 'endDate': final,
                    'start': str(page * 20), 'limit': '20'}),'Run summaries')
                if not batch:
                    break
                if not isinstance(batch, list) or any(not isinstance(item,dict) or 'activityId' not in item or not isinstance(item.get('startTimeLocal'),str) for item in batch):
                    raise InputError('Garmin returned an unexpected run list. Please try again.')
                downloaded.extend(batch)
                checked += len(batch)
                report('Checked ' + str(checked) + ' run summaries · existing downloads kept')
            else:
                raise InputError('Garmin returned too many pages. Choose a shorter date range.')
            for activity in downloaded:
                if isinstance(activity,dict):
                    activity['_station_match'] = stations.nearest_station(activity,15)
            changed = self.cache.save_window(first,final,downloaded)
            for identity in changed:
                self.splits.pop(identity,None)
                self.efforts.pop(identity,None)
        self.activities = self.cache.activities(*sync_window)
        self.activity_window = window
        activity_by_id={str(a['activityId']):a for a in self.activities}
        result = normalized_runs(self.activities, sync_end.isoformat(), days, settings.get('categories', {}), easy_hr, sync_start.isoformat(), settings.get('classification_mode','native'))
        health, weather, warnings = sync_extras(self.client,self.cache,result,settings,refresh,report,self.activities,allow_download=not offline,job=job,terrain_only=terrain_only)
        report('Preparing charts · ' + str(len(result['runs'])) + ' saved sessions')
        result['run_points'] = [dict(row) for row in result['runs']
                                if row['category'] == 'easy' and row['pace'] is not None]
        result['trial_points'] = []
        result['missing_trials'] = 0
        result['interval_points'] = []
        result['missing_intervals'] = 0
        result['split_failures'] = 0
        lap_total = sum(row['category'] in INTERVALS or row['category'] == 'trial'
                        for row in result['runs'])
        lap_done = 0
        for run in result['runs']:
            if run['category'] == 'trial':
                report('Reading saved 5K effort' +
                       ' · ' + str(lap_done + 1) + '/' + str(lap_total) + ' · ' + run['title'][:48], lap_done, lap_total)
                lap_done += 1
                failed = False
                try:
                    effort = self.cache.detail(run['id'],'effort_v1')[1]
                except (GarminConnectTooManyRequestsError, GarminConnectAuthenticationError):
                    raise
                except Exception:
                    effort,failed = None,True
                if not effort:
                    source = activity_by_id.get(run['id'],{})
                    fastest = positive(source.get('fastestSplit_5000'))
                    if fastest:
                        effort = dict(duration=fastest,distance=5000,method='garmin_fastest_split')
                if effort:
                    trial = dict(run, **effort)
                    trial['pace'] = effort['duration']/5
                    result['trial_points'].append(trial)
                    run['best_5k'] = effort
                else:
                    result['missing_trials'] += 1
                    run['trial_error'] = 'Could not read the original recording. Refresh to retry.' if failed else 'No continuous 5 km in the available recording.'
                continue
            if run['category'] in INTERVALS:
                report('Preparing interval metrics' +
                       ' · ' + str(lap_done + 1) + '/' + str(lap_total) + ' · ' + run['title'][:48], lap_done, lap_total)
                lap_done += 1
            if run['category'] not in INTERVALS:
                continue
            have_laps=self.cache.detail(run['id'],'laps')[0]
            has_summary=bool(self.cache.detail(run['id'],'interval_fit_v1')[1] or web_dashboard.interval_pace_from_split_summaries(activity_by_id.get(run['id'],{})))
            if (offline or terrain_only or result.get('optional_downloads_paused') or settings.get('interval_mode')=='session' and has_summary) and not have_laps:
                if not has_summary:result['split_failures'] += 1
                continue
            try:
                payload = job.request(lambda:self._splits(run['id']),'Interval laps')
            except (GarminConnectTooManyRequestsError,GarminConnectAuthenticationError,GarminConnectConnectionError,OSError):
                result['optional_downloads_paused']=True
                warnings.append('Garmin lap downloads paused. Completed data is saved; resume later.')
                result['split_failures']+=1
                continue
            except SyncPaused:raise
            except Exception:
                result['split_failures'] += 1
                continue
            selected = settings.get('laps', {}).get(run['id'])
            if selected is not None:
                selected = {int(index) for index in selected}
            points = work_intervals(run, payload, selected)
            run['work_reps'] = len(points)
            if not points:
                result['missing_intervals'] += 1
            if settings.get('interval_mode') == 'session':
                points = session_average(points)
            result['interval_points'].extend(points)
        result['sync']=coverage(self.cache,result['runs'],*sync_window,settings)
        enrich(result,self.activities,self.splits,health,weather,settings,
               visible_range=window,fit_intervals=self.cache.all_details('interval_fit_v1'))
        result['warnings'] = warnings
        result['sync_paused']=bool(result.get('optional_downloads_paused') or result.get('terrain_downloads_paused'))
        result['cached_only'] = offline
        result['cache_complete'] = not self.cache.missing(*sync_window)
        result['has_saved_data'] = bool(self.activities)
        report('Charts ready · ' + str(len(result['runs'])) + ' sessions', lap_total, lap_total)
        return dict(self.status(), **result)

    def sync_terrain(self,today,days,settings_json,progress=None):
        settings=json.loads(settings_json);settings['include_terrain']=True
        if not self.cache.db.execute('SELECT 1 FROM runs LIMIT 1').fetchone():
            raise InputError('Refresh your activities once before downloading terrain.')
        return self.dashboard(today,days,json.dumps(settings),progress=progress,terrain_only=True)

    def cached_dashboard(self, today, days, settings_json):
        return self.dashboard(today,days,settings_json,offline=True)

    def comparison(self, today, days, settings_json):
        from comparison_contract import sanitize_snapshot
        data = self.cached_dashboard(today,days,settings_json)
        if not data['has_saved_data']:
            raise InputError('Download some dashboard history before sharing a comparison.')
        settings = json.loads(settings_json)
        first,last = data['history_start'],data['history_end']
        activities = self.cache.activities(first,last)
        for activity in activities:
            kind = activity.get('activityType')
            if isinstance(kind,dict):activity['activityType'] = kind.get('typeKey')
        details = {kind:self.cache.all_details(kind) for kind in (
            'laps','effort_v1','interval_fit_v1','hr_histogram_v1','weather_v1','terrain_v1')}
        daily = {kind:self.cache.daily(first,last,kind) for kind in (
            'sleep','rhr','hrv','station:KPVU','station:KSLC')}
        payload = sanitize_snapshot(dict(schema=1,selection=dict(today=today,days=int(days),settings=settings),
                                         activities=activities,coverage=[dict(start=a,end=b) for a,b in self.cache.db.execute('SELECT start,end FROM coverage')],details=details,daily=daily,android=data))
        return dict(self.status(),comparison=payload)

    def _effort(self, identity):
        if identity not in self.efforts:
            found, saved = self.cache.detail(identity, 'effort_v1')
            if found:
                self.efforts[identity] = saved
                return saved
            raw = self.client.download_activity(identity, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
            self.efforts[identity] = best_from_original(raw)
            self.cache.save_detail(identity, 'effort_v1', self.efforts[identity])
        return self.efforts[identity]

    def _splits(self, identity):
        if identity not in self.splits:
            found, saved = self.cache.detail(identity, 'laps')
            if found:
                self.splits[identity] = saved
                return saved
            payload = self.client.get_activity_splits(identity)
            # Retain chart inputs, including HR/elevation, without GPS or tokens.
            from training import laps_list, intensity
            self.splits[identity] = {'lapDTOs': [
                dict({key:lap[key] for key in ('distance','duration','averageSpeed','averageHR','elevationGain','elevationLoss') if key in lap}, intensityType=intensity(lap))
                for lap in laps_list(payload)]}
            self.cache.save_detail(identity, 'laps', self.splits[identity])
        return self.splits[identity]

    def laps(self, identity):
        if self.client is None:
            raise InputError('Sign in to Garmin first.')
        return dict(self.status(), laps=lap_choices(self._splits(str(identity))))

    def sample(self, today):
        if self.client is None:
            raise InputError('Sign in to Garmin first.')
        end = date.fromisoformat(today)
        activities = self.client.get_activities_by_date(
            (end - timedelta(days=364)).isoformat(), end.isoformat(), activitytype='running')
        rows = normalized_runs(activities, today, 365, {})['runs']
        # Share only chart inputs, without credentials, location, or heart rate.
        samples = []
        trials = [row for row in rows if row["category"] == "trial"][:5]
        chosen = trials + [row for row in rows if row not in trials][:20 - len(trials)]
        for row in sorted(chosen, key=lambda row: row["started"], reverse=True):
            item = {key:row[key] for key in ('id','title','started','date','category','pace','distance','duration') if key in row}
            try:
                item['laps'] = lap_choices(self._splits(row['id']))
            except GarminConnectTooManyRequestsError:
                break
            except Exception:
                item['laps'] = []
            if row['category'] == 'trial':
                try:
                    effort = self._effort(row['id'])
                    if effort:
                        item['best_5k'] = {key: effort[key] for key in
                            ('duration', 'distance', 'start_distance', 'end_distance', 'start_elapsed', 'end_elapsed', 'samples')}
                except GarminConnectTooManyRequestsError:
                    break
                except Exception:
                    pass
            samples.append(item)
        return dict(self.status(), sample={'runs': samples})

    def logout(self):
        for client in (self.client, self.pending):
            if client:
                client.password = None
        self.cache.clear()
        self.client = self.pending = None
        self.activities = None
        self.activity_window = None
        self.splits = {}
        self.efforts = {}
        return self.status()


_session = Session()


def call(operation, *args):
    """One JSON boundary: never allow a raw Python exception into Android logs."""
    try:
        if operation not in ('configure_cache', 'restore', 'login', 'verify', 'runs', 'logout', 'status', 'dashboard', 'cached_dashboard', 'sync_terrain', 'comparison', 'laps', 'sample'):
            raise InputError('Unknown operation.')
        result = getattr(_session, operation)(*args)
        result['ok'] = True
        result['tokens'] = _session.tokens()
        return json.dumps(result)
    except GarminConnectTooManyRequestsError:
        error = 'Garmin is limiting sign-ins. Wait a few minutes before trying again.'
    except GarminConnectAuthenticationError:
        error = 'Garmin rejected the credentials, code, or saved session. Check your details or sign in again.'
    except GarminConnectConnectionError:
        error = 'Could not connect to Garmin. Check your network and try again. Garmin may temporarily block unofficial clients.'
    except InputError as invalid:
        error = str(invalid)
    except Exception:
        error = 'Could not complete the request. Try again or restart sign-in.'
    return json.dumps(dict(_session.status(), ok=False, error=error))
