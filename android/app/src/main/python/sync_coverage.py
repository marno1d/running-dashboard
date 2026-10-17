"""Coverage counts describe completed work, including successful empty responses."""
from web_sources import terrain


def coverage(cache,rows,start,end,settings):
    def counts(eligible,kind):
        saved=cache.all_details(kind)
        done=sum(r['id'] in saved for r in eligible)
        return dict(done=done,total=len(eligible),pending=len(eligible)-done)
    outdoor=[r for r in rows if r.get('activity_type') in terrain.OUTDOOR_ELEVATION_TYPES]
    saved=cache.all_details('terrain_v1')
    ready=sum((saved.get(r['id']) or {}).get('status')=='ok' for r in outdoor)
    skipped=sum((saved.get(r['id']) or {}).get('status')=='skipped' for r in outdoor)
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
                summaries_complete=not cache.missing(start,end))
