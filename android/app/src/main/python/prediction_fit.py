"""Chronological 5K estimates anchored to measured trials, not future results.

Only recorded workouts enter the fit. Generated training targets never do.
HR slopes and reference effort are frozen at each trial, separately by workout
type. They describe comparable training, not a threshold or maximum-HR test.
"""
from datetime import date
import math
from statistics import median,mean


def positive(value):
    try:
        value=float(value)
        return value if math.isfinite(value) and value>0 else None
    except (ValueError,TypeError):return None


class TrialFit:
    def __init__(self,interval,normalized):
        self.interval,self.normalized=interval,normalized
        self.groups=('short','medium','long') if interval else ('easy',)
        self.history={key:[] for key in self.groups}
        self.window=3 if interval else 10
        self.minimum=1 if interval else 4
        self.anchor=None
        self.models={}
        self.calibrations=0

    def recent(self,key,day,days=21):
        return [r for r in self.history[key] if 0<=(day-r['day']).days<=days]

    def normalized_pace(self,row,model):
        if not self.normalized or model['hr'] is None:return row['pace']
        if row['hr'] is None or abs(row['hr']-model['hr'])>15:return None
        return row['pace']*math.exp(model['beta']*(row['hr']-model['hr']))

    def baseline(self,key,day):
        near=self.recent(key,day)[-self.window:]
        if len(near)<self.minimum:return None
        hrs=[r['hr'] for r in near if r['hr'] is not None]
        reference=median(hrs) if hrs else None
        usable=[r for r in self.recent(key,day,90) if r['hr'] is not None]
        slopes=[]
        for a,b in zip(usable,usable[1:]):
            delta=b['hr']-a['hr']
            if (b['day']-a['day']).days<=21 and abs(delta)>=3:
                slope=math.log(a['pace']/b['pace'])/delta
                if .001<=slope<=.03:slopes.append(slope)
        prior=.0075 if self.interval else .01
        weight=len(slopes)/(len(slopes)+8)
        beta=prior*(1-weight)+(median(slopes) if slopes else prior)*weight
        model=dict(hr=reference,beta=beta)
        values=[self.normalized_pace(r,model) for r in near]
        values=[v for v in values if v is not None]
        if len(values)<self.minimum:return None
        model['pace']=median(values)
        return model

    def point(self,row,duration,samples,hr_normalized):
        return dict(id=row['id'],date=row['date'],started=row['started'],duration=duration,
                    category='prediction' if self.interval else 'easy_prediction',
                    calibrations=self.calibrations,anchor_date=self.anchor['date'],
                    anchor_seconds=self.anchor_seconds,anchor_age_days=(date.fromisoformat(row['date'])-date.fromisoformat(self.anchor['date'])).days,
                    hr_normalized=hr_normalized,samples=samples)

    def trial(self,row,seconds):
        day=date.fromisoformat(row['date'])
        models={key:self.baseline(key,day) for key in self.groups}
        models={key:model for key,model in models.items() if model is not None}
        # Without nearby training, the interval estimate is the trial benchmark
        # itself. It cannot project a workout trend until a baseline is available.
        self.models=models;self.anchor=row;self.anchor_seconds=seconds
        if not models:
            if not self.interval:return None
            self.calibrations+=1
            return self.point(row,seconds,0,False)
        self.calibrations+=1
        return self.point(row,seconds,sum(len(self.recent(key,day)[-self.window:]) for key in models),
                          self.normalized and all(model['hr'] is not None for model in models.values()))

    def workout(self,row,pace,hr):
        day=date.fromisoformat(row['date']);key=row['category'] if self.interval else 'easy'
        hr=positive(hr);hr=hr if hr is not None and 60<=hr<=220 else None
        self.history[key].append(dict(day=day,pace=pace,hr=hr))
        self.history[key]=self.recent(key,day,90)
        if not self.models:return None
        ratios=[];samples=0;normalized=True
        for group,model in self.models.items():
            near=self.recent(group,day)[-self.window:]
            values=[self.normalized_pace(r,model) for r in near]
            values=[v for v in values if v is not None]
            if len(values)<self.minimum:continue
            ratios.append(math.log(median(values)/model['pace']));samples+=len(values)
            normalized=normalized and model['hr'] is not None
        if not ratios:return None
        seconds=self.anchor_seconds*math.exp(mean(ratios))
        return self.point(row,seconds,samples,self.normalized and normalized)


def prediction_series(rows,settings,calibration_rows=None):
    from dashboard_metrics import adjusted_pace,adjusted_trial
    context=rows if calibration_rows is None else calibration_rows
    context=sorted(context,key=lambda r:(r['started'],0 if r['category']=='trial' else 1,str(r['id'])))
    selected={r['id'] for r in rows}
    fits=[TrialFit(True,settings.get('prediction_mode','intensity')=='intensity'),
          TrialFit(False,settings.get('prediction_mode','intensity')=='intensity')]
    output=[[],[]]
    for row in context:
        points=[None,None]
        if row['category']=='trial' and row.get('best_5k'):
            seconds=positive(adjusted_trial(row,settings))
            if seconds is not None:
                points=[fit.trial(row,seconds) for fit in fits]
        elif row['category'] in fits[0].groups:
            pace=positive(adjusted_pace(row,row.get('work_pace'),settings,True))
            if pace is not None:points[0]=fits[0].workout(row,pace,row.get('work_hr'))
        elif row['category'] in ('easy','easy_long') and row.get('activity_type')=='running':
            pace=positive(adjusted_pace(row,row.get('pace'),settings))
            if pace is not None:points[1]=fits[1].workout(row,pace,row.get('average_hr'))
        if row['id'] in selected:
            for series,point in zip(output,points):
                if point is not None:series.append(point)
    return tuple(output)
