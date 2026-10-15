"""Training chart calculations. Garmin distances are metres and times seconds."""
from datetime import date, timedelta
from calendar import monthrange
import math
import re

CATEGORIES = ('easy', 'short', 'medium', 'long', 'trial', 'other', 'cross_train', 'cross_interval', 'strength', 'warmup', 'easy_long', 'rebuild_run', 'other_run')
INTERVALS = ('short', 'medium', 'long')
CROSS_TRAIN_TYPES = {'cycling','indoor_cycling','virtual_ride','elliptical','lap_swimming','mountain_biking'}


def positive(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (ValueError, TypeError):
        return None


def nonnegative(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (ValueError,TypeError):
        return None


def pace_seconds(record):
    distance, duration = positive(record.get('distance')), positive(record.get('duration'))
    if distance and duration:
        return duration / distance * 1000
    speed = positive(record.get('averageSpeed'))
    return 1000 / speed if speed else None


def category(title):
    title = re.sub(r'[^a-z0-9]+', ' ', str(title).lower()).strip()
    if re.search(r'\b5\s*k\b', title) and re.search(r'\b(time trial|tt|test|race)\b', title):
        return 'trial'
    if re.search(r'\b(easy|recovery)\b', title) and not re.search(r'\b(intervals?|reps?)\b', title):
        return 'easy'
    if re.search(r'\b(intervals?|reps?|repeats?|nsm)\b', title):
        for key in INTERVALS:
            if re.search(r'\b' + key + r'\b', title):
                return key
    return 'other'


def history_start(end, days):
    """18/24-month choices use calendar months, including leap years."""
    if days == 0:
        return min(end, date(2025, 6, 1))
    if days in (548, 730):
        months = 18 if days == 548 else 24
        month_index = end.year * 12 + end.month - 1 - months
        year, zero_month = divmod(month_index, 12)
        month = zero_month + 1
        return date(year, month, min(end.day, monthrange(year, month)[1])) + timedelta(days=1)
    return end - timedelta(days=days - 1)


def normalized_runs(activities, today, days, overrides, easy_hr=134, start_date=None, classification='native'):
    end = date.fromisoformat(today)
    start = date.fromisoformat(start_date) if start_date else history_start(end, days)
    rows, seen = [], set()
    for activity in activities:
        stamp = activity.get('startTimeLocal') or ''
        try:
            day = date.fromisoformat(stamp[:10])
        except (TypeError, ValueError):
            continue
        identity = str(activity.get('activityId', ''))
        if not identity or identity in seen or not start <= day <= end:
            continue
        seen.add(identity)
        title = activity.get('activityName') or 'Untitled run'
        activity_type = activity.get('activityType') or {'typeKey':'running'}
        if isinstance(activity_type,dict):
            activity_type = activity_type.get('typeKey','running')
        is_run = activity_type in ('running','trail_running','treadmill_running','virtual_run','virtual_running','track_running')
        automatic = category(title) if is_run else ('strength' if activity_type=='strength_training' else ('cross_interval' if 'interval' in title.lower() else 'cross_train') if activity_type in CROSS_TRAIN_TYPES else 'other')
        if is_run and re.search(r'\b(warm[ -]?up|cool[ -]?down)\b',title.lower()):
            automatic = 'warmup'
        average_hr = positive(activity.get('averageHR'))
        max_hr = positive(activity.get('maxHR'))
        # Known hard workouts take priority: recovery can lower their average HR.
        hard_title = re.search(r'\b(intervals?|reps?|repeats?|sprints?|tempo|race|trial|tt)\b', str(title).lower())
        reason = 'title' if automatic != 'other' else 'unclassified'
        if is_run and automatic == 'other' and not hard_title and average_hr and average_hr < easy_hr:
            automatic, reason = 'easy', 'average_hr'
        duration = positive(activity.get('duration'))
        if classification=='web':
            from web_sources import dashboard
            source = dict(activity,activityType={'typeKey':activity_type})
            web_kind = dashboard.classify(source,day,easy_hr)
            automatic = {'short_interval':'short','medium_interval':'medium','long_interval':'long','5k_time_trial':'trial'}.get(web_kind,web_kind)
            duration = positive(activity.get('movingDuration')) or duration
            if automatic=='easy' and duration and duration>63*60:
                automatic = 'easy_long'
            reason = 'web classification'
        kind = overrides.get(identity, automatic)
        if kind not in CATEGORIES:
            kind = automatic
        elif identity in overrides:
            reason = 'manual'
        rows.append({'id': identity, 'title': title, 'started': stamp, 'date': day.isoformat(),
                     'category': kind, 'pace': duration/positive(activity.get('distance'))*1000 if classification=='web' and duration and positive(activity.get('distance')) else pace_seconds(activity), 'activity_type': activity_type, 'is_run': is_run,
                     'distance': positive(activity.get('distance')), 'duration': duration, 'timer_duration':positive(activity.get('duration')),
                     'average_hr': average_hr, 'max_hr': max_hr, 'hr_target': easy_hr,
                     'hr_below_target': average_hr < easy_hr if average_hr else None, 'category_reason': reason})
    return {'start': start.isoformat(), 'end': end.isoformat(),
            'runs': sorted(rows, key=lambda row: row['started'], reverse=True)}


def laps_list(payload):
    if isinstance(payload, list):
        return [lap for lap in payload if isinstance(lap, dict)]
    if isinstance(payload, dict):
        for key in ('lapDTOs', 'splits'):
            if isinstance(payload.get(key), list):
                return [lap for lap in payload[key] if isinstance(lap, dict)]
    return []


def intensity(lap):
    value = lap.get('intensityType', '')
    if isinstance(value, dict):
        value = value.get('typeKey', value.get('key', ''))
    return str(value).strip().upper()


def work_intervals(run, payload, selected=None):
    """Only explicit work laps or user-selected laps; never infer fast=work."""
    points = []
    previous_work_index = -2
    for index, lap in enumerate(laps_list(payload)):
        active = intensity(lap) in ('ACTIVE', 'INTERVAL', 'WORK', 'WORK_INTERVAL')
        if (selected is not None and index not in selected) or (selected is None and not active):
            continue
        pace = pace_seconds(lap)
        if pace is None:
            continue
        point = {'id': run['id'], 'title': run['title'], 'date': run['date'],
                 'category': run['category'], 'pace': pace, 'lap': index + 1,
                 'distance': positive(lap.get('distance')), 'duration': positive(lap.get('duration')),
                 'average_hr':positive(lap.get('averageHR')), 'elevation_gain':nonnegative(lap.get('elevationGain')), 'elevation_loss':nonnegative(lap.get('elevationLoss'))}
        # Garmin's auto-lap can split a single work repeat at each mile.
        # A recovery/warm-up boundary ends the repeat. Generic INTERVAL
        # labels can also mean ordinary distance laps, so don't merge those.
        if (selected is None and intensity(lap) in ('ACTIVE', 'WORK', 'WORK_INTERVAL')
                and previous_work_index == index - 1 and points
                and points[-1].get('distance') and points[-1].get('duration')
                and point['distance'] and point['duration']):
            old_duration = points[-1]['duration']
            if points[-1].get('average_hr') and point.get('average_hr'):
                points[-1]['average_hr'] = (points[-1]['average_hr']*old_duration+point['average_hr']*point['duration'])/(old_duration+point['duration'])
            else:
                points[-1]['average_hr'] = None
            for field in ('elevation_gain','elevation_loss'):
                a,b = points[-1].get(field), point.get(field)
                points[-1][field] = a+b if a is not None and b is not None else None
            points[-1]['distance'] += point['distance']
            points[-1]['duration'] += point['duration']
            points[-1]['pace'] = points[-1]['duration'] / points[-1]['distance'] * 1000
            points[-1]['last_lap'] = index + 1
        else:
            points.append(point)
        previous_work_index = index if intensity(lap) in ('ACTIVE', 'WORK', 'WORK_INTERVAL') else -2
    return points


def session_average(points):
    """A weighted pace from total work time / total work distance."""
    usable = [p for p in points if p.get('distance') and p.get('duration')]
    if not usable:
        return []
    result = dict(usable[0])
    result['distance'] = sum(p['distance'] for p in usable)
    result['duration'] = sum(p['duration'] for p in usable)
    result['pace'] = result['duration'] / result['distance'] * 1000
    result['lap'] = 0
    result['reps'] = len(usable)
    return [result]


def lap_choices(payload):
    return [{'index': i, 'lap': i + 1, 'pace': pace_seconds(lap),
             'distance': positive(lap.get('distance')), 'duration': positive(lap.get('duration')),
             'intensity': intensity(lap)} for i, lap in enumerate(laps_list(payload))]
