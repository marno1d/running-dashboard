"""Incremental Garmin health/weather downloads into the app-private cache."""
from datetime import date, timedelta
import time
from garminconnect.exceptions import GarminConnectAuthenticationError, GarminConnectTooManyRequestsError, GarminConnectConnectionError, GarminConnectNotFoundError
from garmin_health import merged_summary
from garmin_weather import summarize_weather
from dashboard_metrics import number
from recording_hr import heart_rate_histogram
from garminconnect import Garmin
from best_effort import best_from_original
from dashboard_sources import original_zip, station_weather, terrain_summary, merge_weather
from web_sources import dashboard, terrain
from sync_job import SyncJob,SyncPaused,TerrainRequests,TerrainDeferred


HEALTH_FIELDS = {'sleep':('sleepHours','sleepScore'),'rhr':('restingHeartRate',),'hrv':('hrvLastNightAvg',)}


def _recovery_rows(kind, raw, first, last):
    """Translate range summaries to the same fields used by daily downloads."""
    rows = raw.get('hrvSummaries') if kind == 'hrv' and isinstance(raw,dict) else raw
    if not isinstance(rows,list):
        raise ValueError('Unexpected recovery range response')
    parts = {}
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError('Unexpected recovery range row')
        stamp = row.get('calendarDate')
        if not isinstance(stamp,str) or date.fromisoformat(stamp).isoformat()!=stamp or not first<=stamp<=last or stamp in parts:
            raise ValueError('Unexpected recovery range date')
        if kind == 'sleep':
            values = row.get('values')
            if not isinstance(values,dict) or 'totalSleepTimeInSeconds' not in values:
                continue  # Leave unrecognized rows for the daily endpoint.
            payload = dict(sleepTimeSeconds=values['totalSleepTimeInSeconds'],
                           sleepScore=values.get('sleepScore',values.get('overallSleepScore')))
        elif kind == 'rhr':
            if 'value' not in row:continue
            payload = dict(value=row['value'])
        else:
            if 'lastNightAvg' not in row:continue
            payload = dict(lastNightAvg=row['lastNightAvg'])
        if any(value is not None and (isinstance(value,bool) or number(value) is None) for value in payload.values()):
            continue
        summary = merged_summary(stamp,{kind:payload})
        parts[stamp] = {key:number(summary.get(key)) for key in HEALTH_FIELDS[kind]}
    return parts


def _sync_recovery(client, cache, parts, start, end, refresh, recent, report, job):
    """Fetch at most 28 days per request; missing rows retain daily fallback."""
    daily = {'sleep':client.get_sleep_data,'rhr':client.get_rhr_day,'hrv':client.get_hrv_data}
    methods = {'sleep':'get_sleep_daily','rhr':'get_rhr_daily','hrv':'get_hrv_data_range'}
    disabled = set()
    last,final = date.fromisoformat(end),date.fromisoformat(start)
    total = (last-final).days+1
    failures = 0
    while last >= final:
        first = max(final,last-timedelta(days=27))
        stamps = [(last-timedelta(days=i)).isoformat() for i in range((last-first).days+1)]
        pending = {kind:{stamp for stamp in stamps if stamp not in parts[kind] or refresh and stamp>=recent}
                   for kind in daily}
        for kind,method in methods.items():
            job.checkpoint()
            needed = pending[kind]
            call = getattr(client,method,None)
            if kind in disabled or len(needed)<2 or not callable(call):continue
            begin,finish = min(needed),max(needed)
            label = 'Recovery · '+kind+' · '+begin+' to '+finish
            report(label,(date.fromisoformat(end)-last).days,total)
            def fetch_range():
                try:return call(begin,finish)
                except GarminConnectConnectionError as error:
                    status = getattr(getattr(error,'response',None),'status_code',None)
                    if isinstance(error,GarminConnectNotFoundError) or status in (400,404,405,422):
                        raise ValueError('Recovery ranges unavailable') from None
                    raise
            try:
                raw = job.request(fetch_range,label)
                rows = _recovery_rows(kind,raw,begin,finish)
                for stamp,part in rows.items():
                    if stamp not in needed:continue
                    job.checkpoint()
                    cache.save_day(stamp,kind,part)
                    parts[kind][stamp] = part
                    needed.remove(stamp)
            except (GarminConnectAuthenticationError,GarminConnectTooManyRequestsError,GarminConnectConnectionError,OSError):
                return failures+1,True
            except SyncPaused:raise
            except Exception:
                # Older accounts/endpoints may not support range summaries.
                # Try the established daily reader without repeating failed batches.
                disabled.add(kind)
            time.sleep(.2)
        for stamp in stamps:
            job.checkpoint()
            if not any(stamp in needed for needed in pending.values()):continue
            report('Recovery · '+stamp,(date.fromisoformat(end)-date.fromisoformat(stamp)).days,total)
            for kind,call in daily.items():
                if stamp not in pending[kind]:continue
                try:
                    raw = job.request(lambda:call(stamp),'Recovery · '+stamp)
                    if raw is not None and not isinstance(raw,(dict,list)):
                        raise ValueError('Unexpected health response')
                    summary = merged_summary(stamp,{kind:raw})
                    part = {key:number(summary.get(key)) for key in HEALTH_FIELDS[kind]}
                    cache.save_day(stamp,kind,part)
                    parts[kind][stamp] = part
                except (GarminConnectAuthenticationError,GarminConnectTooManyRequestsError,GarminConnectConnectionError,OSError):
                    return failures+1,True
                except SyncPaused:raise
                except Exception:
                    failures += 1
                time.sleep(.2)
        last = first-timedelta(days=1)
    return failures,False


