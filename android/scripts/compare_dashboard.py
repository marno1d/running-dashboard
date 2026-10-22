"""Compare saved Android inputs with the real web builder and JavaScript offline."""
from __future__ import annotations
import argparse
from datetime import date
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/app/src/main/python')]
from comparison_contract import validate_snapshot
from garmin_backend import Session
from web_sources import dashboard
from dashboard_sources import station_weather
from dashboard_metrics import target_basis_settings

CATEGORY={'short':'short_interval','medium':'medium_interval','long':'long_interval','trial':'5k_time_trial'}


def replay(snapshot):
    """Reconstruct only allowlisted cache inputs; no credentials or client needed."""
    session=Session()
    activities=snapshot['activities']
    if activities:
        days=[str(a['startTimeLocal'])[:10] for a in activities]
        session.cache.save_window(min(days),max(days),activities)
    with session.cache.db:
        session.cache.db.execute('DELETE FROM coverage')
        for window in snapshot.get('coverage',[]):
            session.cache.db.execute('INSERT INTO coverage VALUES(?,?)',(window['start'],window['end']))
    for kind,entries in snapshot.get('details',{}).items():
        for identity,body in entries.items():session.cache.save_detail(identity,kind,body)
    for kind,entries in snapshot.get('daily',{}).items():
        for day,body in entries.items():session.cache.save_day(day,kind,body)
    session.splits=session.cache.all_details('laps')
    session.efforts=session.cache.all_details('effort_v1')
    return session


def web_data(snapshot,settings):
    cache=replay(snapshot)
    try:
        activities=snapshot['activities']
        raw_health={}
        for kind in ('sleep','rhr','hrv'):
            for day,part in snapshot.get('daily',{}).get(kind,{}).items():raw_health.setdefault(day,{}).update(part)
        weather={}
        for identity,entry in snapshot['details'].get('weather_v1',{}).items():
            weather[identity]=dict(entry)
            if 'temperatureF' in entry:weather[identity].update(temperature=entry['temperatureF'],dewPoint=entry.get('dewPointF'))
        stations={}
        if settings.get('include_station_weather'):
            stations,_=station_weather(cache.cache,activities,lambda *a:None,allow_fetch=False)
        elevations={}
        if settings.get('include_terrain'):
            for identity,entry in snapshot['details'].get('terrain_v1',{}).items():
                if entry and entry.get('status')=='ok':
                    elevations[identity]=dict(status='ok',source='opentopodata',dataset='ned10m,srtm30m',elevationGainMeters=entry.get('elevation_gain'),elevationLossMeters=entry.get('elevation_loss'),intervalElevationGainMeters=entry.get('work_gain'),intervalElevationLossMeters=entry.get('work_loss'))
        provided={str(a['activityId']):{} for a in activities}
        for identity,effort in snapshot['details'].get('effort_v1',{}).items():
            if identity in provided and effort:
                provided[identity]['best_rolling_5000m_v1']=dict(durationSec=effort['duration'],source='fit_rolling_5000m',startOffsetSec=effort.get('start_elapsed'),endOffsetSec=effort.get('end_elapsed'))
        for identity,value in snapshot['details'].get('interval_fit_v1',{}).items():
            if identity in provided:provided[identity]['interval_active_laps_v2']=value
        threshold=float(settings.get('easy_hr',134))
        for identity,histogram in snapshot['details'].get('hr_histogram_v1',{}).items():
            total=sum(histogram.values()) if histogram else 0
            if identity in provided and total:
                under=sum(seconds for hr,seconds in histogram.items() if float(hr)<threshold)
                provided[identity][f'easy_hr_under_{threshold:.1f}']=dict(totalSec=total,underSec=under,overSec=total-under,underPct=under/total*100,fitAvgHr=sum(float(hr)*seconds for hr,seconds in histogram.items())/total)
        records=dashboard.build_records(activities,{},weather,stations,elevations,raw_health,fit_metrics=provided,easy_hr_threshold=threshold)
        weeks=dashboard.build_weeks(records,raw_health)
        return dict(meta=dict(maxHr=settings.get('max_hr',191),easyHrDisplayThreshold=threshold,startDate=dashboard.START_DATE.isoformat()),labels=dashboard.CATEGORY_LABELS,records=records,weeks=weeks)
    finally:
        cache.cache.close()


