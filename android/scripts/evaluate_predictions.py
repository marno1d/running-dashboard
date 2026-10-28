"""Evaluate past 5K forecasts using a consented local snapshot, entirely offline."""
import argparse
from datetime import date
import json
from pathlib import Path
from statistics import mean,median
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from compare_dashboard import replay
from dashboard_metrics import predictions,adjusted_trial


def evaluate(rows,settings):
    """The causal series is evaluated strictly before, never on, each trial."""
    interval,easy=predictions(rows,settings,{})
    cases=[]
    for trial in sorted(rows,key=lambda row:row['started']):
        if trial['category']!='trial' or not trial.get('best_5k'):continue
        result=dict(date=trial['date'],actual_seconds=adjusted_trial(trial,settings))
        for label,series in (('interval',interval),('easy',easy)):
            prior=[p for p in series if p['started']<trial['started'] and
                   0<=(date.fromisoformat(trial['date'])-date.fromisoformat(p['date'])).days<=21]
            if prior:
                point=prior[-1]
                result[label]=dict(seconds=point['duration'],error_seconds=point['duration']-result['actual_seconds'],
                                   anchor_date=point['anchor_date'],hr_normalized=point['hr_normalized'])
        cases.append(result)
    summary={}
    for label in ('interval','easy'):
        errors=[r[label]['error_seconds'] for r in cases if label in r]
        summary[label]=dict(count=len(errors),mean_absolute_error_seconds=mean(map(abs,errors)) if errors else None,
                            median_absolute_error_seconds=median(map(abs,errors)) if errors else None)
    return dict(settings=settings,summary=summary,trials=cases)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot',type=Path)
    parser.add_argument('--out',type=Path,default=Path('.state/prediction-evaluation.json'))
    args=parser.parse_args();payload=json.loads(args.snapshot.read_text());session=replay(payload)
    try:
        selection=payload.get('selection',{})
        settings=dict(payload.get('settings',selection.get('settings',{})))
        settings.pop('target_route_id',None)
        today=payload.get('today',selection.get('today'))
        data=session.cached_dashboard(today,0,json.dumps(dict(settings,full_history=True)))
        rows=sorted(data['runs'],key=lambda row:row['started'])
        results=[evaluate(rows,dict(adjust_elevation=adjusted,adjust_temperature=adjusted,prediction_mode=mode))
                 for adjusted in (False,True) for mode in ('observed','intensity')]
    finally:session.cache.close()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(results,indent=2)+'\n');args.out.chmod(0o600)
    print('Saved chronological forecast evaluation:',args.out)
    for result in results:print(json.dumps(dict(settings=result['settings'],summary=result['summary'])))


if __name__=='__main__':main()
