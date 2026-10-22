"""Local reference routes and GPS-overlap suggestions; no mapping service."""
from datetime import datetime
import io
import math
from statistics import median
import zipfile
import fitdecode

KINDS=('easy','easy_long','intervals','short','medium','long','route')
SEEDS=(('lakeview','Lakeview Parkway · Provo'),('jordan','West → Jordan River → south · SLC'),
       ('liberty','Liberty Park · SLC'),('bonneville','Bonneville Shoreline · SLC'))


def recording_data(raw):
    if not isinstance(raw,bytes) or len(raw)>30*1024*1024:raise ValueError('Missing recording')
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            item=next((item for item in archive.infolist() if item.filename.lower().endswith('.fit') and item.file_size<=20*1024*1024),None)
            if item is None:raise ValueError('No FIT recording')
            raw=archive.read(item)
    cells=set();laps=[];altitudes=[];records=[];positions=[];lap_cursor=0
    def num(value):
        return float(value) if isinstance(value,(int,float)) and math.isfinite(value) else None
    with fitdecode.FitReader(io.BytesIO(raw),check_crc=fitdecode.CrcCheck.RAISE,error_handling=fitdecode.ErrorHandling.IGNORE) as reader:
        for frame in reader:
            if not isinstance(frame,fitdecode.FitDataMessage):continue
            get=lambda key:frame.get_value(key,fallback=None)
            if frame.name=='record':
                distance=num(get('distance'))
                lat,lon=num(get('position_lat')),num(get('position_long'))
                if lat is not None and lon is not None:
                    lat,lon=lat*180/2**31,lon*180/2**31
                    if -90<=lat<=90 and -180<=lon<=180:cells.add((round(lat*1000),round(lon*1000)))
                    if -90<=lat<=90 and -180<=lon<=180 and distance is not None:positions.append((distance,lat,lon))
                stamp=get('timestamp');alt=num(get('enhanced_altitude'))
                if alt is None:alt=num(get('altitude'))
                if isinstance(stamp,datetime) and alt is not None:altitudes.append((stamp,alt))
                if distance is not None and distance>=0 and (not records or distance>records[-1][0]):records.append((distance,alt))
            elif frame.name=='lap':
                gain,loss=num(get('total_ascent')),num(get('total_descent'))
                start,end=get('start_time'),get('timestamp')
                if (gain is None or loss is None) and isinstance(start,datetime) and isinstance(end,datetime):
                    values=[alt for stamp,alt in altitudes if start<=stamp<=end]
                    if len(values)>=3:
                        smooth=[median(values[max(0,i-1):i+2]) for i in range(len(values))]
                        up=down=0;anchor=smooth[0]
                        for value in smooth[1:]:
                            delta=value-anchor
                            if abs(delta)>=3:
                                up+=max(0,delta);down+=max(0,-delta);anchor=value
                        if gain is None:gain=up
                        if loss is None:loss=down
                lap_distance=num(get('total_distance'))
                laps.append(dict(distance=lap_distance,duration=num(get('total_timer_time')),intensity=str(get('intensity')).lower(),
                                 gain=gain,loss=loss,active=str(get('intensity')).lower() in ('active','interval','work','work_interval'),
                                 average_hr=num(get('avg_heart_rate')),start_distance=lap_cursor))
                lap_cursor+=lap_distance or 0
    # Bounded, location-aware cells support overlap without retaining full GPS tracks.
    ordered=sorted(cells)
    if len(ordered)>2000:ordered=[ordered[round(i*(len(ordered)-1)/1999)] for i in range(2000)]
    usable=[(distance,alt) for distance,alt in records if alt is not None]
    profile=[]
    if len(usable)>=3:
        origin=usable[0][0];values=[alt for _,alt in usable]
        smooth=[median([values[j] for j in range(max(0,i-1),min(len(values),i+2)) if abs(usable[j][0]-usable[i][0])<=25]) for i in range(len(values))]
        smooth[0]=values[0];smooth[-1]=values[-1]
        anchor=smooth[0];up=down=0
        for i,((distance,_),alt) in enumerate(zip(usable,smooth)):
            delta=alt-anchor
            if abs(delta)>=3 or i==len(usable)-1:
                up+=max(0,delta);down+=max(0,-delta);anchor=alt
            profile.append([distance-origin,up,down])
        if len(profile)>2500:profile=[profile[round(i*(len(profile)-1)/2499)] for i in range(2500)]
    suggested_turn=None;suggested_loop=None
    if len(positions)>2:
        start_distance,lat0,lon0=positions[0]
        radii=[math.hypot(lat-lat0,(lon-lon0)*math.cos(math.radians(lat0)))*111195 for _,lat,lon in positions]
        furthest=max(range(len(radii)),key=radii.__getitem__)
        suggested_turn=positions[furthest][0]-start_distance
        for i in range(1,len(positions)-1):
            if positions[i][0]-start_distance>500 and radii[i]<30 and radii[i]<=radii[i-1] and radii[i]<=radii[i+1]:
                suggested_loop=positions[i][0]-start_distance;break
    return dict(cells=ordered,laps=laps,profile=profile,profile_version=2,suggested_turn=suggested_turn,suggested_loop=suggested_loop)