def differences(native,web,case):
    results=[]
    def check(metric,left,right,tolerance=1e-6):
        if left is None and right is None:return
        if isinstance(left,(int,float)) and isinstance(right,(int,float)):
            delta=left-right
            if abs(delta)<=1e-6:return
            status='rounding' if abs(delta)<=tolerance else 'different'
        else:
            if left==right:return
            delta=None;status='different'
        results.append(dict(case=case,metric=metric,android=left,web=right,delta=delta,status=status))
    summary=native['summary']
    for key,right in web['summary'].items():
        left=summary.get(key)
        if key in ('best_trial','latest_trial'):left=left.get('best_5k',{}).get('duration') if left else None
        check('summary.'+key,left,right, .1 if key.endswith('miles') else .1 if key=='easy_percent' else .01)
    native_rows={r['id']:r for r in native['runs']}
    for row in web['records']:
        original=native_rows.get(row['id'])
        if original is None:check('record.'+row['id'],None,'present');continue
        for key in ('category','pace','work_pace','work_hr','hr_under_percent'):
            left=original.get(key)
            if key=='category':left=CATEGORY.get(left,left)
            if key in ('pace','work_pace') and left is not None:left*=1.609344
            check('record.'+row['id']+'.'+key,left,row.get(key),.1 if key!='work_hr' else .5)
    check('record count',len(native_rows),len(web['records']))
    for key in ('weeks','run_points','trial_points','prediction_points','easy_prediction_points','interval_points'):
        fields={'weeks':('run_miles','total_minutes','run_minutes','training_load','interval_percent','sleep_hours','resting_hr','hrv'),
                'run_points':('pace',),'interval_points':('pace',),'trial_points':('duration',),
                'prediction_points':('duration',),'easy_prediction_points':('duration',)}[key]
        identity='date' if key in ('weeks','prediction_points','easy_prediction_points') else 'id'
        repeated=key in ('prediction_points','easy_prediction_points')
        def indexed(entries):
            counts={}
            for entry in entries:
                stamp=str(entry[identity]);index=counts.get(stamp,0);counts[stamp]=index+1
                yield (stamp+'#'+str(index) if repeated else stamp),entry
        lookup=dict(indexed(native.get(key,[])))
        if key=='interval_points' and native.get('interval_points') and any(r.get('lap',0)>0 for r in native[key]):
            # Web charts have one session average; per-rep native plots are an explicit preference.
            continue
        for stamp,row in indexed(web[key]):
            original=lookup.get(stamp,{})
            for field in fields:
                left=original.get(field);right=row.get(field)
                if field=='pace' and left is not None:left*=1.609344
                tolerance=.5 if field=='duration' else .1
                if key=='weeks':
                    sessions=original.get('sessions',0)
                    if field in ('total_minutes','run_minutes'):tolerance=sessions*.05+.05
                    elif field=='run_miles':tolerance=sessions*.005+.05
                    elif field=='training_load':tolerance=sessions*.05+.05
                    elif field=='resting_hr':tolerance=.5
                    elif field=='hrv':tolerance=.5
                check(key+'.'+stamp+'.'+field,left,right,tolerance)
        check(key+' count',len(lookup),len(dict(indexed(web[key]))))
    native_targets=native.get('targets',{})
    web_targets=web.get('targets')
    if web_targets:
        check('targets.seconds',native_targets.get('seconds'),web_targets['seconds'],.5)
        check('targets.vdot',native_targets.get('vdot'),web_targets['vdot'],.05)
        if native_targets.get('route_engine')!=2:
            for a,b in zip(native_targets.get('rows',[]),web_targets['rows']):check('targets.'+a['category']+'.pace',a['pace']*1.609344,b['pace'],.5)
    return results


