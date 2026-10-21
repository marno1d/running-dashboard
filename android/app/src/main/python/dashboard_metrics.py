"""Native dashboard calculations, following web_app/dashboard/app.js.

Distances are metres, pace is seconds/km, durations are seconds. Missing
measurements stay missing rather than becoming zero-valued observations.
"""
from datetime import date, timedelta
from statistics import median, mean
import math

from training import positive, INTERVALS, work_intervals, session_average
from web_sources import dashboard

EASY = ("easy", "easy_long")

MILE = 1609.344
FIVE_K_MILES = 3.106855
ELEVATION = {
    'rolling': ([5, 10, 15, 20], [[2,4,6,8],[4,7,10,13],[3,6,8,10],[5,9,12,16]]),
    'gain': ([5,10,15,20,25,30], [[4,9,14,20,25,31],[6,12,18,27,34,41],[7,15,23,34,42,51],[9,18,27,44,50,66]]),
    'loss': ([5,10,15,20,25,30], [[-3,-6,-9,-11,-15,-18],[-4,-8,-12,-16,-20,-24],[-5,-10,-15,-20,-25,-30],[-6,-12,-18,-24,-40,-42]]),
}


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def clamp(value, low, high):
    return max(low, min(high, value))


def mid(values, fallback=None):
    values = [v for v in values if v is not None and math.isfinite(v)]
    return median(values) if values else fallback


def interpolate(xs, ys, value):
    for index in range(1, len(xs)):
        if value <= xs[index]:
            break
    else:
        index = len(xs) - 1
    return ys[index-1] + (ys[index]-ys[index-1]) * (value-xs[index-1]) / (xs[index]-xs[index-1])


def elevation_delta(pace, distance, gain, loss):
    """Norwegian elevation tables, expressed in seconds/km and metres."""
    if not pace or not distance:
        return 0
    gain = abs(gain or 0) / (distance / 1000)
    loss = abs(loss or 0) / (distance / 1000)
    rolling = min(gain, loss)
    result = 0
    for key, grade in (('rolling', rolling), ('gain', gain-rolling), ('loss', loss-rolling)):
        if grade <= 0:
            continue
        marks, rows = ELEVATION[key]
        deltas = [interpolate([0]+marks, [0]+row, grade) for row in rows]
        result += interpolate([180,240,300,360], deltas, clamp(pace,180,360))
    return clamp(result, -120/1.609344, 180/1.609344)


def dew_point(temp, humidity):
    if temp is None or humidity is None:
        return None
    c = (temp-32)*5/9
    gamma = math.log(clamp(humidity,1,100)/100) + 17.625*c/(243.04+c)
    return (243.04*gamma/(17.625-gamma))*9/5+32


def weather_reduction(temp, dew):
    temp_c = (temp-32)*5/9 if temp is not None else -100
    dew_c = (dew-32)*5/9 if dew is not None else -100
    heat = .04 if temp_c >= 25 else .02 if temp_c >= 20 else .01 if temp_c >= 15 else 0
    damp = .04 if dew_c >= 18 else .02 if dew_c >= 15 else .01 if dew_c >= 12 else 0
    return max(heat, damp)


def adjusted_pace(row, pace, settings, interval=False):
    if not pace:
        return None
    distance = (row.get('work_distance') or row.get('distance')) if interval else row.get('distance')
    gain = row.get('work_gain') if interval else row.get('elevation_gain')
    loss = row.get('work_loss') if interval else row.get('elevation_loss')
    if interval and gain is None and loss is None:
        gain, loss = row.get('elevation_gain'), row.get('elevation_loss')
    delta = elevation_delta(pace, distance, gain, loss) if settings.get('adjust_elevation') else 0
    weather = row.get('weather') or {}
    temp = number(weather.get('temperatureF'))
    dew = number(weather.get('dewPointF'))
    if dew is None:
        dew = dew_point(temp, number(weather.get('humidity')))
    if settings.get('adjust_temperature'):
        delta += pace*weather_reduction(temp,dew)
    return max(1, pace-delta)


def fractional_vdot(minutes):
    return .2989558*math.exp(-.1932605*minutes)+.1894393*math.exp(-.012778*minutes)+.8


def vdot_from_5k(seconds):
    minutes = seconds/60
    speed = 5000/minutes
    return (.000104*speed**2+.182258*speed-4.6)/fractional_vdot(minutes)


def speed_from_vdot(minutes, vdot):
    demand = fractional_vdot(minutes)*vdot
    return 29.54+5.000663*demand-.007546*demand**2


