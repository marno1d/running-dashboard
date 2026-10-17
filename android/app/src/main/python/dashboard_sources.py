"""Web weather/terrain sources with app-private caches and no stored GPS."""
from argparse import Namespace
from datetime import date, datetime, timedelta, timezone
import io
import zipfile

from web_sources import dashboard, stations, terrain


def original_zip(raw):
    """The shared web readers consume ZIPs; Garmin can also return a bare FIT."""
    if not isinstance(raw,bytes):
        raise ValueError('Missing original recording')
    stream = io.BytesIO(raw)
    if zipfile.is_zipfile(stream):
        stream.seek(0)
        return stream
    result = io.BytesIO()
    with zipfile.ZipFile(result,'w') as archive:
        archive.writestr('activity.fit',raw)
    result.seek(0)
    return result


def station_weather(cache, activities, report, now=None, allow_fetch=True):
    now = now or datetime.now(timezone.utc)
    selected = [(a,a.get('_station_match')) for a in activities]
    required = stations.required_station_dates(selected,90)
    observations = {}
    warnings = []
    for station,days in required.items():
        first,final = min(days).isoformat(),max(days).isoformat()
        saved = cache.daily(first,final,'station:'+station)
        missing = set()
        for day in days:
            entry = saved.get(day.isoformat())
            # Historical empty responses are final; today's observations are provisional.
            if entry is None or (not entry.get('final',False) and (day < now.date() or now.timestamp()-entry.get('checked_at',0) >= 6*3600)):
                missing.add(day)
        for start,end in stations.group_missing_dates(missing) if allow_fetch else []:
            report('Station weather · '+station+' · '+start.isoformat()+' to '+end.isoformat())
            try:
                check=getattr(report,'checkpoint',None)
                if check is not None:check()
                csv = stations.fetch_station_csv(station,start,end,retries=1,retry_base_delay=1)
                rows = stations.parse_station_csv(csv)
                for day in stations.inclusive_dates(start,end):
                    entry = dict(checked_at=now.timestamp(),final=day<now.date(),rows=[stations.observation_to_json(r) for r in rows if r['valid'].date()==day])
                    cache.save_day(day.isoformat(),'station:'+station,entry)
                    saved[day.isoformat()] = entry
            except Exception as error:
                from sync_job import SyncPaused
                if isinstance(error,SyncPaused):raise
                warnings.append('Station weather '+station+' could not update; Garmin weather is used where available.')
        rows = [stations.observation_from_json(r) for entry in saved.values() for r in entry['rows']]
        observations[station] = sorted((r for r in rows if r is not None),key=lambda r:r['valid'])
    result = {}
    for activity,match in selected:
        summary = stations.build_activity_summary(activity,match,observations,90)
        if summary['status']=='ok':
            result[str(activity['activityId'])] = summary
    return result,warnings


def terrain_summary(raw, activity, request_json=None):
    """Use the web sampler/provider, retaining only its aggregate result."""
    if terrain.type_key(activity) not in terrain.OUTDOOR_ELEVATION_TYPES:
        return dict(status='skipped',reason='no_route')
    stream = original_zip(raw)
    route = terrain.route_points_from_fit(stream)
    samples = terrain.sample_track(route,75,500) if len(route)>=2 else []
    if len(samples)<2:
        return dict(status='skipped',reason='no_route')
    args = Namespace(chunk_size=100,api_base=terrain.DEFAULT_API_BASE,dataset=terrain.DEFAULT_DATASET,
                     delay=0 if request_json is not None else 1.05,timeout=25)
    profile = terrain.query_elevations(samples,args,request_json=request_json) if request_json is not None else terrain.query_elevations(samples,args)
    summary = terrain.summarize_profile(profile,1.0)
    if summary['elevationGainMeters'] is None:
        return dict(status='skipped',reason='no_elevation',samples=len(profile))
    stream.seek(0)
    work = terrain.profile_in_windows(profile,terrain.active_lap_windows_from_fit(stream))
    active = terrain.summarize_profile(work,1.0)
    return dict(status='ok',source='opentopodata:'+terrain.DEFAULT_DATASET,
                elevation_gain=summary['elevationGainMeters'],elevation_loss=summary['elevationLossMeters'],
                work_gain=active['elevationGainMeters'],work_loss=active['elevationLossMeters'],samples=len(profile))


def merge_weather(garmin, station):
    merged = dashboard.merged_weather(garmin or {},station or {})
    temperature = merged.get('temperature')
    if temperature is None:
        temperature = merged.get('apparentTemperature')
    return dict(temperatureF=temperature,dewPointF=merged.get('dewPoint'),humidity=merged.get('humidity'),
                source=merged.get('weatherSource'),station=merged.get('weatherStationId'),
                observation_time=merged.get('weatherObservationTime'),
                observation_offset=merged.get('weatherObservationOffsetMinutes'))