def compare(snapshot,matrix=False,replay_current=False):
    validate_snapshot(snapshot)
    selection=snapshot['selection'];base=selection['settings']
    session=replay(snapshot)
    cases=[('current',base,session.cached_dashboard(selection['today'],selection['days'],json.dumps(base)) if replay_current else snapshot['android'])]
    if matrix:
        for intensity in (False,True):
            for elevation,temperature in ((False,False),(True,False),(False,True),(True,True)):
                mode='intensity' if intensity else 'observed'
                settings=dict(base,prediction_mode=mode,easy_mode=mode,interval_pace_mode=mode,interval_mode='session',adjust_elevation=elevation,adjust_temperature=temperature)
                native=session.cached_dashboard(selection['today'],selection['days'],json.dumps(settings))
                cases.append((f'{mode}/elev={elevation}/temp={temperature}',settings,native))
    try:
        # Adjustment modes share saved downloads and record precision.
        shared=web_data(snapshot,base)
        prepared=[dict(settings=s,target_settings=target_basis_settings(s),days=selection['days'],data=shared,start=n['start'],end=n['end']) for _,s,n in cases]
        proc=subprocess.run(['node',str(ROOT/'android/scripts/compare_web.js')],input=json.dumps(dict(source=str(ROOT/'web_app/dashboard/app.js'),cases=prepared)),text=True,capture_output=True,check=True)
        web_results=json.loads(proc.stdout)
        changes=[d for (name,_,n),w in zip(cases,web_results) for d in differences(n,w,name)]
        return dict(activities=len(snapshot['activities']),cases=len(cases),differences=changes,
                    counts={key:sum(d['status']==key for d in changes) for key in ('rounding','different')},
                    coverage=dict(cache_complete=snapshot['android'].get('cache_complete',False),records=len(snapshot['android']['runs']),health_days=len(snapshot.get('daily',{}).get('rhr',{})),fit_trials=sum(bool(v) for v in snapshot.get('details',{}).get('effort_v1',{}).values())),
                    notes=['Both sides use the same saved downloads and explicit date bounds. This does not repeat live HTTP requests or independently reparse discarded original FIT files.',
                           'Manual category/lap overrides and native per-rep mode can intentionally differ from the web app.',
                           'Small numeric deltas are listed separately; they are not silently discarded.',
                           'Route-profile target paces are a native-only model and excluded from web pace parity. The 5K basis is still compared; private elevation profiles are never exported.'])
    finally:session.cache.close()


def markdown(report):
    lines=['# Dashboard comparison','',f"Activities: {report['activities']} · Cases: {report['cases']}",'',
           f"Differences: {report['counts']['different']} · small rounding deltas: {report['counts']['rounding']}",'',
           '## Coverage','',json.dumps(report['coverage'],sort_keys=True),'',*report['notes'],'',
           '| Case | Metric | Android | Web | Delta | Classification |','|---|---|---:|---:|---:|---|']
    for d in report['differences']:
        values=[d.get(k) for k in ('case','metric','android','web','delta','status')]
        lines.append('| '+' | '.join(str(v).replace('|','/') for v in values)+' |')
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot',type=Path)
    parser.add_argument('--matrix',action='store_true')
    parser.add_argument('--replay-current',action='store_true',help='Compare current source calculations, preserving the original snapshot')
    parser.add_argument('--out',type=Path,default=ROOT/'android/.state/comparison-report.md')
    args=parser.parse_args()
    report=compare(json.loads(args.snapshot.read_text()),args.matrix,args.replay_current)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(markdown(report));args.out.chmod(0o600)
    print(json.dumps({key:value for key,value in report.items() if key not in ('differences','notes')},sort_keys=True))
    print('Report:',args.out)

if __name__=='__main__':main()