def race_seconds(distance, vdot):
    low, high = .1, 600
    while speed_from_vdot(high,vdot)*high < distance and high < 2000:
        high *= 1.5
    for _ in range(80):
        middle = (low+high)/2
        if speed_from_vdot(middle,vdot)*middle < distance:
            low = middle
        else:
            high = middle
    return (low+high)/2*60


def parse_time(value):
    try:
        parts = str(value).strip().split(':')
        if len(parts) not in (2,3) or any(not p.isdigit() for p in parts):
            return None
        values = [int(p) for p in parts]
        if any(p >= 60 for p in values[1:]):
            return None
        seconds = sum(v*60**i for i,v in enumerate(reversed(values)))
        return seconds if 300 <= seconds <= 7200 else None
    except (TypeError, ValueError):
        return None


def intensity(row, health, max_hr, interval):
    hr = row.get('work_hr') if interval else row.get('average_hr')
    rest = positive(row.get('resting_hr')) or positive(health.get(row['date'],{}).get('resting_hr'))
    if rest is not None:
        rest=round(rest)
    if rest is None:
        week = date.fromisoformat(row['date'])
        week -= timedelta(days=week.weekday())
        same_week = [positive(v.get('resting_hr')) for d,v in health.items()
                     if week.isoformat() <= d <= (week+timedelta(days=6)).isoformat()]
        finite = [v for v in same_week if v is not None]
        groups = {}
        for day,value in health.items():
            resting = positive(value.get('resting_hr'))
            if resting:
                stamp = date.fromisoformat(day)
                week_key = (stamp-timedelta(days=stamp.weekday())).isoformat()
                groups.setdefault(week_key,[]).append(resting)
        rest = round(web_sum(finite)/len(finite)) if finite else mid([round(web_sum(values)/len(values)) for values in groups.values()])
    if not hr or not rest or max_hr <= rest:
        return None
    return clamp((hr-rest)/(max_hr-rest), .3 if interval else .2, 1.15 if interval else .9)


def normalized_paces(rows, health, settings, interval=False):
    max_hr = settings.get('max_hr',191)
    # Resolve fallbacks once per session, rather than scanning recovery history
    # again for every pair, category, and normalization step.
    intensities = {r['id']:intensity(r,health,max_hr,interval) for r in rows}
    def effort(row):
        return intensities[row['id']]
    groups = INTERVALS if interval else ('easy',)
    output = {}
    all_values = [effort(r) for r in rows]
    overall = mid(all_values, .86 if interval else .55)
    for group in groups:
        usable = [r for r in rows if (r['category']==group or (not interval and r['category'] in EASY)) and effort(r) is not None]
        target = mid([effort(r) for r in usable],overall)
        fallback = clamp(1/target, .8 if interval else 1.1, 1.35 if interval else 2.3)
        slopes = []
        for previous,row in zip(usable,usable[1:]):
            if (date.fromisoformat(row['date'])-date.fromisoformat(previous['date'])).days > (45 if interval else 21):
                continue
            delta = effort(row)-effort(previous)
            first = previous.get('work_pace') if interval else previous.get('pace')
            last = row.get('work_pace') if interval else row.get('pace')
            if abs(delta)<.015 or not first or not last:
                continue
            slope = math.log(adjusted_pace(previous,first,settings,interval)/adjusted_pace(row,last,settings,interval))/delta
            if 0 < slope < 3:
                slopes.append(slope)
        shrink = len(slopes)/(len(slopes)+(6 if interval else 8))
        beta = clamp(fallback*(1-shrink)+mid(slopes,fallback)*shrink,.65 if interval else .8,2 if interval else 2.4)
        for row in usable:
            pace = row.get('work_pace') if interval else row.get('pace')
            if pace:
                output[row['id']] = adjusted_pace(row,pace,settings,interval)/math.exp(beta*(target-effort(row)))
    return output


