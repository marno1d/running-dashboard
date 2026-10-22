"""Project timed workouts onto a measured elevation profile, keeping phases separate."""
from bisect import bisect_right
import math
from statistics import median

SHAPES=('out_back','loop','one_way')
DEFAULTS={'short':dict(warmup=10,reps=10,work=3,cooldown=10),
          'medium':dict(warmup=10,reps=6,work=5,cooldown=10),
          'long':dict(warmup=10,reps=3,work=10,cooldown=10)}
WALKING_PACE=1200/1.609344  # Configurable initial 20:00/mi, stored as seconds/km.


class RoutePath:
    def __init__(self,profile,shape='one_way',extent=None,reverse=False,turn=None):
        if shape not in SHAPES or len(profile)<2:raise ValueError('Choose a route with a recorded elevation profile.')
        if any(len(p)!=3 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in p) for p in profile):raise ValueError('Invalid elevation profile.')
        if profile[0][0]!=0 or any(b[0]<=a[0] or b[1]<a[1] or b[2]<a[2] for a,b in zip(profile,profile[1:])):raise ValueError('Invalid elevation profile.')
        if reverse:
            length,up,down=profile[-1]
            profile=[[length-d,down-loss,up-gain] for d,gain,loss in reversed(profile)]
        self.profile=profile;self.distances=[p[0] for p in profile];self.length=profile[-1][0]
        if self.length<=0:raise ValueError('The reference needs a positive distance.')
        self.extent=min(self.length,max(1,float(extent or self.length)));self.shape=shape
        self.turn=max(1,float(turn or self.extent))
    def forward(self,distance):
        if distance>self.extent:
            up,down=self.forward(self.extent)
            return up*distance/self.extent,down*distance/self.extent
        i=max(0,min(len(self.profile)-2,bisect_right(self.distances,distance)-1))
        a,b=self.profile[i:i+2];fraction=(distance-a[0])/(b[0]-a[0])
        return a[1]+(b[1]-a[1])*fraction,a[2]+(b[2]-a[2])*fraction
    def cumulative(self,distance):
        distance=max(0,distance)
        if self.shape=='one_way':return self.forward(distance)
        if self.shape=='loop':
            cycles=int(distance/self.extent);local=distance-cycles*self.extent
            up,down=self.forward(self.extent);a,b=self.forward(local)
            return up*cycles+a,down*cycles+b
        cycles=int(distance/(2*self.turn));local=distance-cycles*2*self.turn
        up,down=self.forward(self.turn);base=cycles*(up+down)
        if local<=self.turn:
            a,b=self.forward(local);return base+a,base+b
        a,b=self.forward(2*self.turn-local)
        return base+up+down-b,base+down+up-a
    def delta(self,start,end):
        a,b=self.cumulative(start),self.cumulative(end)
        return max(0,b[0]-a[0]),max(0,b[1]-a[1])
    def beyond_reference(self,distance):
        return self.turn>self.extent+.5 if self.shape=='out_back' else self.shape=='one_way' and distance>self.extent+.5


def workout_definition(settings,kind):
    if kind in ('easy','easy_long'):
        value=float(settings.get('target_easy_long_minutes' if kind=='easy_long' else 'target_easy_minutes',80 if kind=='easy_long' else 45))
        if not math.isfinite(value) or not 5<=value<=360:raise ValueError('Easy duration must be 5–360 minutes.')
        return dict(duration=value)
    if kind not in DEFAULTS:raise ValueError('Unknown workout type.')
    values=dict(DEFAULTS[kind],**((settings.get('workout_definitions') or {}).get(kind) or {}))
    values={key:float(values[key]) for key in DEFAULTS[kind]}
    if not all(math.isfinite(v) for v in values.values()) or not 0<=values['warmup']<=120 or not 0<=values['cooldown']<=120 or not 1<=values['reps']<=40 or values['reps']!=int(values['reps']) or not .5<=values['work']<=60:
        raise ValueError('Use 0–120 min warm-up/cooldown, 1–40 reps, and 0.5–60 min work.')
    values['reps']=int(values['reps'])
    if values['warmup']+values['cooldown']+values['reps']*(values['work']+1)>360:raise ValueError('Keep the planned workout within six hours.')
    return values


