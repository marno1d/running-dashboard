// Run the repository's real web calculations without a browser or network.
const fs=require('fs'),vm=require('vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const source=fs.readFileSync(input.source,'utf8').split('\nrenderMeta();')[0];
const results=[];
for(const entry of input.cases){
  const settings=entry.settings;
  const ids={customTargetTime:settings.target_time||'',targetTemperatureF:settings.target_temperature??45,
    targetHumidityPct:settings.target_humidity??'',targetElevationGainFeet:settings.target_gain??'',targetElevationLossFeet:settings.target_loss??''};
  const choices={predictionMode:settings.prediction_mode==='intensity'?'hrAdjusted':'pace',
    intervalPaceMode:settings.interval_pace_mode||'observed',easyPaceMode:settings.easy_mode||'observed',targetSource:settings.target_source||'predicted'};
  const document={querySelector(selector){
    if(selector.includes('data-adjust'))return {checked:selector.includes('elevation')?!!settings.adjust_elevation:!!settings.adjust_temperature};
    const name=selector.match(/name="([^"]+)"/);return name?{value:choices[name[1]]}:null;
  },getElementById(id){return id in ids?{value:String(ids[id])}:null;}};
  const context={window:{GARMIN_DASHBOARD_DATA:entry.data},document,selection:entry};
  vm.createContext(context);vm.runInContext(source,context,{timeout:30000});
  const result=vm.runInContext(`(()=>{
    const records=DATA.records.filter(r=>r.date>=selection.start&&r.date<=selection.end);
    const weeks=DATA.weeks.filter(w=>w.week<=selection.end&&(selection.days===0||w.week>=selection.start||(selection.days===-1&&new Date(w.week+'T00:00:00Z').getTime()+6*DAY_MS>=new Date(selection.start+'T00:00:00Z').getTime())));
    const intervalModel=buildIntensityModel(records),easyModel=buildEasyIntensityModel(records);
    const intervals=records.filter(r=>INTERVAL_CATEGORIES.has(r.category)&&r.intervalPaceSecPerMile).map(r=>({id:r.id,pace:getIntervalPaceMode()==='intensity'?intensityNormalizedPace(r,intervalModel):adjustedIntervalPace(r)})).filter(r=>Number.isFinite(r.pace));
    const easy=easyPaceRows(records,getEasyPaceMode()==='intensity').map(r=>({id:r.id,pace:getEasyPaceMode()==='intensity'?intensityNormalizedEasyPace(r,easyModel):adjustedPaceForRow(r,r.paceSecPerMile)})).filter(r=>Number.isFinite(r.pace));
    const basis=selectedTargetBasis();let target=null;
    if(basis.seconds){const value=intervalTargetsFrom5k(basis.seconds),mileage=latestIntervalMileageByTarget();target={seconds:basis.seconds,vdot:value.vdot,rows:value.rows.map(r=>({category:INTERVAL_TARGET_CATEGORIES[r.key],pace:adjustedTargetPace(r.paceSecPerMile,getTargetConditions(),mileage[r.key])}))};}
    const summary=summarize(records,weeks);
    return {summary:{run_miles:summary.runMiles,last_four_miles:summary.lastFourAvg,easy_percent:summary.easyPct,interval_count:summary.intervalCount,cross_hours:summary.crossHours,
      best_trial:summary.bestTrial?.fastest5kSec??null,latest_trial:summary.latestTrial?.fastest5kSec??null},
      records:records.map(r=>({id:r.id,category:r.category,pace:r.paceSecPerMile,work_pace:r.intervalPaceSecPerMile,work_hr:r.intervalAvgHr,hr_under_percent:r.easyHrUnderPct})),
      weeks:weeks.map(w=>({date:w.week,run_miles:w.runMiles,total_minutes:w.totalMinutes,run_minutes:w.runMinutes,training_load:w.trainingLoad,interval_percent:w.totalMinutes?w.intervalMinutes/w.totalMinutes*100:0,sleep_hours:w.sleepHoursAvg,resting_hr:w.restingHrAvg,hrv:w.hrvAvg})),
      interval_points:intervals,run_points:easy,trial_points:records.filter(r=>r.category==='5k_time_trial'&&r.fastest5kSec).map(r=>({id:r.id,duration:adjustedTrialTime(r)})),
      prediction_points:buildPredicted5kSeries(records,DATA.records,getPredictionMode()).map(r=>({date:r.date,duration:r.value})),
      easy_prediction_points:buildEasyPredicted5kSeries(records,DATA.records,getPredictionMode()).map(r=>({date:r.date,duration:r.value})),targets:target};
  })()`,context,{timeout:30000});
  results.push(result);
}
process.stdout.write(JSON.stringify(results));