def raw_predictions(rows, settings, health):
    intervals = [r for r in rows if r['category'] in INTERVALS and r.get('work_pace')]
    easy = [r for r in rows if r['category'] in EASY and r.get('pace') and r.get('activity_type') == 'running']
    intensity_mode = settings.get('prediction_mode') == 'intensity'
    interval_paces = normalized_paces(intervals,health,settings,True) if intensity_mode else {}
    easy_paces = normalized_paces(easy,health,settings) if intensity_mode else {}
    recent = {k:[] for k in INTERVALS}
    raw, raw_easy = [], []
    previous = None
    for row in intervals:
        if previous and (date.fromisoformat(row['date'])-date.fromisoformat(previous['date'])).days > 30:
            recent = {k:[] for k in INTERVALS}
        previous = row
        pace = interval_paces.get(row['id']) if intensity_mode else adjusted_pace(row,row['work_pace'],settings,True)
        if pace is None:
            continue
        recent[row['category']] = (recent[row['category']]+[pace])[-3:]
        value = mean([mean(v) for v in recent.values() if v])*1.609344*FIVE_K_MILES
        raw.append(dict(id=row['id'],date=row['date'],started=row['started'],duration=value,category='prediction'))
    recent_easy = []
    previous = None
    for row in easy:
        if previous and (date.fromisoformat(row['date'])-date.fromisoformat(previous['date'])).days > 45:
            recent_easy = []
        previous = row
        pace = easy_paces.get(row['id']) if intensity_mode else adjusted_pace(row,row['pace'],settings)
        if pace is not None:
            recent_easy = (recent_easy+[pace])[-10:]
            if len(recent_easy) >= 4:
                raw_easy.append(dict(id=row['id'],date=row['date'],started=row['started'],duration=median(recent_easy)*1.609344*FIVE_K_MILES,category='easy_prediction'))
    return raw,raw_easy


def predictions(rows, settings, health, calibration_rows=None):
    calibration_rows = rows if calibration_rows is None else calibration_rows
    raw,raw_easy = raw_predictions(rows,settings,health)
    calibration_raw,calibration_easy = raw_predictions(calibration_rows,settings,health)
    def calibrate(series, calibration_series, minimum, lower, upper, chronological):
        ratios = []
        for trial in calibration_rows:
            if trial['category']!='trial' or not trial.get('best_5k'):
                continue
            prior = [p for p in calibration_series if 0 <= (date.fromisoformat(trial['date'])-date.fromisoformat(p['date'])).days <= 21
                     and (not chronological or p['started'] <= trial['started'])]
            if prior:
                ratios.append(adjusted_trial(trial,settings)/prior[-1]['duration'])
        ratio = clamp(median(ratios),lower,upper) if len(ratios)>=minimum else (1 if minimum==1 else None)
        return [dict(p,duration=p['duration']*ratio,calibrations=len(ratios)) for p in series] if ratio else []
    return calibrate(raw,calibration_raw,1,.75,1.05,False), calibrate(raw_easy,calibration_easy,2,.5,.9,True)


def web_sum(values,digits=None):
    # Match the web builder's chronological += aggregation (including ties),
    # after restoring independently rounded JSON units from native units.
    total=0.0
    for value in values:
        total+=round(value,digits) if digits is not None else value
    return total


def weekly(rows, health, start, end, web_mode=False):
    first = date.fromisoformat(start)
    cursor = first-timedelta(days=first.weekday())
    final = date.fromisoformat(end)
    result = []
    def total(values,digits):
        return web_sum(values,digits) if web_mode else sum(values)
    while cursor <= final:
        last = cursor+timedelta(days=6)
        sessions = [r for r in rows if cursor.isoformat() <= r['date'] <= last.isoformat()]
        recovery = [v for d,v in health.items() if max(start,cursor.isoformat()) <= d <= min(end,last.isoformat())]
        run_rows = [r for r in sessions if r.get('is_run',True)]
        minutes = total(((r.get('duration') or 0)/60 for r in sessions),1)
        work = total(((r.get('work_duration') or 0)/60 for r in sessions if r['category'] in INTERVALS),1)
        week = dict(date=cursor.isoformat(), total_minutes=minutes,
                    run_minutes=total(((r.get('duration') or 0)/60 for r in run_rows),1),
                    run_miles=total(((r.get('distance') or 0)/MILE for r in run_rows),2),
                    training_load=total(((r.get('training_load') or 0) for r in sessions),1),
                    load_count=sum(r.get('training_load') is not None for r in sessions),
                    interval_percent=work/minutes*100 if minutes else 0,
                    interval_minutes=work, sessions=len(sessions))
        for key in ('sleep_hours','sleep_score','resting_hr','hrv'):
            values = [number(r.get(key)) for r in recovery]
            values = [v for v in values if v is not None]
            week[key] = (web_sum(values)/len(values) if web_mode else mean(values)) if values else None
            week[key+'_days'] = len(values)
        result.append(week)
        cursor += timedelta(days=7)
    return result