def phases_for(settings,kind,easy_pace,work_pace=None):
    definition=workout_definition(settings,kind)
    needs_easy=kind in ('easy','easy_long') or definition.get('warmup',0)>0 or definition.get('cooldown',0)>0
    if needs_easy and (not easy_pace or easy_pace<=0):raise ValueError('A reliable 128 bpm easy-pace estimate is needed for this surface.')
    if kind in ('easy','easy_long'):return [dict(kind='easy',duration=definition['duration']*60,base_pace=easy_pace)]
    if not work_pace or work_pace<=0:raise ValueError('A 5K basis is needed for interval pace.')
    walking=float(settings.get('target_walking_pace',WALKING_PACE))
    if not math.isfinite(walking) or not 240<=walking<=2400:raise ValueError('Set a walking pace from 4:00 to 40:00 per km in Profile.')
    phases=[]
    if definition['warmup']:phases.append(dict(kind='warmup',duration=definition['warmup']*60,base_pace=easy_pace))
    for rep in range(definition['reps']):
        phases.append(dict(kind='work',rep=rep+1,duration=definition['work']*60,base_pace=work_pace))
        phases.append(dict(kind='walk',rep=rep+1,duration=60,base_pace=walking))
    if definition['cooldown']:phases.append(dict(kind='cooldown',duration=definition['cooldown']*60,base_pace=easy_pace))
    return phases


def simulate(path,phases,settings,fixed_distance=None):
    from dashboard_metrics import upcoming_pace
    position=0;timeline=[];work_distance=work_time=work_gain=work_loss=0
    for phase in phases:
        start=position;remaining=phase['duration'];elapsed=0
        while remaining>1e-7:
            step=100-(position%100)
            if step<.001:step=100
            if fixed_distance is not None:step=min(step,fixed_distance-position)
            if step<=1e-7:break
            gain,loss=path.delta(position,position+step)
            pace=phase['base_pace'] if phase['kind']=='walk' else upcoming_pace(phase['base_pace'],step,dict(target_temperature=settings.get('target_temperature',45),target_humidity=settings.get('target_humidity'),target_gain=gain/.3048,target_loss=loss/.3048))
            dt=step/1000*pace
            fraction=1 if fixed_distance is not None else min(1,remaining/dt)
            position+=step*fraction;elapsed+=dt*fraction;remaining-=dt*fraction
            if fixed_distance is not None and position>=fixed_distance-1e-7:break
        gain,loss=path.delta(start,position)
        entry=dict(kind=phase['kind'],start=start,end=position,duration=elapsed,gain=gain/.3048,loss=loss/.3048)
        if 'rep' in phase:entry['rep']=phase['rep']
        timeline.append(entry)
        if phase['kind']=='work':
            work_distance+=position-start;work_time+=elapsed;work_gain+=gain/.3048;work_loss+=loss/.3048
    gain,loss=path.delta(0,position);duration=sum(p['duration'] for p in timeline)
    return dict(distance=position,duration=duration,gain=gain/.3048,loss=loss/.3048,pace=duration/position*1000 if position else None,
                work_distance=work_distance,work_duration=work_time,work_gain=work_gain,work_loss=work_loss,
                work_pace=work_time/work_distance*1000 if work_distance else None,turnaround=path.turn if path.shape=='out_back' else None,
                extrapolated=path.beyond_reference(position),phases=timeline)


def project(profile,shape,extent,reverse,phases,settings,fixed_distance=None):
    if shape!='out_back':return simulate(RoutePath(profile,shape,extent,reverse),phases,settings,fixed_distance)
    if fixed_distance is not None:
        return simulate(RoutePath(profile,shape,extent,reverse,turn=fixed_distance/2),phases,settings,fixed_distance)
    lo=1;hi=max(100,sum(p['duration']/p['base_pace']*1000 for p in phases))
    for _ in range(12):
        plan=simulate(RoutePath(profile,shape,extent,reverse,turn=hi),phases,settings)
        if plan['distance']<=2*hi:break
        hi*=2
    for _ in range(20):
        turn=(lo+hi)/2;plan=simulate(RoutePath(profile,shape,extent,reverse,turn=turn),phases,settings)
        error=plan['distance']-2*turn
        if abs(error)<.5:return plan
        if error>0:lo=turn
        else:hi=turn
    return plan


