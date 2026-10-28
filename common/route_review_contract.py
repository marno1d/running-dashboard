"""Explicit local route/elevation review; no credentials or geographic coordinates."""
from comparison_contract import SCALAR,fields,_project,ACTIVITY,SETTINGS,LAP,FIT_INTERVAL,TERRAIN,EFFORT,GEAR

PROFILE_LAP=fields('distance duration intensity gain loss active average_hr start_distance')
REFERENCE=fields('id title date distance duration gain loss stale')
ROUTE=fields('id name shape surface reverse extent suggested_extent profile_ready extent_version extent_mode turn_confidence elevation_source')
ROUTE['reference']=REFERENCE
RECORDING=fields('profile_version suggested_turn suggested_reverse_turn suggested_loop turn_confidence source geometry_version metres_per_unit')
RECORDING.update(profile=[[SCALAR]],heights=[[SCALAR]],laps=[PROFILE_LAP],track=[[SCALAR]])
OUTLINE=dict(segments=[[[SCALAR]]])
SCHEMA=dict(schema=SCALAR,kind=SCALAR,today=SCALAR,generated_at=SCALAR,app_version=SCALAR,display_units=SCALAR,
    units=fields('distance duration activity_elevation reference_elevation profile_elevation elevation_rate outline'),
    settings=SETTINGS,activities=[ACTIVITY],routes=[ROUTE],
    coverage=[fields('start end')],reference_recordings={'*':RECORDING},outlines={'*':OUTLINE},
    details=dict(laps={'*':dict(lapDTOs=[LAP])},interval_fit_v1={'*':FIT_INTERVAL},terrain_v1={'*':TERRAIN},gear_v1={'*':GEAR},
        effort_v1={'*':EFFORT},weather_v1={'*':fields('temperature apparentTemperature dewPoint humidity weatherDescription weatherStation temperatureF dewPointF source')}),
    available=fields('gps_outlines gps_indexes elevation_profiles'))


def sanitize_review(payload):
    clean=_project(payload,SCHEMA)
    if clean.get('schema')!=1 or clean.get('kind')!='route_review':raise ValueError('Invalid route review')
    for key,kind in (('activities',list),('routes',list),('reference_recordings',dict),('settings',dict),('outlines',dict)):
        if not isinstance(clean.get(key),kind):raise ValueError('Missing route review inputs')
    for recording in clean['reference_recordings'].values():
        if not isinstance(recording,dict):raise ValueError('Invalid reference recording')
        profile=recording.get('profile',[])
        if not isinstance(profile,list) or len(profile)>2500 or any(not isinstance(point,list) or len(point)!=3 or any(isinstance(value,bool) or not isinstance(value,(int,float)) for value in point) for point in profile):
            raise ValueError('Invalid elevation profile')
        heights=recording.get('heights',[])
        if not isinstance(heights,list) or len(heights)>2500 or any(not isinstance(point,list) or len(point)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) for v in point) or point[0]<0 for point in heights):raise ValueError('Invalid terrain heights')
        track=recording.get('track',[])
        if not isinstance(track,list) or len(track)>1000 or any(not isinstance(point,list) or len(point)!=3 or any(isinstance(v,bool) or not isinstance(v,(int,float)) for v in point) or point[0]<0 or any(not 0<=v<=1 for v in point[1:]) for point in track):
            raise ValueError('Invalid relative course track')
    for outline in clean['outlines'].values():
        if not isinstance(outline,dict):raise ValueError('Invalid route outline')
        segments=outline.get('segments',[])
        if not isinstance(segments,list) or any(not isinstance(segment,list) for segment in segments) or len(segments)>64 or sum(map(len,segments))>1200:raise ValueError('Invalid route outline')
        for segment in segments:
            if any(not isinstance(point,list) or len(point)!=2 or any(isinstance(value,bool) or not isinstance(value,(int,float)) or not 0<=value<=1 for value in point) for point in segment):
                raise ValueError('Invalid relative route outline')
    return clean


def validate_review(payload):
    clean=sanitize_review(payload)
    if clean!=payload:raise ValueError('Unexpected fields in route review')
    return clean
