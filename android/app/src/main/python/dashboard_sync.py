"""Incremental Garmin health/weather downloads into the app-private cache."""
from datetime import date, timedelta
import time
from garminconnect.exceptions import GarminConnectAuthenticationError, GarminConnectTooManyRequestsError
from garmin_health import merged_summary
from garmin_weather import summarize_weather
from dashboard_metrics import number
from recording_hr import heart_rate_histogram
from garminconnect import Garmin
from best_effort import best_from_original
from dashboard_sources import original_zip, station_weather, terrain_summary, merge_weather
from web_sources import dashboard, terrain


def sync_extras(client, cache, result, settings, refresh, report, activities=None):
    start,end = result['start'],result['end']
    recent = (date.today()-timedelta(days=2)).isoformat()
    health_parts = {kind:cache.daily(start,end,kind) for kind in ('sleep','rhr','hrv')}
    warnings = []
    garmin_paused = False
    if settings.get('include_recovery'):
        day = date.fromisoformat(start)
        final = date.fromisoformat(end)
        total = (final-day).days+1
        index = 0
        failures = 0
        calls = {'sleep':client.get_sleep_data,'rhr':client.get_rhr_day,'hrv':client.get_hrv_data}
        while day <= final:
            stamp = day.isoformat()
            report('Recovery · '+stamp,index,total)
            for kind,call in calls.items():
                if garmin_paused or (stamp in health_parts[kind] and not (refresh and stamp >= recent)):
                    continue
                try:
                    raw = call(stamp)
                    if raw is not None and not isinstance(raw,(dict,list)):
                        raise ValueError('Unexpected health response')
                    summarized = merged_summary(stamp,{kind:raw})
                    fields = {'sleep':('sleepHours','sleepScore'),'rhr':('restingHeartRate',),'hrv':('hrvLastNightAvg',)}[kind]
                    part = {key:number(summarized.get(key)) for key in fields}
                    cache.save_day(stamp,kind,part)
                    health_parts[kind][stamp] = part
                except (GarminConnectAuthenticationError,GarminConnectTooManyRequestsError):
                    garmin_paused = True
                    failures += 1
                except Exception:
                    failures += 1
                time.sleep(.2)
            day += timedelta(days=1)
            index += 1
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
    for index,row in enumerate(result['runs']):
        identity = row['id']
        easy = row['category'] in ('easy','easy_long')
        interval = row['category'] in ('short','medium','long')
        have_hr,histogram = cache.detail(identity,'hr_histogram_v1')
        have_interval,fit_interval = cache.detail(identity,'interval_fit_v1')
        have_trial,trial = cache.detail(identity,'effort_v1')
        have_terrain,elevation = cache.detail(identity,'terrain_v1')
        use_recordings = settings.get('include_recordings',False) and not garmin_paused
        want_hr = use_recordings and easy and not have_hr
        want_interval = use_recordings and interval and not have_interval
        want_trial = use_recordings and row['category']=='trial' and not have_trial
        activity = indexed.get(identity,dict(activityId=identity,activityType={'typeKey':row.get('activity_type','running')}))
        outdoor = terrain.type_key(activity) in terrain.OUTDOOR_ELEVATION_TYPES
        want_terrain = settings.get('include_terrain',False) and outdoor and not have_terrain and not garmin_paused
        if want_hr or want_interval or want_trial or want_terrain:
            report('Reading original recording · '+row['date']+' · '+row['title'][:40],index,len(result['runs']))
            try:
                raw = client.download_activity(identity,dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
                if want_hr:
                    histogram = heart_rate_histogram(raw)
                    cache.save_detail(identity,'hr_histogram_v1',histogram)
                if want_interval:
                    fit_interval = dashboard.interval_laps_from_fit(original_zip(raw))
                    cache.save_detail(identity,'interval_fit_v1',fit_interval)
                if want_trial:
                    trial = best_from_original(raw)
                    cache.save_detail(identity,'effort_v1',trial)
                if want_terrain:
                    report('Terrain elevation · '+row['date'],index,len(result['runs']))
                    try:
                        elevation = terrain_summary(raw,activity)
                        cache.save_detail(identity,'terrain_v1',elevation)
                    except Exception:
                        terrain_failures += 1
            except (GarminConnectAuthenticationError,GarminConnectTooManyRequestsError):
                garmin_paused = True
                recording_failures += 1
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
        found,saved = cache.detail(row['id'],'weather_v1')
        if settings.get('include_weather') and not found and row.get('is_run',True) and not garmin_paused:
            report('Weather · '+row['date']+' · '+row['title'][:40],index,len(result['runs']))
            try:
                raw = client.get_activity_weather(row['id'])
                if raw is not None and not isinstance(raw,dict):
                    raise ValueError('Unexpected weather response')
                summary = summarize_weather(dict(activityId=row['id'],startTimeLocal=row['started']),raw)
                saved = {key:summary.get(key) for key in ('temperature','apparentTemperature','dewPoint','humidity','weatherDescription','weatherStation')}
                cache.save_detail(row['id'],'weather_v1',saved)
            except (GarminConnectAuthenticationError,GarminConnectTooManyRequestsError):
                garmin_paused = True
                failures += 1
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
        station_rows,station_warnings = station_weather(cache,activities or [],report)
        warnings.extend(station_warnings)
    weather = {row['id']:merge_weather(weather.get(row['id']),station_rows.get(row['id'])) for row in result['runs']}
    if garmin_paused:
        warnings.append('Garmin paused optional downloads. Retry later or reconnect in Profile; saved measurements remain available.')
    result['optional_downloads_paused'] = garmin_paused
    return health,weather,warnings
