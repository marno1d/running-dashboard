"""Small, reusable GPS indexes for reference discovery, separate from FIT profiles."""
import math
from route_preview import project_route,thumbnail_route
from training_routes import gps_coverage


def from_details(details):
    """Read Garmin's bounded details polyline; never retain its raw response."""
    geo=details.get('geoPolylineDTO') if isinstance(details,dict) else None
    if isinstance(details,dict) and 'geoPolylineDTO' in details and geo is None and not details.get('pendingData'):
        return dict(cells=[],outline=dict(segments=[]))
    if not isinstance(geo,dict) or not isinstance(geo.get('polyline'),list):
        raise ValueError('GPS response unavailable')
    points=geo['polyline']
    if len(points)>10000:raise ValueError('Oversized GPS response')
    cells=set();segments=[];segment=[];valid=0
    for point in points:
        lat=point.get('lat') if isinstance(point,dict) else None
        lon=point.get('lon') if isinstance(point,dict) else None
        if (isinstance(lat,bool) or isinstance(lon,bool) or not isinstance(lat,(int,float))
                or not isinstance(lon,(int,float)) or not math.isfinite(lat) or not math.isfinite(lon)
                or not -90<=lat<=90 or not -180<=lon<=180 or lat==lon==0):
            if segment:segments.append(segment)
            segment=[];continue
        valid+=1;cells.add((round(lat*1000),round(lon*1000)));segment.append((lat,lon))
    if segment:segments.append(segment)
    if points and not valid:raise ValueError('Invalid GPS response')
    cells=sorted(cells)
    if len(cells)>2000:cells=[cells[round(i*(len(cells)-1)/1999)] for i in range(2000)]
    return dict(cells=cells,outline=project_route(segments))


def candidate(row):
    result={key:row.get(key) for key in ('id','title','date','started','category','distance','duration')}
    kind=row['category']
    result['needs_review']=(kind=='other' and row.get('is_run',True)
        or kind in ('short','medium','long') and not row.get('work_reps')
        or kind=='trial' and not row.get('best_5k'))
    return result


class RouteMatcher:
    """One catalog per scan; all SQLite work stays on the backend's owning thread."""
    def __init__(self,cache,rows,original,anchor):
        self.cache=cache;self.original=original;self.anchor=anchor['cells'];self.index={};self.scores={}
        self.rows=sorted((row for row in rows if row.get('activity_type') in ('running','trail_running','track_running')
            and row['id']!=original['id'] and (row.get('distance') or 0)>(original.get('distance') or 0)),
            key=lambda row:(row['distance'],row['started']),reverse=True)
        for row in [original]+self.rows:
            identity=row['id'];found,data=cache.detail(identity,'route_match_v1')
            if not found:
                found,recording=cache.detail(identity,'route_data_v1')
                if found:
                    data=dict(cells=recording.get('cells',[]),outline=cache.detail(identity,'route_outline_v1')[1])
                    cache.save_detail(identity,'route_match_v1',data)
            if found:self.index[identity]=data
        # The selected reference was validated against the original recording.
        self.index[original['id']]=dict(cells=self.anchor,outline=cache.detail(original['id'],'route_outline_v1')[1])
        self.pending=[row for row in self.rows if row['id'] not in self.index]

    def accept(self,identity,details):
        data=from_details(details)
        self.cache.save_detail(identity,'route_match_v1',data)
        if not self.cache.detail(identity,'route_outline_v1')[0]:
            self.cache.save_detail(identity,'route_outline_v1',data['outline'])
        self.index[identity]=data
        self.scores.pop(identity,None)

    def snapshot(self,error=None,paused=False,maximum=None):
        def item(row):
            value=candidate(row);data=self.index.get(row['id']) or {}
            if data.get('outline') is not None:value['outline']=thumbnail_route(data['outline'])
            return value
        matches=[];match_count=0
        for row in self.rows:
            data=self.index.get(row['id'])
            if data is None:continue
            if row['id'] not in self.scores:self.scores[row['id']]=gps_coverage(self.anchor,data.get('cells',[]))
            score=self.scores[row['id']]
            if score>=.85:
                match_count+=1
                if maximum is None or len(matches)<maximum:
                    value=item(row);value.update(overlap=score,longer=True);matches.append(value)
        checked=sum(row['id'] in self.index for row in self.rows)
        return dict(original=item(self.original),candidates=matches,match_count=match_count,checked=checked,total=len(self.rows),
                    remaining=len(self.rows)-checked,scan_error=error,paused=paused)
