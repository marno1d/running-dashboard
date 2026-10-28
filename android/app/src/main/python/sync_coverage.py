"""Coverage counts describe completed work, including successful empty responses."""
from web_sources import terrain
from route_terrain import cached_states
from gear_sync import coverage as gear_coverage


def coverage(cache,rows,start,end,settings):
    def counts(eligible,kind):
        saved=cache.all_details(kind)
        done=sum(r['id'] in saved for r in eligible)
        return dict(done=done,total=len(eligible),pending=len(eligible)-done)
    outdoor=[r for r in rows if r.get('activity_type') in terrain.OUTDOOR_ELEVATION_TYPES]
    saved=cached_states(cache)
    ready=sum(saved.get(r['id'])==('ok',True) for r in outdoor)
    skipped=sum(saved.get(r['id'])==('skipped',True) for r in outdoor)
    from datetime import date
    days=(date.fromisoformat(end)-date.fromisoformat(start)).days+1
    recovered=sum(len(cache.daily(start,end,k)) for k in ('sleep','rhr','hrv'))
    easy=[r for r in rows if r['category'] in ('easy','easy_long')]
    intervals=[r for r in rows if r['category'] in ('short','medium','long')]
    trials=[r for r in rows if r['category']=='trial']
    return dict(terrain=dict(done=ready,total=len(outdoor),skipped=skipped,pending=len(outdoor)-ready-skipped,enabled=bool(settings.get('include_terrain'))),
                recovery=dict(done=recovered,total=days*3,pending=days*3-recovered),
                hr_recordings=counts(easy,'hr_histogram_v1'),interval_recordings=counts(intervals,'interval_fit_v1'),
                trial_recordings=counts(trials,'effort_v1'),weather=counts([r for r in rows if r.get('is_run')],'weather_v1'),
                gear=gear_coverage(cache,rows,settings.get('include_gear',False)),
                summaries_complete=not cache.missing(start,end))
