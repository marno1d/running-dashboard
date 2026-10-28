"""Small, on-demand workout drawings from cached terrain; no map/network requests."""
from bisect import bisect_right
import math

from dashboard_metrics import upcoming_pace
from route_workouts import RoutePath,course_profile
from route_terrain import display_track


def trace(route,data,plan):
    distance=plan.get('distance',0);phases=plan.get('phases',[])
    if not isinstance(distance,(int,float)) or not math.isfinite(distance) or not 0<distance<=200_000 or not 1<=len(phases)<=100:
        raise ValueError('Reopen the target card to load its workout.')
    profile=course_profile(route,data)
    reverse=route.get('reverse',False) if route['shape']!='loop' else False
    path=RoutePath(profile,route['shape'],route['extent'],reverse,turn=plan.get('turnaround'))
    track=display_track(data,route.get('reverse',False))
    if len(track)<2:raise ValueError('This reference has no cached GPS drawing. Choose another reference in Routes.')
    track_distances=[p[0] for p in track]
    origin=(data.get('heights') or [[0,0]])[-1 if route.get('reverse') else 0][1]
    conditions=plan.get('trace_conditions') or {}
    settings=dict(target_temperature=conditions.get('target_temperature',45),target_humidity=conditions.get('target_humidity'))
    paces=[];boundaries={0.,float(distance)};previous=0
    for index,phase in enumerate(phases):
        start,end,base=(phase[key] for key in ('start','end','base_pace'))
        if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (start,end,base)) or abs(start-previous)>.01 or not start<=end<=distance+.01 or base<=0:
            raise ValueError('Reopen the target card to load its workout.')
        boundaries.update((start,end));position=start
        while position<end-1e-7:
            step=100-position%100
            if step<.001:step=100
            gain,loss=path.delta(position,position+step)
            pace=base if phase['kind']=='walk' else upcoming_pace(base,step,dict(settings,target_gain=gain/.3048,target_loss=loss/.3048))
            stop=min(end,position+step)
            paces.append([round(position,5),round(stop,5),round(pace,3),index]);position=stop
        previous=end
    if abs(previous-distance)>.01:raise ValueError('Reopen the target card to load its workout.')
    # Bound the drawing independently of the number of recordings in the cache.
    count=min(1600,max(2,math.ceil(distance/25)))
    boundaries.update(distance*i/count for i in range(count+1))
    period=path.extent if path.shape=='loop' else 2*path.turn if path.shape=='out_back' else None
    if period:
        for cycle in range(math.ceil(distance/period)+1):
            boundaries.add(min(distance,cycle*period))
            if path.shape=='out_back':boundaries.add(min(distance,cycle*period+path.turn))
    else:boundaries.add(min(distance,path.extent))
    nodes=[]
    for at in sorted(boundaries):
        if path.shape=='loop':local=at%path.extent
        elif path.shape=='out_back':
            local=at%(2*path.turn)
            if local>path.turn:local=2*path.turn-local
        else:local=at
        # Never invent GPS coordinates beyond the saved route. Elevation remains
        # explicitly modeled using the same average-rate extrapolation as targets.
        estimated=local>min(path.extent,track_distances[-1])+.01
        x=y=None
        if not estimated:
            i=max(0,min(len(track)-2,bisect_right(track_distances,local)-1));a,b=track[i:i+2]
            fraction=max(0,min(1,(local-a[0])/max(.001,b[0]-a[0])))
            x=round(a[1]+(b[1]-a[1])*fraction,6);y=round(a[2]+(b[2]-a[2])*fraction,6)
        up,down=path.cumulative(at)
        nodes.append([round(at,5),x,y,round((origin+up-down)/.3048,3)])
    return dict(nodes=nodes,paces=paces,distance=distance,source=data.get('source','Downloaded terrain'))