def targets(rows, prediction, settings):
    source = settings.get('target_source','predicted')
    trials = [r for r in rows if r.get('best_5k')]
    if source=='custom':
        seconds = parse_time(settings.get('target_time',''))
    elif source=='latest':
        trial = trials[-1] if trials else None
        seconds = adjusted_trial(trial,settings) if trial else None
    else:
        seconds = prediction[-1]['duration'] if prediction else None
    if not seconds:
        return {'source':source,'error':'Enter a 5K time (mm:ss).' if source=='custom' else 'No 5K trial available.' if source=='latest' else 'No interval prediction available yet.'}
    vdot = vdot_from_5k(seconds)
    temp = number(settings.get('target_temperature',45))
    humidity = number(settings.get('target_humidity'))
    gain = number(settings.get('target_gain',0)) or 0
    loss = number(settings.get('target_loss',0)) or 0
    reduction = weather_reduction(temp,dew_point(temp,humidity))
    def adjusted(pace,distance):
        return max(1,pace+elevation_delta(pace,distance,gain*.3048,loss*.3048)+pace/(1-reduction)-pace)
    target_rows = []
    for key,minutes,reps in (('short',60,'3-min reps'),('medium',90,'5-min reps'),('long',150,'10-min reps')):
        pace = 1000/speed_from_vdot(minutes,vdot)*60
        previous = [r for r in rows if r['category']==key and (r.get('work_distance') or r.get('distance'))]
        distance = (previous[-1].get('work_distance') or previous[-1].get('distance')) if previous else None
        target_rows.append(dict(category=key,reps=reps,pace=adjusted(pace,distance),base_pace=pace,distance_basis=distance,delta=adjusted(pace,distance)-pace))
    races = []
    for label,distance in (('1 mile',MILE),('5K',5000),('10K',10000),('Half marathon',21097.5),('Marathon',42195)):
        duration = race_seconds(distance,vdot)
        races.append(dict(label=label,duration=adjusted(duration/distance*1000,distance)*distance/1000,base_duration=duration,pace=adjusted(duration/distance*1000,distance)))
    custom_distance = positive(settings.get('race_distance_miles'))
    if custom_distance and custom_distance <= 200:
        distance = custom_distance*MILE
        duration = race_seconds(distance,vdot)
        races.append(dict(label=str(custom_distance)+' miles',duration=adjusted(duration/distance*1000,distance)*distance/1000,base_duration=duration,pace=adjusted(duration/distance*1000,distance)))
    return dict(source=source,seconds=seconds,vdot=vdot,rows=target_rows,races=races)


def rolling_easy_range(points):
    values, previous_range, previous_day = [], None, None
    for point in points:
        if point.get('activity_type')=='trail_running':
            continue
        day = date.fromisoformat(point['date'])
        if previous_day and (day-previous_day).days>45:
            values,previous_range = [],None
        previous_day = day
        values = (values+[point['pace']])[-10:]
        if len(values)<4:
            continue
        ordered = sorted(values)
        def quantile(q):
            position = (len(ordered)-1)*q
            lower = int(position)
            return ordered[lower]+(ordered[min(lower+1,len(ordered)-1)]-ordered[lower])*(position-lower)
        lower,upper = quantile(.25),quantile(.75)
        if previous_range:
            lower = previous_range[0]*.65+lower*.35
            upper = previous_range[1]*.65+upper*.35
        point['range_lower'],point['range_upper'] = lower,upper
        previous_range = lower,upper


def web_precision(row):
    """Use the web builder's published precision before chart calculations.

    The cache keeps original measurements. In web classification mode these
    display rows follow the JSON records consumed by the browser, including
    independently rounded pace, mileage, time, feet, and heart-rate fields.
    """
    for key,scale,digits in (
        ('pace',1.609344,1),('work_pace',1.609344,1),
        ('distance',1/MILE,2),('work_distance',1/MILE,2),
        ('duration',1/60,1),('work_duration',1/60,1),
        ('average_hr',1,0),('work_hr',1,0),('max_hr',1,0),
        ('elevation_gain',1/.3048,0),('elevation_loss',1/.3048,0),
        ('work_gain',1/.3048,0),('work_loss',1/.3048,0),
        ('training_load',1,1),('hr_under_percent',1,1),('hr_total_seconds',1/60,1)):
        value=number(row.get(key))
        if value is not None:row[key]=round(value*scale,digits)/scale
    row['weather']=dict(row.get('weather') or {})
    for key in ('temperatureF','dewPointF','humidity'):
        value=number(row['weather'].get(key))
        if value is not None:row['weather'][key]=round(value,0)
    if row.get('best_5k'):
        row['best_5k']=dict(row['best_5k'])
        row['trial_pace']=round(row['best_5k']['duration']/FIVE_K_MILES,1)/1.609344
        row['best_5k']['duration']=round(row['best_5k']['duration'],1)