def infer_workout(data,kind,settings,identity):
    laps=data.get('laps',[]);selected=settings.get('laps',{}).get(identity)
    indices=[i for i,lap in enumerate(laps) if (i in selected if selected is not None else lap.get('active'))]
    if not indices:raise ValueError('This session has no selected work laps. Correct work laps in Sessions first.')
    groups=[]
    for i in indices:
        if groups and i==groups[-1][-1]+1:groups[-1].append(i)
        else:groups.append([i])
    if any(not lap.get('duration') for lap in laps):raise ValueError('The recording needs lap timer durations.')
    warmup=sum(lap['duration'] for lap in laps[:indices[0]])/60
    tail=laps[indices[-1]+1:]
    # One minute of walking is modeled after the last rep too, even when Garmin
    # folds that minute into a longer cooldown lap.
    cooldown=max(0,sum(lap['duration'] for lap in tail)-60)/60
    walking=[laps[i+1] for i in indices if i+1<len(laps) and i+1 not in indices and laps[i+1].get('distance') and laps[i+1].get('intensity') in ('rest','recovery')]
    walk_pace=sum(lap['duration'] for lap in walking)/sum(lap['distance'] for lap in walking)*1000 if walking else None
    values=dict(warmup=round(warmup,1),cooldown=round(cooldown,1),reps=len(groups),work=round(median(sum(laps[i]['duration'] for i in group) for group in groups)/60,2))
    workout_definition(dict(workout_definitions={kind:values}),kind)
    if walk_pace is not None and not 240<=walk_pace<=2400:walk_pace=None
    return values,walk_pace


def apply_route(target,route,data,settings):
    """Only aggregate results cross into the dashboard; profiles stay in private cache."""
    from dashboard_metrics import MILE,positive
    target.update(route_engine=2,route_name=route['name'],route_surface=route['surface'],route_shape=route['shape'])
    profile=data.get('profile',[])
    if len(profile)<2:raise ValueError('Open Routes and select this route once to load its recorded elevation profile.')
    easy=next((p for p in target.get('easy',[]) if p['surface']==route['surface'] and not p.get('error')),None)
    easy_pace=easy.get('base_pace') if easy else None
    plans=[];by_kind={r['category']:r for r in target.get('rows',[])}
    for kind in ('easy','easy_long','short','medium','long'):
        row=by_kind.get(kind);definition=workout_definition(settings,kind)
        try:
            phases=phases_for(settings,kind,easy_pace,row.get('base_pace') if row else None)
            plan=project(profile,route['shape'],route['extent'],route.get('reverse',False),phases,settings)
        except ValueError as error:plan=dict(error=str(error))
        plan.update(kind=kind,surface=route['surface']);plans.append(plan)
        if row is not None:
            row.update(reps=f"{definition['reps']} × {definition['work']:g} min",pace=plan.get('work_pace'),distance_basis=plan.get('work_distance'))
            row['delta']=row['pace']-row['base_pace'] if row['pace'] else None
    target['route_plans']=plans
    distances=[MILE,5000,10000,21097.5,42195]
    custom=positive(settings.get('race_distance_miles'))
    if custom:distances.append(custom*MILE)
    for race,distance in zip(target.get('races',[]),distances):
        base=race['base_duration']/distance*1000
        plan=project(profile,route['shape'],route['extent'],route.get('reverse',False),[dict(kind='race',duration=1e12,base_pace=base)],settings,distance)
        race.update(duration=plan['duration'],pace=plan['pace'],gain=plan['gain'],loss=plan['loss'],extrapolated=plan['extrapolated'],distance=distance)


def invalidate(target,error):
    target.update(route_engine=2,route_error=str(error),route_plans=[])
    for row in target.get('rows',[]):row['pace']=None
    for row in target.get('races',[]):row.update(pace=None,duration=None)