def sync_extras(client, cache, result, settings, refresh, report, activities=None, allow_download=True, job=None, terrain_only=False):
    job=job or SyncJob()
    start,end = result['start'],result['end']
    provider=TerrainRequests(cache,job)
    terrain_paused=False
    recent = (date.today()-timedelta(days=2)).isoformat()
    health_parts = {kind:cache.daily(start,end,kind) for kind in ('sleep','rhr','hrv')}
    warnings = []
    garmin_paused = False
    if allow_download and not terrain_only and settings.get('include_recovery'):
        failures,garmin_paused = _sync_recovery(client,cache,health_parts,start,end,refresh,recent,report,job)
        if failures:
            warnings.append(str(failures)+' recovery requests failed; refresh to retry.')
    health = {}
    for parts in health_parts.values():
        for day,part in parts.items():
            health.setdefault(day,{}).update(part)
    health = {day:dict(sleep_hours=row.get('sleepHours'),sleep_score=row.get('sleepScore'),
                       resting_hr=row.get('restingHeartRate'),hrv=row.get('hrvLastNightAvg')) for day,row in health.items()}
    recording_failures = 0
    terrain_failures = 0
    indexed = {str(a['activityId']):a for a in activities or []}
    terrain_rows=[r for r in result['runs'] if r.get('activity_type') in terrain.OUTDOOR_ELEVATION_TYPES]
    saved_terrain=cache.all_details('terrain_v1')
    terrain_done=sum((saved_terrain.get(r['id']) or {}).get('status')=='ok' for r in terrain_rows)
    terrain_skipped=sum((saved_terrain.get(r['id']) or {}).get('status')=='skipped' for r in terrain_rows)
    for index,row in enumerate(result['runs']):
        job.checkpoint()
        identity = row['id']
        easy = row['category'] in ('easy','easy_long')
        interval = row['category'] in ('short','medium','long')
        have_hr,histogram = cache.detail(identity,'hr_histogram_v1')
        have_interval,fit_interval = cache.detail(identity,'interval_fit_v1')
        have_trial,trial = cache.detail(identity,'effort_v1')
        have_terrain,elevation = cache.detail(identity,'terrain_v1')
        use_recordings = allow_download and settings.get('include_recordings',False) and not garmin_paused
        want_hr = use_recordings and easy and not have_hr and not terrain_only
        want_interval = use_recordings and interval and not have_interval and not terrain_only
        want_trial = allow_download and not garmin_paused and not terrain_only and row['category']=='trial' and not have_trial
        activity = indexed.get(identity,dict(activityId=identity,activityType={'typeKey':row.get('activity_type','running')}))
        outdoor = terrain.type_key(activity) in terrain.OUTDOOR_ELEVATION_TYPES
        want_terrain = allow_download and settings.get('include_terrain',False) and outdoor and not have_terrain and not garmin_paused and not terrain_paused
        if want_terrain:
            try:provider.ready()
            except TerrainDeferred as error:
                warnings.append(str(error));terrain_paused=True;want_terrain=False
        if want_hr or want_interval or want_trial or want_terrain:
            report('Reading original recording · '+row['date']+' · '+row['title'][:40],index,len(result['runs']))
            try:
                raw = job.request(lambda:client.download_activity(identity,dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL),'Original recording · '+row['date'])
                parsers=[]
                if want_hr or (want_terrain and use_recordings and easy and not have_hr):
                    parsers.append(('hr_histogram_v1',lambda:heart_rate_histogram(raw)))
                if want_interval or (want_terrain and use_recordings and interval and not have_interval):
                    parsers.append(('interval_fit_v1',lambda:dashboard.interval_laps_from_fit(original_zip(raw))))
                if want_trial or (want_terrain and row['category']=='trial' and not have_trial):
                    parsers.append(('effort_v1',lambda:best_from_original(raw)))
                for kind,parse in parsers:
                    job.checkpoint()
                    try:
                        value=parse();cache.save_detail(identity,kind,value)
                        if kind=='hr_histogram_v1':histogram=value
                    except SyncPaused:raise
                    except Exception:recording_failures+=1
                if want_terrain:
                    report('Terrain · '+str(terrain_done)+'/'+str(len(terrain_rows))+' ready · '+row['date'],terrain_done+terrain_skipped,len(terrain_rows))
                    try:
                        elevation = terrain_summary(raw,activity,request_json=provider)
                        cache.save_detail(identity,'terrain_v1',elevation)
                        if elevation.get('status')=='ok':terrain_done+=1
                        else:terrain_skipped+=1
                        report('Terrain · '+str(terrain_done)+'/'+str(len(terrain_rows))+' ready · '+str(terrain_skipped)+' without usable terrain',terrain_done+terrain_skipped,len(terrain_rows))
                    except (SyncPaused,TerrainDeferred):raise
                    except Exception:
                        terrain_failures += 1
            except (GarminConnectAuthenticationError,GarminConnectTooManyRequestsError):
                garmin_paused = True
                recording_failures += 1
            except SyncPaused:raise
            except TerrainDeferred as error:
                warnings.append(str(error));terrain_paused=True
            except (GarminConnectConnectionError,OSError):
                garmin_paused=True;recording_failures+=1
            except Exception:
                recording_failures += 1
            time.sleep(.2)
        if settings.get('include_terrain') and elevation and elevation.get('status')=='ok':
            row['terrain'] = elevation
        if not easy:
            continue
        total = sum(histogram.values()) if histogram else 0
        if total:
            under = sum(value for hr,value in histogram.items() if int(hr) < settings.get('easy_hr',134))
            row['hr_under_percent'],row['hr_total_seconds'] = under/total*100,total
            row['hr_source'] = 'recorded'
        elif row.get('average_hr'):
            row['hr_under_percent'] = 100 if row['average_hr'] < settings.get('easy_hr',134) else 0
            row['hr_total_seconds'] = row.get('duration') or 0
            row['hr_source'] = 'average HR estimate'
    if recording_failures:
        warnings.append(str(recording_failures)+' original recordings failed; refresh to retry.')
    if terrain_failures:
        warnings.append(str(terrain_failures)+' terrain lookups failed; Garmin elevation is used until refresh.')
    weather = {}
    failures = 0
    for index,row in enumerate(result['runs']):
        job.checkpoint()
        found,saved = cache.detail(row['id'],'weather_v1')
        if allow_download and not terrain_only and settings.get('include_weather') and not found and row.get('is_run',True) and not garmin_paused:
            report('Weather · '+row['date']+' · '+row['title'][:40],index,len(result['runs']))
            try:
                raw = job.request(lambda:client.get_activity_weather(row['id']),'Activity weather · '+row['date'])
                if raw is not None and not isinstance(raw,dict):
                    raise ValueError('Unexpected weather response')
                summary = summarize_weather(dict(activityId=row['id'],startTimeLocal=row['started']),raw)
                saved = {key:summary.get(key) for key in ('temperature','apparentTemperature','dewPoint','humidity','weatherDescription','weatherStation')}
                cache.save_detail(row['id'],'weather_v1',saved)
            except (GarminConnectAuthenticationError,GarminConnectTooManyRequestsError):
                garmin_paused = True
                failures += 1
            except SyncPaused:raise
            except (GarminConnectConnectionError,OSError):
                garmin_paused=True;failures+=1
            except Exception:
                failures += 1
            time.sleep(.2)
        if saved:
            # Read caches written by 0.6 as well as the shared web schema.
            if 'temperatureF' in saved:
                saved = dict(temperature=saved.get('temperatureF'),dewPoint=saved.get('dewPointF'),humidity=saved.get('humidity'))
            weather[row['id']] = saved
    if failures:
        warnings.append(str(failures)+' weather requests failed; refresh to retry.')
    station_rows = {}
    if settings.get('include_station_weather'):
        station_rows,station_warnings = station_weather(cache,activities or [],report,allow_fetch=allow_download and not terrain_only)
        warnings.extend(station_warnings)
    weather = {row['id']:merge_weather(weather.get(row['id']),station_rows.get(row['id'])) for row in result['runs']}
    if garmin_paused:
        warnings.append('Garmin paused optional downloads. Retry later or reconnect in Profile; saved measurements remain available.')
    result['optional_downloads_paused'] = garmin_paused
    result['terrain_downloads_paused'] = terrain_paused
    return health,weather,warnings
