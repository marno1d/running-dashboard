"""Distance profiles and reviewable course suggestions from downloaded terrain/GPS."""
from bisect import bisect_right
import math

VERSION=1
GEOMETRY_VERSION=2
METRIC_FIELDS=('status','reason','source','elevation_gain','elevation_loss','work_gain','work_loss','samples')


def metrics(entry):
    """Only aggregate elevations belong in dashboard rows or chart points."""
    return {key:entry[key] for key in METRIC_FIELDS if key in entry}


def cached_states(cache):
    """Coverage/picker flags without holding every saved geometry in memory."""
    if cache._terrain_states is None:
        cache._terrain_states={identity:(entry.get('status'),complete(entry)) for identity,entry in cache.iter_details('terrain_v1')}
    return cache._terrain_states


def _turns(path):
    distances=[p[0] for p in path];length=distances[-1]
    def at(distance):
        i=max(0,min(len(path)-2,bisect_right(distances,distance)-1));a,b=path[i:i+2]
        f=(distance-a[0])/(b[0]-a[0]);return a[1]+f*(b[1]-a[1]),a[2]+f*(b[2]-a[2])
    def separation(a,b):return math.hypot(a[0]-b[0],a[1]-b[1])
    start=path[0][1:];candidates=[]
    for distance,x,y in path[1:-1]:
        span=min(distance,length-distance)
        if span<max(300,length*.12) or separation(start,(x,y))<100:continue
        errors=[separation(at(distance-span*i/20),at(distance+span*i/20)) for i in range(2,21)]
        fraction=sum(error<=60 for error in errors)/len(errors)
        if fraction>=.85:candidates.append((span*fraction,sum(min(error,120) for error in errors)/len(errors),distance))
    turn=reverse_turn=None
    if candidates:
        best=max(score for score,_,_ in candidates)
        eligible=[(error,distance) for score,error,distance in candidates if score>=best*.98]
        best_error=min(error for error,_ in eligible)
        # Match quality resolves nearby candidates. Only equivalent repeat
        # traversals use the earliest-turn tie break.
        turn=min(distance for error,distance in eligible if error<=best_error+.5)
        reverse_turn=min(length-distance for error,distance in eligible if error<=best_error+.5)
    return dict(suggested_turn=turn,suggested_reverse_turn=reverse_turn,turn_confidence='retrace' if turn is not None else 'review')


def retune(data):
    """Improve suggestions using saved relative geometry, without fetching terrain."""
    if data.get('geometry_version')==GEOMETRY_VERSION or len(data.get('track',[]))<2:return data
    track=data['track'];length=track[-1][0]
    travelled=sum(math.hypot(b[1]-a[1],b[2]-a[2]) for a,b in zip(track,track[1:]))
    if travelled<=0:return data
    scale=data.get('metres_per_unit') or length/travelled
    path=[[distance,x*scale,y*scale] for distance,x,y in track]
    return dict(data,**_turns(path),geometry_version=GEOMETRY_VERSION,metres_per_unit=scale)


def geometry(points):
    """Bounded relative path; geographic positions never enter the saved result."""
    points=[p for p in points if all(isinstance(p.get(k),(int,float)) and math.isfinite(p[k]) for k in ('distanceMeters','lat','lng'))]
    if len(points)<2:return dict(track=[],suggested_turn=None,suggested_loop=None,turn_confidence='review')
    origin=points[0]['distanceMeters'];lat0=points[0]['lat'];lon0=points[0]['lng']
    cosine=math.cos(math.radians(lat0));path=[]
    for p in points:
        distance=p['distanceMeters']-origin
        if path and distance<=path[-1][0]:continue
        path.append((distance,((p['lng']-lon0+180)%360-180)*cosine*111195,-(p['lat']-lat0)*111195))
    if len(path)<2 or path[-1][0]<=0:return dict(track=[],suggested_turn=None,suggested_loop=None,turn_confidence='review')
    if len(path)>1000:path=[path[round(i*(len(path)-1)/999)] for i in range(1000)]
    def separation(a,b):return math.hypot(a[0]-b[0],a[1]-b[1])
    start=path[0][1:];length=path[-1][0]
    # Compare the actual outward and return paths at equal travelled distances.
    # A farthest-from-start point is not necessarily the turnaround on a winding path.
    turns=_turns(path)
    loop=None
    radii=[separation(start,p[1:]) for p in path]
    for i in range(1,len(path)-1):
        if path[i][0]>500 and radii[i]<30 and radii[i]<=radii[i-1] and radii[i]<=radii[i+1]:
            loop=path[i][0];break
    if loop is None and length>500 and radii[-1]<30:loop=length
    left=min(p[1] for p in path);top=min(p[2] for p in path)
    scale=max(max(p[1] for p in path)-left,max(p[2] for p in path)-top,1)
    return dict(track=[[round(d,2),round((x-left)/scale,6),round((y-top)/scale,6)] for d,x,y in path],
        **turns,suggested_loop=loop,geometry_version=GEOMETRY_VERSION,metres_per_unit=scale)


def build(profile,route,source):
    """Use precisely the same 1 m accumulation policy as Session terrain totals."""
    usable=[p for p in profile if isinstance(p.get('elevationMeters'),(int,float)) and math.isfinite(p['elevationMeters'])]
    if len(usable)!=len(profile) or len(usable)<2:raise ValueError('Terrain elevations are incomplete. Retry when terrain is available.')
    origin=usable[0]['distanceMeters'];anchor=usable[0]['elevationMeters'];up=down=0;cumulative=[]
    for point in usable:
        distance=point['distanceMeters']-origin
        if cumulative and distance<=cumulative[-1][0]:continue
        delta=point['elevationMeters']-anchor
        if abs(delta)>=1:
            up+=max(0,delta);down+=max(0,-delta);anchor=point['elevationMeters']
        cumulative.append([distance,up,down])
    if len(cumulative)<2:raise ValueError('Terrain needs a positive recorded distance.')
    result=geometry(route)
    # Preserve the downloaded heights as well as calculated totals, so future
    # elevation-policy changes can rebuild locally without querying the provider.
    result.update(profile=cumulative,heights=[[p['distanceMeters']-origin,p['elevationMeters']] for p in usable],profile_version=VERSION,source=source)
    return result


def ready(data):
    return isinstance(data,dict) and data.get('profile_version')==VERSION and str(data.get('source','')).startswith('opentopodata:') and len(data.get('profile',[]))>=2


def complete(entry):
    """Old totals remain displayable, but only saved profiles finish terrain sync."""
    if not entry:return False
    if entry.get('status')=='skipped':return True
    data=entry.get('route')
    return entry.get('status')=='ok' and ready(data) and len(data.get('heights',[]))>=2


def display_track(data,reverse=False):
    track=data.get('track',[])
    if reverse and track:
        length=data['profile'][-1][0]
        return [[max(0,length-d),x,y] for d,x,y in reversed(track)]
    return track