def adjusted_trial(row,settings):
    duration=row['best_5k']['duration']
    pace=row.get('trial_pace') or duration/5
    adjusted=adjusted_pace(row,pace,settings)
    return adjusted*1.609344*FIVE_K_MILES if adjusted!=pace else duration


def enrich(result, activities, splits, health, weather, settings, visible_range=None, fit_intervals=None):
    original = {str(a['activityId']):a for a in activities}
    all_rows = sorted(result['runs'],key=lambda r:r['started'])
    fit_intervals = fit_intervals or {}
    web_mode=settings.get('classification_mode')=='web'
    # Rebuild one work average per session, independent of legacy plot preferences.
    result['interval_points'] = []
    for row in all_rows:
        activity = original.get(row['id'],{})
        row['training_load'] = number(activity.get('activityTrainingLoad'))
        row['elevation_gain'] = number(activity.get('elevationGain'))
        row['elevation_loss'] = number(activity.get('elevationLoss'))
        row['elevation_source'] = 'Garmin'
        row['weather'] = weather.get(row['id'],{})
        if row['category'] in INTERVALS:
            selection = settings.get('laps',{}).get(row['id'])
            points = work_intervals(row,splits.get(row['id'],{}),set(selection) if selection is not None else None)
            avg = session_average(points)
            fit = fit_intervals.get(row['id']) or {}
            summary = dashboard.interval_pace_from_split_summaries(activity) or fit
            if avg:
                row['work_reps'] = len(points)
                row['work_pace'],row['work_distance'],row['work_duration'] = avg[0]['pace'],avg[0]['distance'],avg[0]['duration']
                weighted = [(p.get('average_hr'),p.get('duration')) for p in points if p.get('average_hr') and p.get('duration')]
                row['work_hr'] = sum(h*d for h,d in weighted)/sum(d for _,d in weighted) if weighted else None
                for source,key in (('elevation_gain','work_gain'),('elevation_loss','work_loss')):
                    values = [p.get(source) for p in points]
                    row[key] = sum(v for v in values if v is not None) if any(v is not None for v in values) else None
            if selection is None and summary and summary.get('distanceMeters') and summary.get('durationSec'):
                row['work_distance'],row['work_duration'] = summary['distanceMeters'],summary['durationSec']
                row['work_pace'] = row['work_duration']/row['work_distance']*1000
                row['work_reps'] = summary['count']
                row['work_source'] = summary['source']
            if selection is None and (fit or web_mode):
                row['work_hr'] = fit.get('avgHr')
                row['work_gain'],row['work_loss'] = fit.get('ascentMeters'),fit.get('descentMeters')
            if row.get('work_pace'):
                result['interval_points'].append(dict(row,pace=row['work_pace'],duration=row['work_duration'],distance=row['work_distance'],lap=0,reps=row.get('work_reps',0)))
        terrain = row.get('terrain')
        if terrain:
            row['elevation_gain'],row['elevation_loss'] = terrain['elevation_gain'],terrain['elevation_loss']
            row['elevation_source'] = terrain['source']
            if row['id'] not in settings.get('laps',{}):
                if terrain.get('work_gain') is not None:row['work_gain']=terrain['work_gain']
                if terrain.get('work_loss') is not None:row['work_loss']=terrain['work_loss']
        if web_mode:
            web_precision(row)
            if row['category'] in INTERVALS:
                for point in result['interval_points']:
                    if point['id']==row['id']:
                        point['pace']=row.get('work_pace')
                        point['distance']=row.get('work_distance')
                        point['duration']=row.get('work_duration')
    context_start,context_end = result['start'],result['end']
    if visible_range:
        result['start'],result['end'] = visible_range
    rows = [r for r in all_rows if result['start']<=r['date']<=result['end']]
    result['runs'] = sorted(rows,key=lambda r:r['started'],reverse=True)
    selected = {r['id'] for r in rows}
    result['interval_points'] = sorted((p for p in result['interval_points'] if p['id'] in selected),key=lambda p:(p['date'],p.get('lap',0)))
    result['trial_points'] = [p for p in result['trial_points'] if p['id'] in selected]
    all_weeks = weekly(all_rows,health,context_start,context_end,web_mode)
    if settings.get('full_history'):
        result['weeks'] = [w for w in all_weeks if w['date']<=result['end'] and (settings.get('all_range') or w['date']>=result['start'] or settings.get('custom_range') and (date.fromisoformat(w['date'])+timedelta(days=6)).isoformat()>=result['start'])]
    else:
        result['weeks'] = weekly(rows,health,result['start'],result['end'],web_mode)
    if web_mode:
        for week in result['weeks']:
            for field,digits in (('run_miles',1),('total_minutes',1),('run_minutes',1),('training_load',1),('interval_minutes',1),('sleep_hours',2),('sleep_score',0),('resting_hr',0),('hrv',0)):
                if week.get(field) is not None:week[field]=round(week[field],digits)
            week['interval_percent']=week['interval_minutes']/week['total_minutes']*100 if week['total_minutes'] else 0
    predicted,easy_predicted = predictions(rows,settings,health,all_rows)
    full_prediction,_ = predictions(all_rows,settings,health)
    result['prediction_points'],result['easy_prediction_points'] = predicted,easy_predicted
    result['targets'] = targets(all_rows,full_prediction,settings)
    easy = [r for r in rows if r['category'] in EASY and r.get('pace')]
    intervals = [r for r in rows if r['category'] in INTERVALS and r.get('work_pace')]
    easy_normal = normalized_paces(easy,health,settings) if settings.get('easy_mode')=='intensity' else {}
    interval_normal = normalized_paces(intervals,health,settings,True) if settings.get('interval_pace_mode')=='intensity' else {}
    by_id = {r['id']:r for r in rows}
    result['run_points'] = [dict(r,pace=easy_normal.get(r['id']) if settings.get('easy_mode')=='intensity' else adjusted_pace(r,r['pace'],settings)) for r in easy]
    result['run_points'] = [p for p in result['run_points'] if p['pace'] is not None]
    rolling_easy_range(result['run_points'])
    for point in result['interval_points']:
        row = by_id[point['id']]
        pace = adjusted_pace(row,point['pace'],settings,True)
        if settings.get('interval_pace_mode')=='intensity':
            normalized = interval_normal.get(point['id'])
            point['pace'] = pace*normalized/adjusted_pace(row,row['work_pace'],settings,True) if normalized else None
        else:
            point['pace'] = pace
    result['interval_points'] = [p for p in result['interval_points'] if p['pace'] is not None]
    result['trial_points'] = [dict(p,duration=adjusted_trial(by_id[p['id']],settings)) for p in result['trial_points']]
    result['hr_points'] = [dict(r,value=r['average_hr']) for r in easy if r.get('average_hr')]
    trials = [r for r in rows if r.get('best_5k')]
    easy_weight = sum(r.get('hr_total_seconds') or r.get('duration') or 0 for r in easy)
    last_four = result['weeks'][-4:]
    result['summary'] = dict(sessions=len(rows),run_miles=sum((r.get('distance') or 0)/MILE for r in rows if r.get('is_run',True)),
                            total_hours=sum((r.get('duration') or 0)/3600 for r in rows),
                            latest_prediction=predicted[-1]['duration'] if predicted else None,
                            easy_percent=sum((r.get('hr_under_percent') or 0)*(r.get('hr_total_seconds') or r.get('duration') or 0) for r in easy)/easy_weight if easy_weight else None,
                            last_four_miles=mean([w['run_miles'] for w in last_four]) if last_four else None,
                            best_trial=min(trials,key=lambda r:r['best_5k']['duration']) if trials else None,
                            latest_trial=trials[-1] if trials else None,
                            interval_count=len([r for r in rows if r['category'] in INTERVALS]),
                            cross_hours=sum((r.get('duration') or 0)/3600 for r in rows if r['category'] in ('cross_train','cross_interval')))
    for row in rows:
        # Cards compare the whole activity independently of work reps or a 5K segment.
        row['display_overall_pace'] = adjusted_pace(row,row.get('pace'),settings) if row.get('is_run',True) else row.get('pace')
        row['display_work_pace'] = adjusted_pace(row,row.get('work_pace'),settings,True) if row['category'] in INTERVALS else None
        raw = row.get('work_pace') if row['category'] in INTERVALS else row['best_5k']['duration']/5 if row.get('best_5k') else row.get('pace')
        row['display_pace'] = adjusted_pace(row,raw,settings,row['category'] in INTERVALS) if row['category'] in EASY+INTERVALS+('trial',) else raw
    result['history_start'],result['history_end'] = context_start,context_end
