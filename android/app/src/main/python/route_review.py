"""Read-only snapshot of every saved session and all configured route references."""
from datetime import datetime,timezone
import json
from route_review_contract import sanitize_review
from route_preview import thumbnail_route
from route_terrain import metrics,cached_states


def snapshot(cache,routes,settings,today,app_version='',display_units='miles'):
    activities=[]
    for body, in cache.db.execute('SELECT body FROM runs ORDER BY day DESC,id DESC'):
        row=json.loads(body)
        if isinstance(row.get('activityType'),dict):row['activityType']=row['activityType'].get('typeKey')
        activities.append(row)
    references={route['reference']['id'] for route in routes if route.get('reference')}
    recordings={}
    for identity in references:
        found,data=cache.detail(identity,'terrain_v1')
        if found and isinstance(data.get('route'),dict):recordings[identity]=data['route']
    outlines={identity:thumbnail_route(outline) for identity,outline in cache.iter_details('route_outline_v1')}
    details={kind:cache.all_details(kind) for kind in ('laps','interval_fit_v1','effort_v1','weather_v1','gear_v1')}
    details['terrain_v1']={identity:metrics(entry) for identity,entry in cache.iter_details('terrain_v1')}
    return sanitize_review(dict(schema=1,kind='route_review',today=today,generated_at=datetime.now(timezone.utc).isoformat(),
        app_version=app_version,display_units=display_units,settings=settings,activities=activities,routes=routes,
        coverage=[dict(start=first,end=last) for first,last in cache.db.execute('SELECT start,end FROM coverage ORDER BY start')],
        reference_recordings=recordings,outlines=outlines,details=details,
        available=dict(gps_outlines=len(outlines),gps_indexes=cache.db.execute("SELECT count(*) FROM details WHERE kind='route_match_v1'").fetchone()[0],
            elevation_profiles=sum(state==('ok',True) for state in cached_states(cache).values())),
        units=dict(distance='metres',duration='seconds',activity_elevation='metres',reference_elevation='feet',
            profile_elevation='metres',elevation_rate='feet per mile',outline='relative shape, north up, no geographic origin')))
