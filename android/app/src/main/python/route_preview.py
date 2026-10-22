"""Small, north-up route outlines. Retain shape, not geographic coordinates."""
from datetime import datetime
import io
import math
import zipfile
import fitdecode


def thumbnail_route(outline):
    """Thin relative outlines for lists, keeping gaps and segment endpoints."""
    segments=(outline or {}).get('segments',[])
    total=sum(map(len,segments))
    result=[]
    for segment in segments:
        budget=max(2,round(96*len(segment)/max(1,total)))
        if len(segment)>budget:
            segment=[segment[round(i*(len(segment)-1)/(budget-1))] for i in range(budget)]
        result.append(segment)
    return dict(segments=result)


def project_route(segments):
    segments = [segment for segment in segments if len(segment)>=2][:64]
    if not segments:
        return dict(segments=[])
    origin = segments[0][0][1]
    latitude = sum(point[0] for segment in segments for point in segment)/sum(map(len,segments))
    cosine = max(.001,math.cos(math.radians(latitude)))
    projected=[]
    for segment in segments:
        points=[]
        previous=origin
        for lat,lon in segment:
            lon=previous+(lon-previous+180)%360-180
            points.append((lon*cosine,-lat));previous=lon
        projected.append(points)
    xs=[p[0] for segment in projected for p in segment]
    ys=[p[1] for segment in projected for p in segment]
    left,top=min(xs),min(ys)
    span=max(max(xs)-left,max(ys)-top)
    if span<1e-8:
        return dict(segments=[])
    total=sum(map(len,projected))
    outline=[]
    for segment in projected:
        budget=max(2,round(1000*len(segment)/total))
        if len(segment)>budget:
            segment=[segment[round(i*(len(segment)-1)/(budget-1))] for i in range(budget)]
        outline.append([[round((x-left)/span,6),round((y-top)/span,6)] for x,y in segment])
    return dict(segments=outline)


def route_from_original(raw):
    if not isinstance(raw,bytes) or len(raw)>30*1024*1024:
        raise ValueError('Missing or oversized original recording')
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            item=next((item for item in archive.infolist() if item.filename.lower().endswith('.fit') and item.file_size<=20*1024*1024),None)
            if item is None:
                raise ValueError('No FIT recording')
            raw=archive.read(item)
    segments=[]
    current=[]
    previous=None
    with fitdecode.FitReader(io.BytesIO(raw),check_crc=fitdecode.CrcCheck.RAISE,
                             error_handling=fitdecode.ErrorHandling.IGNORE) as reader:
        for frame in reader:
            if not isinstance(frame,fitdecode.FitDataMessage) or frame.name!='record':
                continue
            lat=frame.get_value('position_lat',fallback=None)
            lon=frame.get_value('position_long',fallback=None)
            stamp=frame.get_value('timestamp',fallback=None)
            if not isinstance(lat,(int,float)) or not isinstance(lon,(int,float)):
                if current:segments.append(current)
                current=[];previous=None;continue
            lat,lon=lat*180/2**31,lon*180/2**31
            if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:
                if current:segments.append(current)
                current=[];previous=None;continue
            if previous:
                dy=lat-previous[0];dx=(lon-previous[1]+180)%360-180
                distance=math.hypot(dy,dx*math.cos(math.radians(lat)))*111195
                elapsed=(stamp-previous[2]).total_seconds() if isinstance(stamp,datetime) and isinstance(previous[2],datetime) else None
                if elapsed is not None and (elapsed>90 or elapsed<=0 or distance/max(elapsed,1)>45):
                    if current:segments.append(current)
                    current=[]
            if not current or current[-1]!=(lat,lon):current.append((lat,lon))
            previous=lat,lon,stamp
    if current:segments.append(current)
    return project_route(segments)
