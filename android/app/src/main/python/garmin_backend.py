"""Garmin work runs inside the APK's Python runtime, off Android's UI thread."""
from datetime import date, timedelta
import json
import logging
from training import positive, normalized_runs, work_intervals, lap_choices, INTERVALS, history_start

from run_cache import RunCache
from dashboard_metrics import enrich, number
from dashboard_sync import sync_extras
from sync_job import SyncJob,SyncPaused
from sync_coverage import coverage
from web_sources import stations, dashboard as web_dashboard
from best_effort import best_from_original
from route_preview import route_from_original,thumbnail_route
import training_routes
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
        # Older installs and saved comparison inputs may still request rep plots.
        settings['interval_mode'] = 'session'
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
            if (offline or terrain_only or result.get('optional_downloads_paused') or has_summary) and not have_laps:
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
        result['sync']=coverage(self.cache,result['runs'],*sync_window,settings)
        enrich(result,self.activities,self.splits,health,weather,settings,
               visible_range=window,fit_intervals=self.cache.all_details('interval_fit_v1'))
        if settings.get('target_route_engine')==2 and settings.get('target_route_id'):
            from route_workouts import apply_route,invalidate
            try:
                route=next((r for r in self.route_book(settings_json)['routes'] if r['id']==settings['target_route_id']),None)
                if route is None or not route.get('reference'):raise ValueError('Choose a reference in Profile → Routes.')
                if route['reference'].get('stale'):raise ValueError('The route reference changed. Choose it again in Profile → Routes.')
                if route.get('extent') is None:raise ValueError('Open Routes and select this route to load its elevation profile.')
                data=self.cache.detail(route['reference']['id'],'route_data_v1')[1] or {}
                apply_route(result['targets'],route,data,settings)
            except ValueError as error:invalidate(result['targets'],error)
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
        settings['interval_mode'] = 'session'
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

    def route(self, identity):
        identity=str(identity)
        if not identity.isdigit() or int(identity)<=0:
            raise InputError('Invalid session.')
        found,outline=self.cache.detail(identity,'route_outline_v1')
        if not found:
            if self.client is None:
                raise InputError('Connect to Garmin to load this route.')
            raw=self.client.download_activity(identity,dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
            outline=route_from_original(raw)
            self.cache.save_detail(identity,'route_outline_v1',outline)
            try:self.cache.save_detail(identity,'route_data_v1',training_routes.recording_data(raw))
            except Exception:pass
        return dict(self.status(),route=outline)

    def _route_data(self,identity,outline=False,profile=False):
        found,data=self.cache.detail(identity,'route_data_v1')
        if not found or profile and data.get('profile_version')!=2 or outline and self.client is not None and not self.cache.detail(identity,'route_outline_v1')[0]:
            if self.client is None:raise InputError('Connect to Garmin to read this reference recording.')
            raw=self.client.download_activity(identity,dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
            data=training_routes.recording_data(raw)
            self.cache.save_detail(identity,'route_data_v1',data)
            self.cache.save_detail(identity,'route_outline_v1',route_from_original(raw))
        return data

    def routes(self,settings_json):
        settings=json.loads(settings_json);routes=training_routes.configuration(self.cache)
        for route in routes:
            for ref in route['references'].values():
                row=self.cache.db.execute('SELECT fingerprint FROM runs WHERE id=?',(ref['id'],)).fetchone()
                ref['stale']=not row or row[0]!=ref.get('fingerprint') or ref.get('interval') and settings.get('laps',{}).get(ref['id'])!=ref.get('lap_selection')
                ref['outline']=self.cache.detail(ref['id'],'route_outline_v1')[1]
        return dict(self.status(),routes=routes)

    def route_candidates(self,route_id,kind,today,settings_json,scan=0):
        settings=json.loads(settings_json)
        if kind not in training_routes.KINDS:raise InputError('Choose a workout type.')
        routes=self.routes(settings_json)['routes'];route=next((r for r in routes if r['id']==route_id),None)
        if route is None:raise InputError('Route not found.')
        rows=[r for r in self._route_rows(today,settings_json) if r.get('activity_type') in ('running','trail_running','track_running')]
        preferred=('short','medium','long') if kind=='intervals' else ('easy','easy_long') if kind in ('easy','easy_long') else (kind,)
        if kind!='route':rows.sort(key=lambda row:(row['category']!=kind,row['category'] not in preferred))
        checked=self.cache.all_details('route_data_v1');attempted=0;scan_error=None
        for row in rows:
            if attempted>=min(5,max(0,int(scan))):break
            if row['id'] in checked:continue
            attempted+=1
            try:checked[row['id']]=self._route_data(row['id'])
            except Exception:
                scan_error='Could not check more recordings. Check your connection and retry.';break
        anchors=[checked.get(ref['id'],{}).get('cells',[]) for ref in route['references'].values() if not ref.get('stale')]
        candidates=[]
        for row in rows:
            cells=checked.get(row['id'],{}).get('cells',[])
            score=max((training_routes.gps_overlap(anchor,cells) for anchor in anchors),default=0)
            item={key:row.get(key) for key in ('id','title','date','started','category','distance','duration','work_distance','work_duration')}
            item['needs_review']=(row['category']=='other' and row.get('is_run',True)
                or row['category'] in INTERVALS and not row.get('work_reps')
                or row['category']=='trial' and not row.get('best_5k'))
            item.update(overlap=score,checked=row['id'] in checked)
            candidates.append(item)
        candidates.sort(key=lambda r:(r['overlap']>=.65,r['category']==kind,r['category'] in preferred,r['overlap']),reverse=True)
        return dict(self.status(),candidates=candidates,scan_error=scan_error,remaining=sum(r['id'] not in checked for r in rows))

    def route_assign(self,route_id,kind,identity,today,settings_json):
        if kind not in training_routes.KINDS:raise InputError('Choose a workout type.')
        routes=training_routes.configuration(self.cache);route=next((r for r in routes if r['id']==route_id),None)
        if route is None:raise InputError('Route not found.')
        if not identity:route['references'].pop(kind,None)
        else:
            row=next((r for r in self.cached_dashboard(today,0,settings_json)['runs'] if r['id']==str(identity)),None)
            if not row:raise InputError('This session is no longer saved. Sync and choose it again.')
            try:ref=training_routes.reference(row,self._route_data(row['id'],True),kind,json.loads(settings_json))
            except ValueError as error:raise InputError(str(error)) from None
            ref['fingerprint']=self.cache.db.execute('SELECT fingerprint FROM runs WHERE id=?',(row['id'],)).fetchone()[0]
            route['references'][kind]=ref
        self.cache.save_meta('training_routes_v1',routes)
        return self.routes(settings_json)

    def route_rename(self,route_id,name,settings_json):
        name=str(name).strip()
        if not name or len(name)>100:raise InputError('Use a route name of 1–100 characters.')
        routes=training_routes.configuration(self.cache);route=next((r for r in routes if r['id']==route_id),None)
        if route is None:raise InputError('Route not found.')
        route['name']=name;self.cache.save_meta('training_routes_v1',routes)
        return self.routes(settings_json)

    def route_selection(self,route_id,kind,settings_json):
        route=next((r for r in self.routes(settings_json)['routes'] if r['id']==route_id),None)
        if route is None:raise InputError('Route not found.')
        try:selected=training_routes.selection(route,kind)
        except ValueError as error:raise InputError(str(error)) from None
        return dict(self.status(),selection=selected)

    def route_book(self,settings_json):
        saved=self.cache.meta('route_book_v2')
        if saved is None:
            saved=[]
            for old in training_routes.configuration(self.cache):
                refs=list(old['references'].values());whole=[r for r in refs if not r.get('interval')]
                ref=max(whole or refs,key=lambda r:r['distance']) if refs else None
                if ref:
                    original=self.cache.db.execute('SELECT body FROM runs WHERE id=?',(ref['id'],)).fetchone()
                    if original:
                        original=json.loads(original[0]);ref['distance']=number(original.get('distance')) or ref['distance']
                        ref['duration']=number(original.get('movingDuration')) or number(original.get('duration')) or ref['duration']
                saved.append(dict(id=old['id'],name=old['name'],shape='loop' if old['id']=='liberty' else 'out_back',
                    surface='trail' if old['id']=='bonneville' else 'road',extent=None,reverse=False,reference=ref))
        for route in saved:
            ref=route.get('reference')
            route['profile_ready']=False
            if not ref:continue
            row=self.cache.db.execute('SELECT fingerprint FROM runs WHERE id=?',(ref['id'],)).fetchone()
            ref['stale']=not row or row[0]!=ref.get('fingerprint')
            data=self.cache.detail(ref['id'],'route_data_v1')[1] or {}
            route['profile_ready']=data.get('profile_version')==2 and len(data.get('profile',[]))>=2
            ref['outline']=self.cache.detail(ref['id'],'route_outline_v1')[1]
            if route.get('reverse') and ref.get('outline'):
                ref['outline']=dict(segments=[list(reversed(segment)) for segment in reversed(ref['outline']['segments'])])
            if route['profile_ready']:
                length,gain,loss=data['profile'][-1];ref.update(distance=length,gain=gain/.3048,loss=loss/.3048)
                route['suggested_extent']=self._route_extent(route,data)
                if route.get('extent') is None:route['extent']=route['suggested_extent']
        return dict(self.status(),routes=saved)

    def _route_rows(self,today,settings_json):
        settings=json.loads(settings_json);settings.pop('target_route_engine',None)
        return self.cached_dashboard(today,0,json.dumps(settings))['runs']

    def _route_extent(self,route,data):
        length=data['profile'][-1][0]
        if route['shape']=='out_back':
            turn=data.get('suggested_turn')
            return min(turn,length) if turn and .05*length<turn else length/2
        return (data.get('suggested_loop') or length) if route['shape']=='loop' else length

    def route_configure(self,route_id,patch_json,settings_json):
        from route_workouts import SHAPES
        routes=self.route_book(settings_json)['routes'];route=next((r for r in routes if r['id']==route_id),None)
        if route is None:raise InputError('Route not found.')
        patch=json.loads(patch_json)
        if 'name' in patch:
            name=str(patch['name']).strip()
            if not name or len(name)>100:raise InputError('Use a name of 1–100 characters.')
            route['name']=name
        if 'shape' in patch:
            if patch['shape'] not in SHAPES:raise InputError('Choose out-and-back, loop, or one-way.')
            if route['shape']!=patch['shape']:route['extent']=None
            route['shape']=patch['shape']
        if 'surface' in patch:
            if patch['surface'] not in ('road','trail'):raise InputError('Choose Road or Trail.')
            route['surface']=patch['surface']
        if 'reverse' in patch:route['reverse']=bool(patch['reverse'])
        if 'extent' in patch:
            value=number(patch['extent']);ref=route.get('reference') or {}
            if value is None or not 100<=value<=ref.get('distance',0):raise InputError('Use a distance from 100 m to the reference length.')
            route['extent']=value
        self.cache.save_meta('route_book_v2',routes)
        return self.route_book(settings_json)

    def route_reference(self,route_id,identity,today,settings_json):
        routes=self.route_book(settings_json)['routes'];route=next((r for r in routes if r['id']==route_id),None)
        if route is None:raise InputError('Route not found.')
        if not identity:route.update(reference=None,extent=None)
        else:
            row=next((r for r in self._route_rows(today,settings_json) if r['id']==str(identity)),None)
            if row is None:raise InputError('This session is no longer saved.')
            data=self._route_data(row['id'],True,True)
            if len(data.get('profile',[]))<2 or len(data.get('cells',[]))<2:raise InputError('Choose an outdoor recording with GPS, distance, and altitude. Elevation totals alone cannot define route segments.')
            length,gain,loss=data['profile'][-1]
            route['reference']=dict(id=row['id'],title=row['title'],date=row['date'],distance=length,duration=row['duration'],gain=gain/.3048,loss=loss/.3048,
                fingerprint=self.cache.db.execute('SELECT fingerprint FROM runs WHERE id=?',(row['id'],)).fetchone()[0])
            route['extent']=self._route_extent(route,data)
        self.cache.save_meta('route_book_v2',routes)
        return self.route_book(settings_json)

    def route_candidates_v2(self,route_id,today,settings_json,scan=0):
        result=self.route_candidates(route_id,'route',today,settings_json,scan)
        route=next((r for r in self.route_book(settings_json)['routes'] if r['id']==route_id),None)
        ref=(route or {}).get('reference') or {};checked=self.cache.all_details('route_data_v1')
        outlines=self.cache.all_details('route_outline_v1')
        anchor=checked.get(ref.get('id'),{}).get('cells',[])
        for row in result['candidates']:
            data=checked.get(row['id'],{});row['overlap']=training_routes.gps_overlap(anchor,data.get('cells',[]))
            row['profile_ready']=len(data.get('profile',[]))>=2
            row['longer']=(row.get('distance') or 0)>ref.get('distance',float('inf'))
            if row['id'] in outlines:row['outline']=thumbnail_route(outlines[row['id']])
        result['candidates'].sort(key=lambda r:r.get('started') or r['date'],reverse=True)
        return result

    def route_matches(self,route_id,identity,today,settings_json,scan=0):
        """Preview a prospective reference and longer matches without assigning it."""
        rows=self._route_rows(today,settings_json)
        original=next((r for r in rows if r['id']==str(identity)),None)
        if original is None:raise InputError('This session is no longer saved.')
        anchor=self._route_data(original['id'],True,True)
        if len(anchor.get('cells',[]))<2 or len(anchor.get('profile',[]))<2:
            raise InputError('Choose an outdoor recording with GPS, distance, and altitude.')
        longer=[r for r in rows if r.get('activity_type') in ('running','trail_running','track_running')
                and r['id']!=original['id'] and (r.get('distance') or 0)>(original.get('distance') or 0)]
        longer.sort(key=lambda r:(r['distance'],r['started']),reverse=True)
        checked=self.cache.all_details('route_data_v1');attempted=0;scan_error=None
        for row in longer:
            if attempted>=min(5,max(0,int(scan))):break
            if row['id'] in checked:continue
            attempted+=1
            try:checked[row['id']]=self._route_data(row['id'],True)
            except Exception:
                scan_error='Could not check more recordings. Check your connection and retry.';break
        result=self.route_candidates_v2(route_id,today,settings_json)
        candidates={r['id']:r for r in result['candidates']}
        if original['id'] not in candidates:raise InputError('Choose an outdoor running session.')
        original=candidates[original['id']];matches=[]
        for row in longer:
            if row['id'] not in candidates:continue
            candidate=candidates[row['id']]
            score=training_routes.gps_coverage(anchor['cells'],checked.get(row['id'],{}).get('cells',[]))
            if score>=.85:
                candidate.update(overlap=score,longer=True);matches.append(candidate)
        return dict(self.status(),original=original,candidates=matches,scan_error=scan_error,
                    remaining=sum(r['id'] not in checked for r in longer),
                    checked=sum(r['id'] in checked for r in longer))

    def route_use(self,route_id,settings_json):
        routes=self.route_book(settings_json)['routes'];route=next((r for r in routes if r['id']==route_id),None)
        if route is None or not route.get('reference'):raise InputError('Choose a route reference in Profile → Routes.')
        ref=route['reference']
        if ref.get('stale'):raise InputError('The reference session changed. Choose it again in Profile → Routes.')
        data=self._route_data(ref['id'],True,True)
        if len(data.get('profile',[]))<2:raise InputError('The reference needs a recorded altitude profile. Choose another session.')
        if route.get('extent') is None:
            route['extent']=self._route_extent(route,data);self.cache.save_meta('route_book_v2',routes)
        return dict(self.status(),selection={key:route[key] for key in ('id','name','shape','surface','extent','reverse')})

    def workout_latest(self,kind,today,settings_json):
        from route_workouts import infer_workout
        settings=json.loads(settings_json);rows=self._route_rows(today,settings_json)
        row=next((r for r in rows if r['category']==kind or kind=='walking' and r['category'] in INTERVALS),None)
        if row is None:raise InputError('No saved session of this type. Sync more history or enter the workout manually.')
        result=dict(self.status(),source=dict(id=row['id'],date=row['date'],title=row['title']))
        if kind in ('easy','easy_long'):
            if not row.get('duration'):raise InputError('The latest session has no recorded duration.')
            result['minutes']=max(5,min(360,round(row['duration']/60)));return result
        try:definition,walking=infer_workout(self._route_data(row['id'],False,True),row['category'],settings,row['id'])
        except ValueError as error:raise InputError(str(error)) from None
        result.update(definition=definition,walking_pace=walking)
        if kind=='walking' and walking is None:raise InputError('The latest interval recording has no usable moving recovery laps. Enter walking pace manually.')
        return result

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
        if operation not in ('configure_cache', 'restore', 'login', 'verify', 'runs', 'logout', 'status', 'dashboard', 'cached_dashboard', 'sync_terrain', 'comparison', 'laps', 'sample', 'route', 'routes', 'route_candidates', 'route_assign', 'route_rename', 'route_selection', 'route_book', 'route_configure', 'route_reference', 'route_candidates_v2', 'route_matches', 'route_use', 'workout_latest'):
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
