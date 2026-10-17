"""Allowlisted local dashboard comparison format. No credentials or GPS routes."""
import math

SCALAR = 'scalar'

def fields(names):
    return {name:SCALAR for name in names.split()}

EFFORT = fields('duration distance start_distance end_distance start_elapsed end_elapsed samples method')
LAP = fields('distance duration averageSpeed intensityType averageHR elevationGain elevationLoss')
FIT_INTERVAL = fields('distanceMeters durationSec count avgHr ascentMeters descentMeters source')
TERRAIN = fields('status reason source elevation_gain elevation_loss work_gain work_loss samples')
WEATHER = fields('temperatureF dewPointF humidity source station observation_time observation_offset')
ROW = fields('id date started category pace distance duration timer_duration activity_type is_run average_hr max_hr hr_target hr_below_target category_reason training_load elevation_gain elevation_loss elevation_source work_pace work_distance work_duration work_hr work_reps work_gain work_loss work_source hr_under_percent hr_total_seconds hr_source trial_pace display_pace range_lower range_upper value lap last_lap reps calibrations')
ROW.update(best_5k=EFFORT,weather=WEATHER,terrain=TERRAIN)
WEEK = fields('date total_minutes run_minutes run_miles training_load load_count interval_percent interval_minutes sessions sleep_hours sleep_score resting_hr hrv sleep_hours_days sleep_score_days resting_hr_days hrv_days')
SUMMARY = fields('sessions run_miles total_hours latest_prediction easy_percent last_four_miles interval_count cross_hours')
SUMMARY.update(best_trial=ROW,latest_trial=ROW)
TARGETS = fields('source error seconds vdot')
TARGETS.update(rows=[fields('category reps pace base_pace distance_basis delta')],
               races=[fields('label duration base_duration pace')])
ANDROID = fields('sync_paused terrain_downloads_paused start end history_start history_end cached_only cache_complete has_saved_data optional_downloads_paused missing_trials missing_intervals split_failures')
COUNT=fields('done total pending skipped enabled')
ANDROID['sync']={key:COUNT for key in ('terrain','recovery','hr_recordings','interval_recordings','trial_recordings','weather')}
ANDROID['sync']['summaries_complete']=SCALAR
ANDROID.update(runs=[ROW],weeks=[WEEK],summary=SUMMARY,targets=TARGETS,
               run_points=[ROW],interval_points=[ROW],trial_points=[ROW],
               prediction_points=[ROW],easy_prediction_points=[ROW],hr_points=[ROW])
SETTINGS = fields('easy_hr max_hr interval_mode classification_mode full_history include_recovery include_weather include_station_weather include_recordings include_terrain custom_start custom_end custom_range adjust_elevation adjust_temperature prediction_mode interval_pace_mode easy_mode target_source target_time target_temperature target_humidity target_gain target_loss race_distance_miles weekly_metric recovery_metric recent_filter')
SETTINGS.update(categories={'*':SCALAR},laps={'*':[SCALAR]})
ACTIVITY = fields('activityId activityName startTimeLocal startTimeGMT distance duration movingDuration elapsedDuration averageSpeed averageHR maxHR activityType activityTrainingLoad elevationGain elevationLoss averageTemperature fastestSplit_5000')
ACTIVITY.update(_station_match=fields('station stationName stationRoute stationDistanceMiles'),
                splitSummaries=[fields('distance duration noOfSplits splitType')])
OBSERVATION = fields('station valid temperature dewPoint humidity apparentTemperature metar')
STATION_DAY = fields('checked_at final')
STATION_DAY['rows'] = [OBSERVATION]
SCHEMA = dict(schema=SCALAR,selection=dict(today=SCALAR,days=SCALAR,settings=SETTINGS),
              activities=[ACTIVITY],coverage=[fields("start end")],android=ANDROID,
              details=dict(laps={'*':dict(lapDTOs=[LAP])},effort_v1={'*':EFFORT},
                           interval_fit_v1={'*':FIT_INTERVAL},hr_histogram_v1={'*':{'*':SCALAR}},
                           weather_v1={'*':fields('temperature apparentTemperature dewPoint humidity weatherDescription weatherStation temperatureF dewPointF source')},
                           terrain_v1={'*':TERRAIN}),
              daily={'sleep':{'*':fields('sleepHours sleepScore')},
                     'rhr':{'*':fields('restingHeartRate')},
                     'hrv':{'*':fields('hrvLastNightAvg')},
                     'station:KPVU':{'*':STATION_DAY},'station:KSLC':{'*':STATION_DAY}})


def _project(value, schema):
    if value is None:
        return None
    if schema==SCALAR:
        if not isinstance(value,(str,int,float,bool)):
            raise ValueError('Invalid comparison value')
        if isinstance(value,float) and not math.isfinite(value):
            raise ValueError('Non-finite comparison value')
        if isinstance(value,str) and len(value)>4096:
            raise ValueError('Comparison text is too long')
        return value
    if isinstance(schema,list):
        if not isinstance(value,list) or len(value)>10000:
            raise ValueError('Invalid comparison list')
        return [_project(item,schema[0]) for item in value]
    if not isinstance(value,dict) or len(value)>10000:
        raise ValueError('Invalid comparison object')
    return {key:_project(item,schema.get(key,schema.get('*'))) for key,item in value.items()
            if key in schema or '*' in schema}


def sanitize_snapshot(payload):
    clean = _project(payload,SCHEMA)
    if clean.get('schema')!=1 or not isinstance(clean.get('activities'),list) or not isinstance(clean.get('android'),dict):
        raise ValueError('Invalid comparison snapshot')
    selection=clean.get('selection',{})
    if not isinstance(selection.get('settings'),dict) or not isinstance(selection.get('today'),str):
        raise ValueError('Missing comparison selection')
    return clean


def validate_snapshot(payload):
    clean = sanitize_snapshot(payload)
    if clean!=payload:
        raise ValueError('Unexpected fields in comparison snapshot')
    return clean