def gps_overlap(first,second):
    a={tuple(p) for p in first};b={tuple(p) for p in second}
    if len(a)<2 or len(b)<2:return 0
    def covered(source,other):
        return sum(any((x+dx,y+dy) in other for dx in (-1,0,1) for dy in (-1,0,1)) for x,y in source)/len(source)
    ab,ba=covered(a,b),covered(b,a)
    return .7*min(ab,ba)+.3*max(ab,ba)


def gps_coverage(reference,candidate):
    """Fraction of the chosen path covered by a potentially much longer run."""
    a={tuple(p) for p in reference};b={tuple(p) for p in candidate}
    if len(a)<2 or len(b)<2:return 0
    return sum(any((x+dx,y+dy) in b for dx in (-1,0,1) for dy in (-1,0,1)) for x,y in a)/len(a)


def configuration(cache):
    saved=cache.meta('training_routes_v1')
    return saved if isinstance(saved,list) else [dict(id=key,name=name,references={}) for key,name in SEEDS]


def reference(row,data,kind,settings):
    from dashboard_metrics import adjusted_pace, MILE, number
    if len(data.get('cells',[]))<2:raise ValueError('Choose a session with a usable recorded GPS route.')
    interval=kind in ('intervals','short','medium','long')
    selected=settings.get('laps',{}).get(row['id']) if interval else None
    if interval:
        laps=data.get('laps',[])
        indices=selected if selected is not None else [i for i,lap in enumerate(laps) if lap['active']]
        if not indices or any(not isinstance(i,int) or not 0<=i<len(laps) for i in indices):
            raise ValueError('Choose a session with selected work laps. Correct work laps in Sessions first.')
        chosen=[laps[i] for i in indices]
        if any(lap.get(key) is None or lap[key]<0 for lap in chosen for key in ('distance','duration','gain','loss')):
            raise ValueError('The work laps need recorded distance, time, gain and loss.')
        distance,duration,gain,loss=(sum(lap[key] for lap in chosen) for key in ('distance','duration','gain','loss'))
    else:
        distance,duration,gain,loss=(number(row.get(key)) for key in ('distance','duration','elevation_gain','elevation_loss'))
    if not distance or not duration or gain is None or loss is None or gain<0 or loss<0:
        raise ValueError('Choose a reference with recorded distance, time, gain and loss.')
    source=dict(row,distance=distance,elevation_gain=gain,elevation_loss=loss)
    pace=adjusted_pace(source,duration/distance*1000,dict(adjust_elevation=True,adjust_temperature=True))
    return dict(id=row['id'],title=row['title'],date=row['date'],category=row['category'],distance=distance,duration=duration,
                gain=gain/.3048,loss=loss/.3048,gain_per_mile=gain/.3048/(distance/MILE),loss_per_mile=loss/.3048/(distance/MILE),
                base_pace=pace,surface='trail' if row.get('activity_type')=='trail_running' else 'road',lap_selection=selected,
                interval=interval)


def selection(route,kind):
    if kind not in KINDS:raise ValueError('Choose a workout type.')
    refs=route['references'];ref=refs.get(kind)
    if ref is None and kind in ('short','medium','long'):ref=refs.get('intervals')
    if not ref or ref.get('stale'):raise ValueError('Choose a current reference for this workout type in Profile → Routes.')
    result=dict(route_id=route['id'],name=route['name'],kind=kind,reference=ref,interval_rates={})
    if kind in ('intervals','short','medium','long'):
        for key in ('short','medium','long'):
            entry=refs.get(key)
            if not entry or entry.get('stale'):entry=refs.get('intervals')
            if entry and not entry.get('stale'):
                result['interval_rates'][key]={field:entry[field] for field in ('gain_per_mile','loss_per_mile','distance','duration')}
    return result
