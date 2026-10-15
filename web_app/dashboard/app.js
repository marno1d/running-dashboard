const DATA = window.GARMIN_DASHBOARD_DATA;

const COLORS = {
  run: "#287c71",
  easy: "#4c9a4b",
  cross: "#c9822a",
  hard: "#b34e4e",
  blue: "#3f6fa8",
  violet: "#725ca8",
  muted: "#66736d",
  line: "#dfe4dc",
  text: "#1f2723",
  panel: "#ffffff"
};

const INTERVAL_COLORS = {
  short_interval: COLORS.violet,
  medium_interval: COLORS.blue,
  long_interval: COLORS.run
};

const INTERVAL_TARGET_CATEGORIES = {
  short: "short_interval",
  medium: "medium_interval",
  long: "long_interval"
};

const INTERVAL_LINE_GAP_DAYS = 30;
const FIVE_K_MILES = 3.106855;
const FIVE_K_METERS = 5000;
const METERS_PER_MILE = 1609.344;
const KM_PER_MILE = METERS_PER_MILE / 1000;
const DAY_MS = 24 * 60 * 60 * 1000;
const RECENT_PAGE_SIZE = 10;
const REFRESH_POLL_MS = 1000;
const PACE_ADJUSTMENT_KEYS = ["elevation", "temperature"];
const NSM_WEATHER_MAX_REDUCTION = 0.04;
const DEFAULT_INTENSITY_TARGET = 0.86;
const EASY_PACE_MIN_SEC = 7 * 60;
const EASY_PACE_MAX_SEC = 10 * 60;
const EASY_PACE_TICKS = [EASY_PACE_MIN_SEC, 8 * 60, 9 * 60, EASY_PACE_MAX_SEC];
const EASY_PACE_MARKER_RADIUS = 4.5;
const EASY_PACE_RANGE_WINDOW = 10;
const EASY_PACE_RANGE_MIN_POINTS = 4;
const EASY_PACE_RANGE_GAP_DAYS = 45;
const EASY_PACE_RANGE_SMOOTHING = 0.35;
const PREDICTION_CALIBRATION_LOOKBACK_DAYS = 21;
const EASY_5K_MIN_CALIBRATIONS = 2;
const EASY_5K_CALIBRATION_MIN = 0.5;
const EASY_5K_CALIBRATION_MAX = 0.9;
const EASY_CATEGORIES = new Set(["easy", "easy_long"]);
const INTERVAL_CATEGORIES = new Set(["short_interval", "medium_interval", "long_interval"]);
let recentPage = 0;
let customRaceDistanceMiles = "";
let chartTooltip = null;
const trialSeriesVisibility = {
  actual: true,
  interval: true,
  easy: true
};
const NORWEGIAN_ELEVATION_PACES_SEC_PER_KM = [180, 240, 300, 360];
const NORWEGIAN_ELEVATION_TABLES = {
  rolling: {
    metersPerKm: [5, 10, 15, 20],
    deltaSecPerKm: [
      [2, 4, 6, 8],
      [4, 7, 10, 13],
      [3, 6, 8, 10],
      [5, 9, 12, 16]
    ]
  },
  gain: {
    metersPerKm: [5, 10, 15, 20, 25, 30],
    deltaSecPerKm: [
      [4, 9, 14, 20, 25, 31],
      [6, 12, 18, 27, 34, 41],
      [7, 15, 23, 34, 42, 51],
      [9, 18, 27, 44, 50, 66]
    ]
  },
  loss: {
    metersPerKm: [5, 10, 15, 20, 25, 30],
    deltaSecPerKm: [
      [-3, -6, -9, -11, -15, -18],
      [-4, -8, -12, -16, -20, -24],
      [-5, -10, -15, -20, -25, -30],
      [-6, -12, -18, -24, -40, -42]
    ]
  }
};
const INTERVAL_TARGETS = [
  {
    key: "short",
    label: "Short intervals",
    reps: "3-min reps",
    durationMin: 60
  },
  {
    key: "medium",
    label: "Medium intervals",
    reps: "5-min reps",
    durationMin: 90
  },
  {
    key: "long",
    label: "Long intervals",
    reps: "10-min reps",
    durationMin: 150
  }
];
const RACE_PREDICTIONS = [
  { label: "1 mile", distanceMeters: METERS_PER_MILE },
  { label: "5K", distanceMeters: FIVE_K_METERS },
  { label: "10K", distanceMeters: 10000 },
  { label: "Half marathon", distanceMeters: 21097.5 },
  { label: "Marathon", distanceMeters: 42195 }
];
const WEEKLY_METRICS = {
  trainingLoad: {
    label: "TRIMP load",
    color: COLORS.hard,
    value: (week) => week.trainingLoad ?? 0,
    format: (value) => formatNumber(value, 0),
    tooltip: (value) => `${formatNumber(value, 0)} load`
  },
  totalMinutes: {
    label: "total training time",
    color: COLORS.blue,
    value: (week) => (week.totalMinutes ?? ((week.runMinutes ?? 0) + (week.crossTrainHours ?? 0) * 60)) / 60,
    format: (value) => `${formatNumber(value, 1)}h`,
    tooltip: (value) => `${formatNumber(value, 1)} h total`
  },
  runMinutes: {
    label: "running time",
    color: COLORS.run,
    value: (week) => (week.runMinutes ?? 0) / 60,
    format: (value) => `${formatNumber(value, 1)}h`,
    tooltip: (value) => `${formatNumber(value, 1)} h running`
  },
  intervalPercent: {
    label: "active interval percent",
    color: COLORS.violet,
    value: (week) => week.totalMinutes
      ? (week.intervalMinutes ?? 0) / week.totalMinutes * 100
      : 0,
    format: (value) => `${formatNumber(value, 0)}%`,
    tooltip: (value, week) => {
      const intervalHours = (week.intervalMinutes ?? 0) / 60;
      return `${formatNumber(value, 1)}% active intervals, ${formatNumber(intervalHours, 1)} h`;
    }
  },
  runMiles: {
    label: "running miles",
    color: COLORS.run,
    value: (week) => week.runMiles ?? 0,
    format: (value) => formatNumber(value, 0),
    tooltip: (value) => `${formatNumber(value, 1)} run mi`
  }
};

function parseDate(value) {
  return new Date(`${value}T00:00:00`);
}

function formatDate(value, opts = {}) {
  return new Intl.DateTimeFormat("en-US", {
    month: opts.month || "short",
    day: opts.day || "numeric",
    year: opts.year || undefined
  }).format(parseDate(value));
}

function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits
  }).format(value);
}

function formatDuration(seconds) {
  if (!seconds) return "-";
  const rounded = Math.round(seconds);
  const mins = Math.floor(rounded / 60);
  const secs = rounded % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

function formatRaceTime(seconds) {
  if (!seconds) return "-";
  const rounded = Math.round(seconds);
  const hours = Math.floor(rounded / 3600);
  const mins = Math.floor((rounded % 3600) / 60);
  const secs = rounded % 60;
  if (!hours) {
    return `${mins}:${String(secs).padStart(2, "0")}`;
  }
  return `${hours}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function formatPace(seconds) {
  if (!seconds) return "-";
  return `${formatDuration(seconds)}/mi`;
}

function formatSignedSecondsPerMile(value) {
  if (!Number.isFinite(value) || Math.abs(value) < 0.5) return "0s/mi";
  const sign = value > 0 ? "+" : "-";
  return `${sign}${Math.abs(Math.round(value))}s/mi`;
}

function formatSignedDuration(value) {
  if (!Number.isFinite(value) || Math.abs(value) < 0.5) return "0s";
  const sign = value > 0 ? "+" : "-";
  const seconds = Math.abs(Math.round(value));
  return `${sign}${seconds < 60 ? `${seconds}s` : formatRaceTime(seconds)}`;
}

function formatElevation(row) {
  const gain = row.elevationGainFeet;
  const loss = row.elevationLossFeet;
  if (gain == null && loss == null) return "-";
  if (gain != null && loss != null) {
    return `+${formatNumber(gain, 0)} / -${formatNumber(loss, 0)} ft`;
  }
  if (gain != null) return `+${formatNumber(gain, 0)} ft`;
  return `-${formatNumber(loss, 0)} ft`;
}

function elevationTitle(row) {
  const value = formatElevation(row);
  if (!row.elevationSource || value === "-") return value;
  return `${value} from ${row.elevationSource}`;
}

function formatTemperature(row) {
  const temperature = row.temperatureF ?? row.apparentTemperatureF;
  const dewPoint = row.dewPointF ?? dewPointFromTemperatureHumidityF(temperature, row.humidity);
  if (temperature == null && dewPoint == null) return "-";
  const parts = [];
  if (temperature != null) parts.push(`${formatNumber(temperature, 0)}&deg;F`);
  if (dewPoint != null) parts.push(`dp ${formatNumber(dewPoint, 0)}&deg;F`);
  return parts.join(" / ");
}

function weatherTitle(row) {
  const value = formatTemperature(row).replaceAll("&deg;", " deg");
  if (value === "-") return value;
  const parts = [value];
  if (row.weatherSource) parts.push(`source ${row.weatherSource}`);
  if (row.weatherStation) parts.push(row.weatherStation);
  if (row.weatherStationDistanceMiles != null) {
    parts.push(`${formatNumber(row.weatherStationDistanceMiles, 1)} mi from start`);
  }
  if (row.weatherObservationOffsetMinutes != null) {
    const offset = row.weatherObservationOffsetMinutes;
    const direction = offset >= 0 ? "after" : "before";
    parts.push(`${formatNumber(Math.abs(offset), 0)} min ${direction} run midpoint`);
  }
  return parts.join(" - ");
}

function interpolateLinear(xs, ys, x) {
  if (!Number.isFinite(x) || xs.length !== ys.length || !xs.length) return null;
  if (xs.length === 1) return ys[0];

  if (x <= xs[0]) {
    const width = xs[1] - xs[0];
    return width ? ys[0] + (ys[1] - ys[0]) * ((x - xs[0]) / width) : ys[0];
  }

  for (let index = 1; index < xs.length; index += 1) {
    if (x <= xs[index]) {
      const width = xs[index] - xs[index - 1];
      return width
        ? ys[index - 1] + (ys[index] - ys[index - 1]) * ((x - xs[index - 1]) / width)
        : ys[index];
    }
  }

  const last = xs.length - 1;
  const width = xs[last] - xs[last - 1];
  return width
    ? ys[last - 1] + (ys[last] - ys[last - 1]) * ((x - xs[last - 1]) / width)
    : ys[last];
}

function norwegianTableDeltaSecPerKm(table, paceSecPerMile, metersPerKm) {
  if (!paceSecPerMile || !Number.isFinite(metersPerKm) || metersPerKm <= 0) return 0;
  const elevationMarks = [0, ...table.metersPerKm];
  const deltasAtPace = table.deltaSecPerKm.map((deltas) =>
    interpolateLinear(elevationMarks, [0, ...deltas], metersPerKm)
  );
  const paceSecPerKm = clamp(
    paceSecPerMile / KM_PER_MILE,
    NORWEGIAN_ELEVATION_PACES_SEC_PER_KM[0],
    NORWEGIAN_ELEVATION_PACES_SEC_PER_KM.at(-1)
  );
  return interpolateLinear(NORWEGIAN_ELEVATION_PACES_SEC_PER_KM, deltasAtPace, paceSecPerKm) ?? 0;
}

function norwegianElevationDeltaSecPerMile(paceSecPerMile, distanceMiles, gainFeet, lossFeet) {
  if (!paceSecPerMile || !distanceMiles || distanceMiles <= 0) return null;
  const gain = Math.abs(gainFeet || 0);
  const loss = Math.abs(lossFeet || 0);
  if (!gain && !loss) return null;

  const distanceKm = distanceMiles * KM_PER_MILE;
  const gainMetersPerKm = gain * 0.3048 / distanceKm;
  const lossMetersPerKm = loss * 0.3048 / distanceKm;
  const rollingMetersPerKm = Math.min(gainMetersPerKm, lossMetersPerKm);
  const netGainMetersPerKm = Math.max(0, gainMetersPerKm - rollingMetersPerKm);
  const netLossMetersPerKm = Math.max(0, lossMetersPerKm - rollingMetersPerKm);

  const deltaSecPerKm =
    norwegianTableDeltaSecPerKm(NORWEGIAN_ELEVATION_TABLES.rolling, paceSecPerMile, rollingMetersPerKm) +
    norwegianTableDeltaSecPerKm(NORWEGIAN_ELEVATION_TABLES.gain, paceSecPerMile, netGainMetersPerKm) +
    norwegianTableDeltaSecPerKm(NORWEGIAN_ELEVATION_TABLES.loss, paceSecPerMile, netLossMetersPerKm);
  return deltaSecPerKm * KM_PER_MILE;
}

function rowElevationProfile(row, scope = "activity") {
  if (scope === "interval") {
    const hasIntervalElevation = row.intervalAscentFeet != null || row.intervalDescentFeet != null;
    return {
      distanceMiles: row.intervalDistanceMiles || row.miles,
      gainFeet: hasIntervalElevation ? row.intervalAscentFeet : row.elevationGainFeet,
      lossFeet: hasIntervalElevation ? row.intervalDescentFeet : row.elevationLossFeet
    };
  }

  return {
    distanceMiles: row.miles,
    gainFeet: row.elevationGainFeet,
    lossFeet: row.elevationLossFeet
  };
}

function elevationDeltaForRow(row, paceSecPerMile, scope = "activity") {
  const profile = rowElevationProfile(row, scope);
  return norwegianElevationDeltaSecPerMile(
    paceSecPerMile,
    profile.distanceMiles,
    profile.gainFeet,
    profile.lossFeet
  );
}

function fahrenheitToCelsius(value) {
  return (value - 32) * 5 / 9;
}

function celsiusToFahrenheit(value) {
  return value * 9 / 5 + 32;
}

function dewPointFromTemperatureHumidityF(tempF, humidityPct) {
  if (tempF == null || humidityPct == null) return null;
  const humidity = clamp(humidityPct, 1, 100);
  const tempC = fahrenheitToCelsius(tempF);
  const a = 17.625;
  const b = 243.04;
  const gamma = Math.log(humidity / 100) + (a * tempC) / (b + tempC);
  return celsiusToFahrenheit((b * gamma) / (a - gamma));
}

function nsmTemperatureReduction(tempF) {
  if (tempF == null) return 0;
  const tempC = fahrenheitToCelsius(tempF);
  if (tempC >= 25) return NSM_WEATHER_MAX_REDUCTION;
  if (tempC >= 20) return 0.02;
  if (tempC >= 15) return 0.01;
  return 0;
}

function nsmDewPointReduction(dewPointF) {
  if (dewPointF == null) return 0;
  const dewPointC = fahrenheitToCelsius(dewPointF);
  if (dewPointC >= 18) return NSM_WEATHER_MAX_REDUCTION;
  if (dewPointC >= 15) return 0.02;
  if (dewPointC >= 12) return 0.01;
  return 0;
}

function nsmWeatherReductionFraction(tempF, dewPointF) {
  return Math.max(nsmTemperatureReduction(tempF), nsmDewPointReduction(dewPointF));
}

function observedWeatherAdjustmentSeconds(paceSecPerMile, tempF, dewPointF) {
  return paceSecPerMile * nsmWeatherReductionFraction(tempF, dewPointF);
}

function targetWeatherAdjustmentSeconds(paceSecPerMile, tempF, dewPointF) {
  const reduction = nsmWeatherReductionFraction(tempF, dewPointF);
  return reduction ? paceSecPerMile / (1 - reduction) - paceSecPerMile : 0;
}

function rowWeatherConditions(row) {
  const temperatureF = row.temperatureF ?? row.apparentTemperatureF;
  return {
    temperatureF,
    dewPointF: row.dewPointF ?? dewPointFromTemperatureHumidityF(temperatureF, row.humidity)
  };
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function getPaceAdjustmentState() {
  return Object.fromEntries(
    PACE_ADJUSTMENT_KEYS.map((key) => {
      const input = document.querySelector(`[data-adjust="${key}"]`);
      return [key, Boolean(input && input.checked)];
    })
  );
}

function getWeeklyMetric() {
  const selected = document.querySelector('input[name="weeklyMetric"]:checked')?.value;
  return WEEKLY_METRICS[selected] ? selected : "trainingLoad";
}

function getPredictionMode() {
  const selected = document.querySelector('input[name="predictionMode"]:checked')?.value;
  return selected === "hrAdjusted" ? "hrAdjusted" : "pace";
}

function getIntervalPaceMode() {
  const selected = document.querySelector('input[name="intervalPaceMode"]:checked')?.value;
  return selected === "intensity" ? "intensity" : "observed";
}

function getEasyPaceMode() {
  const selected = document.querySelector('input[name="easyPaceMode"]:checked')?.value;
  return selected === "intensity" ? "intensity" : "observed";
}

function predictionModeLabel(mode = getPredictionMode()) {
  return mode === "hrAdjusted" ? "intensity-normalized pace" : "pace";
}

function getTargetSource() {
  return document.querySelector('input[name="targetSource"]:checked')?.value || "predicted";
}

function numberInputValue(id) {
  const value = document.getElementById(id)?.value.trim();
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function getTargetConditions() {
  const temperatureF = numberInputValue("targetTemperatureF");
  const humidityPct = numberInputValue("targetHumidityPct");
  return {
    temperatureF,
    humidityPct,
    dewPointF: dewPointFromTemperatureHumidityF(temperatureF, humidityPct),
    elevationGainFeet: numberInputValue("targetElevationGainFeet"),
    elevationLossFeet: numberInputValue("targetElevationLossFeet")
  };
}

function hasTargetConditions(conditions = getTargetConditions()) {
  return conditions.temperatureF != null ||
    conditions.humidityPct != null ||
    conditions.dewPointF != null ||
    conditions.elevationGainFeet != null ||
    conditions.elevationLossFeet != null;
}

function getRecentTypeFilter() {
  return document.getElementById("recentTypeFilter")?.value || "all";
}

function resetRecentPage() {
  recentPage = 0;
}

function resetRecentPageAndRender() {
  resetRecentPage();
  render();
}

function activeAdjustmentLabels() {
  const state = getPaceAdjustmentState();
  return PACE_ADJUSTMENT_KEYS
    .filter((key) => state[key])
    .map((key) => key === "temperature" ? "temp" : key);
}

function paceAdjustmentBreakdown(row, options = {}) {
  const state = getPaceAdjustmentState();
  const rawPace = options.paceSecPerMile ?? row.intervalPaceSecPerMile ?? row.paceSecPerMile;
  const breakdown = {
    elevation: 0,
    temperature: 0
  };

  if (rawPace && state.elevation) {
    const delta = elevationDeltaForRow(row, rawPace, options.elevationScope);
    if (Number.isFinite(delta)) {
      breakdown.elevation = clamp(delta, -120, 180);
    }
  }

  if (rawPace && state.temperature) {
    const weather = rowWeatherConditions(row);
    if (weather.temperatureF != null || weather.dewPointF != null) {
      breakdown.temperature = observedWeatherAdjustmentSeconds(
        rawPace,
        weather.temperatureF,
        weather.dewPointF
      );
    }
  }

  breakdown.total = breakdown.elevation + breakdown.temperature;
  return breakdown;
}

function latestIntervalMileageByTarget(records = DATA.records) {
  return Object.fromEntries(
    Object.entries(INTERVAL_TARGET_CATEGORIES).map(([targetKey, category]) => {
      const latest = records
        .filter((row) => row.category === category && (row.intervalDistanceMiles || row.miles))
        .sort((a, b) => a.datetime.localeCompare(b.datetime))
        .at(-1);
      return [targetKey, latest ? {
        miles: latest.intervalDistanceMiles || latest.miles,
        date: latest.date,
        name: latest.name,
        source: latest.intervalDistanceMiles ? "active intervals" : "workout"
      } : null];
    })
  );
}

function targetConditionBreakdown(rawPace, conditions = getTargetConditions(), mileageBasis = null) {
  const breakdown = {
    elevation: 0,
    temperature: 0
  };

  if (rawPace && (conditions.elevationGainFeet != null || conditions.elevationLossFeet != null)) {
    const delta = norwegianElevationDeltaSecPerMile(
      rawPace,
      mileageBasis?.miles,
      conditions.elevationGainFeet,
      conditions.elevationLossFeet
    );
    if (Number.isFinite(delta)) {
      breakdown.elevation = clamp(delta, -120, 180);
    }
  }

  if (rawPace && (conditions.temperatureF != null || conditions.humidityPct != null || conditions.dewPointF != null)) {
    breakdown.temperature = targetWeatherAdjustmentSeconds(
      rawPace,
      conditions.temperatureF,
      conditions.dewPointF
    );
  }

  breakdown.total = breakdown.elevation + breakdown.temperature;
  return breakdown;
}

function adjustedTargetPace(rawPace, conditions = getTargetConditions(), mileageBasis = null) {
  if (!rawPace || !hasTargetConditions(conditions)) return rawPace;
  const breakdown = targetConditionBreakdown(rawPace, conditions, mileageBasis);
  return Math.max(1, rawPace + breakdown.total);
}

function targetAdjustmentBasisText(mileageBasis) {
  if (!mileageBasis) return " without mileage basis";
  const source = mileageBasis.source ? ` ${mileageBasis.source}` : "";
  const date = mileageBasis.date ? ` from ${formatDate(mileageBasis.date)}` : "";
  return ` over ${formatNumber(mileageBasis.miles, 2)} mi${source}${date}`;
}

function targetConditionsLabel(conditions = getTargetConditions()) {
  const parts = [];
  if (conditions.temperatureF != null) {
    parts.push(`${formatNumber(conditions.temperatureF, 0)}&deg;F`);
  }
  if (conditions.humidityPct != null) {
    const dewLabel = conditions.dewPointF != null
      ? `, dew ${formatNumber(conditions.dewPointF, 0)}&deg;F`
      : "";
    parts.push(`${formatNumber(clamp(conditions.humidityPct, 0, 100), 0)}% RH${dewLabel}`);
  }
  if (conditions.elevationGainFeet != null || conditions.elevationLossFeet != null) {
    const gain = Math.abs(conditions.elevationGainFeet || 0);
    const loss = Math.abs(conditions.elevationLossFeet || 0);
    parts.push(`+${formatNumber(gain, 0)} / -${formatNumber(loss, 0)} ft`);
  }
  return parts.join(", ");
}

function targetAdjustmentTitle(rawPace, conditions = getTargetConditions(), mileageBasis = null) {
  const breakdown = targetConditionBreakdown(rawPace, conditions, mileageBasis);
  const parts = [];
  if (conditions.elevationGainFeet != null || conditions.elevationLossFeet != null) {
    parts.push(`elevation ${formatSignedSecondsPerMile(breakdown.elevation)} via Norwegian tables${targetAdjustmentBasisText(mileageBasis)}`);
  }
  if (conditions.temperatureF != null || conditions.humidityPct != null || conditions.dewPointF != null) {
    const tempCap = conditions.temperatureF != null && conditions.temperatureF > 82
      ? ", capped at NSM 4% max above 82&deg;F"
      : "";
    parts.push(`weather ${formatSignedSecondsPerMile(breakdown.temperature)} via NSM table${tempCap}`);
  }
  return parts.length ? parts.join(", ") : "no adjustment";
}

function adjustedPaceForRow(row, rawPace, options = {}) {
  if (!rawPace) return null;
  const total = options.applyAdjustments === false
    ? 0
    : paceAdjustmentBreakdown(row, { ...options, paceSecPerMile: rawPace }).total;
  return Math.max(1, rawPace - total);
}

function adjustedIntervalPace(row, options = {}) {
  return adjustedPaceForRow(row, row.intervalPaceSecPerMile, { elevationScope: "interval", ...options });
}

function fastest5kPace(row) {
  return row.fastest5kPaceSecPerMile ?? (row.fastest5kSec ? row.fastest5kSec / FIVE_K_MILES : null);
}

function adjustedTrialTime(row, options = {}) {
  if (!row.fastest5kSec) return null;
  const rawPace = fastest5kPace(row);
  if (!rawPace) return row.fastest5kSec;
  const total = options.applyAdjustments === false
    ? 0
    : paceAdjustmentBreakdown(row, { ...options, paceSecPerMile: rawPace }).total;
  if (!total) return row.fastest5kSec;
  return Math.max(1, rawPace - total) * FIVE_K_MILES;
}

function adjustedTrialPace(row, options = {}) {
  const rawPace = fastest5kPace(row);
  return rawPace ? adjustedPaceForRow(row, rawPace, options) : null;
}

function paceAdjustmentTitle(row, adjustedPace) {
  return runPaceAdjustmentTitle(row, row.intervalPaceSecPerMile, adjustedPace, { elevationScope: "interval" });
}

function runPaceAdjustmentTitle(row, rawPace, adjustedPace, options = {}) {
  const labels = activeAdjustmentLabels();
  if (!labels.length) {
    return `${formatPace(rawPace)}`;
  }
  const breakdown = paceAdjustmentBreakdown(row, { ...options, paceSecPerMile: rawPace });
  const parts = PACE_ADJUSTMENT_KEYS
    .filter((key) => breakdown[key])
    .map((key) => `${key === "temperature" ? "temp" : key} ${formatSignedSecondsPerMile(breakdown[key])}`);
  const suffix = parts.length ? `; ${parts.join(", ")}` : "";
  return `${formatPace(adjustedPace)} adjusted from ${formatPace(rawPace)}${suffix}`;
}

function adjustedTrialTitle(row, adjustedSeconds) {
  const labels = activeAdjustmentLabels();
  if (!labels.length) return `${formatDuration(row.fastest5kSec)} actual`;

  const rawPace = fastest5kPace(row);
  const breakdown = paceAdjustmentBreakdown(row, { paceSecPerMile: rawPace });
  const parts = PACE_ADJUSTMENT_KEYS
    .filter((key) => breakdown[key])
    .map((key) => `${key === "temperature" ? "temp" : key} ${Math.round(breakdown[key])}s/mi`);
  const suffix = parts.length ? `; ${parts.join(", ")}` : "";
  return `${formatDuration(adjustedSeconds)} adjusted from ${formatDuration(row.fastest5kSec)}${suffix}`;
}

function recentPaceInfo(row) {
  if (INTERVAL_CATEGORIES.has(row.category) && row.intervalPaceSecPerMile) {
    const pace = adjustedIntervalPace(row);
    return {
      pace,
      title: paceAdjustmentTitle(row, pace)
    };
  }

  if (EASY_CATEGORIES.has(row.category) && row.paceSecPerMile) {
    const pace = adjustedPaceForRow(row, row.paceSecPerMile);
    return {
      pace,
      title: runPaceAdjustmentTitle(row, row.paceSecPerMile, pace)
    };
  }

  if (row.category === "5k_time_trial") {
    const rawPace = fastest5kPace(row) ?? row.paceSecPerMile;
    const pace = fastest5kPace(row)
      ? adjustedTrialPace(row)
      : adjustedPaceForRow(row, row.paceSecPerMile);
    return {
      pace,
      title: rawPace ? runPaceAdjustmentTitle(row, rawPace, pace) : "-"
    };
  }

  return {
    pace: row.paceSecPerMile,
    title: formatPace(row.paceSecPerMile)
  };
}

function intervalRows(records) {
  return records
    .filter((row) =>
      ["short_interval", "medium_interval", "long_interval"].includes(row.category) &&
      row.intervalPaceSecPerMile &&
      row.intervalAvgHr
    )
    .sort((a, b) => a.datetime.localeCompare(b.datetime));
}

function median(values) {
  const sorted = values
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);
  if (!sorted.length) return null;
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2) return sorted[middle];
  return (sorted[middle - 1] + sorted[middle]) / 2;
}

function quantile(values, probability) {
  const sorted = values
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => a - b);
  if (!sorted.length) return null;
  const index = (sorted.length - 1) * clamp(probability, 0, 1);
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (index - lower);
}

function mean(values) {
  const finite = values.filter((value) => Number.isFinite(value));
  if (!finite.length) return null;
  return finite.reduce((sum, value) => sum + value, 0) / finite.length;
}

function restingHrForDate(date) {
  const time = parseDate(date).getTime();
  const week = DATA.weeks.find((row) => {
    const start = parseDate(row.week).getTime();
    return time >= start && time <= start + 6 * DAY_MS;
  });
  if (week?.restingHrAvg != null) return week.restingHrAvg;
  return median(DATA.weeks.map((row) => row.restingHrAvg));
}

function restingHrForRow(row) {
  return row.restingHr ?? restingHrForDate(row.date);
}

function intervalIntensity(row) {
  const heartRate = row.intervalAvgHr;
  const restingHr = restingHrForRow(row);
  const maxHr = DATA.meta.maxHr;
  if (!heartRate || !restingHr || !maxHr || maxHr <= restingHr) return null;
  return clamp((heartRate - restingHr) / (maxHr - restingHr), 0.3, 1.15);
}

function intervalSpeed(row, options = {}) {
  const pace = adjustedIntervalPace(row, options);
  return pace ? METERS_PER_MILE / pace : null;
}

function defaultIntensityBeta(rows) {
  const typicalIntensity = median(rows.map(intervalIntensity)) ?? DEFAULT_INTENSITY_TARGET;
  return clamp(1 / typicalIntensity, 0.8, 1.35);
}

function estimateIntensityBeta(rows, options = {}) {
  const sorted = rows
    .filter((row) => intervalIntensity(row) != null && intervalSpeed(row, options))
    .sort((a, b) => a.datetime.localeCompare(b.datetime));
  const defaultBeta = defaultIntensityBeta(sorted);
  const slopes = [];

  for (let index = 1; index < sorted.length; index += 1) {
    const previous = sorted[index - 1];
    const row = sorted[index];
    const gapDays = (parseDate(row.date).getTime() - parseDate(previous.date).getTime()) / DAY_MS;
    if (gapDays > 45) continue;

    const intensityDelta = intervalIntensity(row) - intervalIntensity(previous);
    if (Math.abs(intensityDelta) < 0.015) continue;

    const speedRatio = intervalSpeed(row, options) / intervalSpeed(previous, options);
    const slope = Math.log(speedRatio) / intensityDelta;
    if (Number.isFinite(slope) && slope > 0 && slope < 3) {
      slopes.push(slope);
    }
  }

  const rawBeta = median(slopes);
  if (!rawBeta) return defaultBeta;
  const shrink = slopes.length / (slopes.length + 6);
  return clamp(defaultBeta * (1 - shrink) + rawBeta * shrink, 0.65, 2.0);
}

function buildIntensityModel(records, options = {}) {
  const intervals = intervalRows(records);
  const allIntensities = intervals.map(intervalIntensity).filter((value) => Number.isFinite(value));
  const overallTarget = median(allIntensities) ?? DEFAULT_INTENSITY_TARGET;
  const overallBeta = estimateIntensityBeta(intervals, options);
  const targets = {};
  const betas = {};
  const counts = {};

  INTERVAL_CATEGORIES.forEach((category) => {
    const rows = intervals.filter((row) => row.category === category);
    const intensities = rows.map(intervalIntensity).filter((value) => Number.isFinite(value));
    targets[category] = median(intensities) ?? overallTarget;
    betas[category] = estimateIntensityBeta(rows, options) ?? overallBeta;
    counts[category] = intensities.length;
  });

  return { targets, betas, counts, overallTarget, overallBeta };
}

function intensityNormalizedPace(row, model, options = {}) {
  const pace = adjustedIntervalPace(row, options);
  const intensity = intervalIntensity(row);
  if (!pace || !intensity) return null;

  const target = model?.targets?.[row.category] ?? model?.overallTarget ?? intensity;
  const beta = model?.betas?.[row.category] ?? model?.overallBeta ?? defaultIntensityBeta([row]);
  const observedSpeed = METERS_PER_MILE / pace;
  const normalizedSpeed = observedSpeed * Math.exp(beta * (target - intensity));
  return normalizedSpeed > 0 ? METERS_PER_MILE / normalizedSpeed : null;
}

function easyPaceRows(records, requireHeartRate = false) {
  return records
    .filter((row) =>
      EASY_CATEGORIES.has(row.category) &&
      row.paceSecPerMile &&
      (!requireHeartRate || row.avgHr)
    )
    .sort((a, b) => a.datetime.localeCompare(b.datetime));
}

function easyRunIntensity(row) {
  const heartRate = row.avgHr;
  const restingHr = restingHrForRow(row);
  const maxHr = DATA.meta.maxHr;
  if (!heartRate || !restingHr || !maxHr || maxHr <= restingHr) return null;
  return clamp((heartRate - restingHr) / (maxHr - restingHr), 0.2, 0.9);
}

function easyRunSpeed(row, options = {}) {
  const pace = adjustedPaceForRow(row, row.paceSecPerMile, options);
  return pace ? METERS_PER_MILE / pace : null;
}

function defaultEasyIntensityBeta(rows) {
  const typicalIntensity = median(rows.map(easyRunIntensity)) ?? 0.55;
  return clamp(1 / typicalIntensity, 1.1, 2.3);
}

function estimateEasyIntensityBeta(rows, options = {}) {
  const sorted = rows
    .filter((row) => easyRunIntensity(row) != null && easyRunSpeed(row, options))
    .sort((a, b) => a.datetime.localeCompare(b.datetime));
  const defaultBeta = defaultEasyIntensityBeta(sorted);
  const slopes = [];

  for (let index = 1; index < sorted.length; index += 1) {
    const previous = sorted[index - 1];
    const row = sorted[index];
    const gapDays = (parseDate(row.date).getTime() - parseDate(previous.date).getTime()) / DAY_MS;
    if (gapDays > 21) continue;

    const intensityDelta = easyRunIntensity(row) - easyRunIntensity(previous);
    if (Math.abs(intensityDelta) < 0.015) continue;

    const speedRatio = easyRunSpeed(row, options) / easyRunSpeed(previous, options);
    const slope = Math.log(speedRatio) / intensityDelta;
    if (Number.isFinite(slope) && slope > 0 && slope < 3) {
      slopes.push(slope);
    }
  }

  const rawBeta = median(slopes);
  if (!rawBeta) return defaultBeta;
  const shrink = slopes.length / (slopes.length + 8);
  return clamp(defaultBeta * (1 - shrink) + rawBeta * shrink, 0.8, 2.4);
}

function buildEasyIntensityModel(records, options = {}) {
  const rows = easyPaceRows(records, true);
  const intensities = rows.map(easyRunIntensity).filter((value) => Number.isFinite(value));
  const targetIntensity = median(intensities) ?? 0.55;
  return {
    targetIntensity,
    beta: estimateEasyIntensityBeta(rows, options),
    count: intensities.length
  };
}

function intensityNormalizedEasyPace(row, model, options = {}) {
  const pace = adjustedPaceForRow(row, row.paceSecPerMile, options);
  const intensity = easyRunIntensity(row);
  if (!pace || !intensity) return null;

  const target = model?.targetIntensity ?? intensity;
  const beta = model?.beta ?? defaultEasyIntensityBeta([row]);
  const observedSpeed = METERS_PER_MILE / pace;
  const normalizedSpeed = observedSpeed * Math.exp(beta * (target - intensity));
  return normalizedSpeed > 0 ? METERS_PER_MILE / normalizedSpeed : null;
}

function outdoorEasyPredictionRows(records, requireHeartRate = false) {
  return easyPaceRows(records, requireHeartRate)
    .filter((row) => row.type === "running");
}

function isTrailRun(row) {
  return row.type === "trail_running";
}

function runSurfaceLabel(row) {
  return isTrailRun(row) ? "Trail run" : "Regular run";
}

function trianglePath(cx, cy, r) {
  return [
    `M ${cx.toFixed(1)} ${(cy - r).toFixed(1)}`,
    `L ${(cx + r * 0.95).toFixed(1)} ${(cy + r * 0.75).toFixed(1)}`,
    `L ${(cx - r * 0.95).toFixed(1)} ${(cy + r * 0.75).toFixed(1)}`,
    "Z"
  ].join(" ");
}

function rollingEasyPaceRange(points) {
  const regularPoints = points.filter((point) => !isTrailRun(point.row));
  const range = [];
  let windowPoints = [];
  let previous = null;
  let previousRange = null;

  regularPoints.forEach((point) => {
    if (previous) {
      const gapDays = (parseDate(point.row.date).getTime() - parseDate(previous.row.date).getTime()) / DAY_MS;
      if (gapDays > EASY_PACE_RANGE_GAP_DAYS) {
        windowPoints = [];
        previousRange = null;
      }
    }

    windowPoints.push(point.value);
    windowPoints = windowPoints.slice(-EASY_PACE_RANGE_WINDOW);
    if (windowPoints.length >= EASY_PACE_RANGE_MIN_POINTS) {
      const rawLower = quantile(windowPoints, 0.25);
      const rawUpper = quantile(windowPoints, 0.75);
      const lower = previousRange
        ? previousRange.lower * (1 - EASY_PACE_RANGE_SMOOTHING) + rawLower * EASY_PACE_RANGE_SMOOTHING
        : rawLower;
      const upper = previousRange
        ? previousRange.upper * (1 - EASY_PACE_RANGE_SMOOTHING) + rawUpper * EASY_PACE_RANGE_SMOOTHING
        : rawUpper;
      previousRange = {
        date: point.row.date,
        lower,
        upper,
        count: windowPoints.length
      };
      range.push(previousRange);
    }
    previous = point;
  });

  return range;
}

function parseRaceTime(value) {
  const text = String(value || "").trim();
  if (!text) return null;
  const parts = text.split(":").map((part) => part.trim());
  if (parts.some((part) => part === "" || Number.isNaN(Number(part)))) return null;

  let seconds = null;
  if (parts.length === 1) {
    seconds = Number(parts[0]);
  } else if (parts.length === 2) {
    seconds = Number(parts[0]) * 60 + Number(parts[1]);
  } else if (parts.length === 3) {
    seconds = Number(parts[0]) * 3600 + Number(parts[1]) * 60 + Number(parts[2]);
  }

  return seconds && seconds > 0 ? seconds : null;
}

function vdotOxygenDemand(speedMetersPerMin) {
  return 0.000104 * speedMetersPerMin ** 2 + 0.182258 * speedMetersPerMin - 4.6;
}

function fractionalVdot(durationMin) {
  return 0.2989558 * Math.exp(-0.1932605 * durationMin) +
    0.1894393 * Math.exp(-0.012778 * durationMin) +
    0.8;
}

function speedFromVdot(durationMin, vdot) {
  const oxygenDemand = fractionalVdot(durationMin) * vdot;
  return 29.54 + 5.000663 * oxygenDemand - 0.007546 * oxygenDemand ** 2;
}

function vdotFromRace(distanceMeters, raceSeconds) {
  const durationMin = raceSeconds / 60;
  const raceSpeed = distanceMeters / durationMin;
  return vdotOxygenDemand(raceSpeed) / fractionalVdot(durationMin);
}

function paceFromSpeedMetersPerMin(speedMetersPerMin) {
  return METERS_PER_MILE / speedMetersPerMin * 60;
}

function equivalentRaceTime(distanceMeters, vdot) {
  const distanceAt = (durationMin) => speedFromVdot(durationMin, vdot) * durationMin;
  let low = 0.1;
  let high = 600;

  while (distanceAt(high) < distanceMeters && high < 2000) {
    high *= 1.5;
  }

  for (let index = 0; index < 80; index += 1) {
    const mid = (low + high) / 2;
    if (distanceAt(mid) < distanceMeters) {
      low = mid;
    } else {
      high = mid;
    }
  }

  return ((low + high) / 2) * 60;
}

function racePredictionFromVdot(race, vdot) {
  const seconds = equivalentRaceTime(race.distanceMeters, vdot);
  return {
    ...race,
    seconds,
    paceSecPerMile: seconds / (race.distanceMeters / METERS_PER_MILE)
  };
}

function racePredictionsFromVdot(vdot) {
  return RACE_PREDICTIONS.map((race) => racePredictionFromVdot(race, vdot));
}

function adjustedTargetRacePrediction(race, conditions = getTargetConditions()) {
  const distanceMiles = race.distanceMeters / METERS_PER_MILE;
  const mileageBasis = {
    miles: distanceMiles,
    source: "race distance"
  };
  const adjustedPace = adjustedTargetPace(race.paceSecPerMile, conditions, mileageBasis);
  const adjustedSeconds = adjustedPace * distanceMiles;
  return {
    seconds: adjustedSeconds,
    paceSecPerMile: adjustedPace,
    deltaSeconds: adjustedSeconds - race.seconds,
    title: targetAdjustmentTitle(race.paceSecPerMile, conditions, mileageBasis)
  };
}

function intervalTargetsFrom5k(raceSeconds) {
  const vdot = vdotFromRace(FIVE_K_METERS, raceSeconds);
  return {
    vdot,
    rows: INTERVAL_TARGETS.map((target) => {
      const speed = speedFromVdot(target.durationMin, vdot);
      return {
        ...target,
        paceSecPerMile: paceFromSpeedMetersPerMin(speed),
        speedMetersPerMin: speed
      };
    })
  };
}

function predicted5kPace(row, mode = getPredictionMode(), options = {}, model = null) {
  if (mode === "hrAdjusted") {
    return intensityNormalizedPace(row, model, options);
  }
  return adjustedIntervalPace(row, options);
}

function buildRawPredicted5kSeries(records, mode = getPredictionMode(), options = {}) {
  const intervals = records
    .filter((row) =>
      ["short_interval", "medium_interval", "long_interval"].includes(row.category) &&
      row.intervalPaceSecPerMile
    )
    .sort((a, b) => a.datetime.localeCompare(b.datetime));
  const recent = {
    short_interval: [],
    medium_interval: [],
    long_interval: []
  };
  const series = [];
  let previous = null;
  const intensityModel = mode === "hrAdjusted" ? buildIntensityModel(intervals, options) : null;

  intervals.forEach((row) => {
    if (previous) {
      const gapDays = (parseDate(row.date).getTime() - parseDate(previous.date).getTime()) / (24 * 60 * 60 * 1000);
      if (gapDays > INTERVAL_LINE_GAP_DAYS) {
        Object.keys(recent).forEach((key) => {
          recent[key] = [];
        });
      }
    }

    const predictionPace = predicted5kPace(row, mode, options, intensityModel);
    if (predictionPace == null) {
      previous = row;
      return;
    }

    recent[row.category].push(predictionPace);
    recent[row.category] = recent[row.category].slice(-3);

    const available = Object.entries(recent)
      .filter(([, values]) => values.length)
      .map(([category, values]) => ({
        category,
        value: mean(values)
      }));
    if (available.length) {
      const pace = mean(available.map((item) => item.value));
      series.push({
        date: row.date,
        value: pace * FIVE_K_MILES,
        mode,
        sources: available.map((item) => DATA.labels[item.category]).join(", ")
      });
    }

    previous = row;
  });

  return series;
}

function predictionCalibration(records, mode = getPredictionMode(), options = {}) {
  const rawSeries = buildRawPredicted5kSeries(records, mode, options);
  const trials = records
    .filter((row) => row.category === "5k_time_trial" && row.fastest5kSec)
    .sort((a, b) => a.datetime.localeCompare(b.datetime));
  const ratios = [];

  trials.forEach((trial) => {
    const trialTime = parseDate(trial.date).getTime();
    const prior = rawSeries
      .filter((row) => {
        const rowTime = parseDate(row.date).getTime();
        const daysBefore = (trialTime - rowTime) / (24 * 60 * 60 * 1000);
        return daysBefore >= 0 && daysBefore <= PREDICTION_CALIBRATION_LOOKBACK_DAYS;
      })
      .at(-1);

    if (prior && prior.value > 0) {
      const trialTime = adjustedTrialTime(trial, options);
      if (trialTime) {
        ratios.push(trialTime / prior.value);
      }
    }
  });

  const ratio = median(ratios);
  return {
    ratio: ratio ? clamp(ratio, 0.75, 1.05) : 1,
    count: ratios.length
  };
}

function buildPredicted5kSeries(records, calibrationRecords = DATA.records, mode = getPredictionMode(), options = {}) {
  const calibration = predictionCalibration(calibrationRecords, mode, options);
  return buildRawPredicted5kSeries(records, mode, options).map((row) => ({
    ...row,
    rawValue: row.value,
    value: row.value * calibration.ratio,
    calibrationRatio: calibration.ratio,
    calibrationCount: calibration.count
  }));
}

function buildRawEasyPredicted5kSeries(records, mode = getPredictionMode(), options = {}) {
  const easy = outdoorEasyPredictionRows(records, mode === "hrAdjusted");
  const intensityModel = mode === "hrAdjusted" ? buildEasyIntensityModel(easy, options) : null;
  const series = [];
  let recentPaces = [];
  let previous = null;

  easy.forEach((row) => {
    if (previous) {
      const gapDays = (parseDate(row.date).getTime() - parseDate(previous.date).getTime()) / DAY_MS;
      if (gapDays > EASY_PACE_RANGE_GAP_DAYS) {
        recentPaces = [];
      }
    }

    const pace = mode === "hrAdjusted"
      ? intensityNormalizedEasyPace(row, intensityModel, options)
      : adjustedPaceForRow(row, row.paceSecPerMile, options);
    if (Number.isFinite(pace)) {
      recentPaces.push(pace);
      recentPaces = recentPaces.slice(-EASY_PACE_RANGE_WINDOW);
      if (recentPaces.length >= EASY_PACE_RANGE_MIN_POINTS) {
        const rollingPace = median(recentPaces);
        series.push({
          date: row.date,
          datetime: row.datetime,
          value: rollingPace * FIVE_K_MILES,
          easyPaceSecPerMile: rollingPace,
          count: recentPaces.length,
          mode
        });
      }
    }
    previous = row;
  });

  return series;
}

function easyPredictionCalibration(records, mode = getPredictionMode(), options = {}) {
  const rawSeries = buildRawEasyPredicted5kSeries(records, mode, options);
  const trials = records
    .filter((row) => row.category === "5k_time_trial" && row.fastest5kSec)
    .sort((a, b) => a.datetime.localeCompare(b.datetime));
  const ratios = [];

  trials.forEach((trial) => {
    const trialTime = parseDate(trial.date).getTime();
    const prior = rawSeries
      .filter((row) => {
        const rowTime = parseDate(row.date).getTime();
        const daysBefore = (trialTime - rowTime) / DAY_MS;
        return row.datetime <= trial.datetime &&
          daysBefore >= 0 && daysBefore <= PREDICTION_CALIBRATION_LOOKBACK_DAYS;
      })
      .at(-1);
    const actualTime = adjustedTrialTime(trial, options);

    if (prior?.value > 0 && actualTime) {
      ratios.push(actualTime / prior.value);
    }
  });

  const ratio = median(ratios);
  return {
    ratio: ratios.length >= EASY_5K_MIN_CALIBRATIONS && ratio
      ? clamp(ratio, EASY_5K_CALIBRATION_MIN, EASY_5K_CALIBRATION_MAX)
      : null,
    count: ratios.length
  };
}

function buildEasyPredicted5kSeries(records, calibrationRecords = DATA.records, mode = getPredictionMode(), options = {}) {
  const calibration = easyPredictionCalibration(calibrationRecords, mode, options);
  if (!calibration.ratio) return [];

  return buildRawEasyPredicted5kSeries(records, mode, options).map((row) => ({
    ...row,
    rawValue: row.value,
    value: row.value * calibration.ratio,
    calibrationRatio: calibration.ratio,
    calibrationCount: calibration.count
  }));
}

function latest5kTrial(records = DATA.records) {
  return records
    .filter((row) => row.category === "5k_time_trial" && row.fastest5kSec)
    .sort((a, b) => a.datetime.localeCompare(b.datetime))
    .at(-1) || null;
}

function latestPredicted5k(records = DATA.records, mode = getPredictionMode()) {
  return buildPredicted5kSeries(records, DATA.records, mode).at(-1) || null;
}

function selectedTargetBasis() {
  const source = getTargetSource();
  if (source === "latest") {
    const trial = latest5kTrial();
    if (!trial) {
      return { source, error: "No 5K time trial found." };
    }
    const seconds = adjustedTrialTime(trial) ?? trial.fastest5kSec;
    return {
      source,
      seconds,
      label: `Latest 5K TT (${formatDate(trial.date, { year: "numeric" })})`,
      detail: adjustedTrialTitle(trial, seconds)
    };
  }

  if (source === "predicted") {
    const mode = getPredictionMode();
    const prediction = latestPredicted5k(DATA.records, mode);
    if (!prediction) {
      return { source, error: "No 5K prediction available." };
    }
    return {
      source,
      seconds: prediction.value,
      label: `Predicted 5K (${predictionModeLabel(mode)})`,
      detail: `${formatDuration(prediction.value)} calibrated from ${prediction.calibrationCount} trials`
    };
  }

  const customSeconds = parseRaceTime(document.getElementById("customTargetTime")?.value);
  if (!customSeconds) {
    return { source, error: "Enter a 5K time as mm:ss or h:mm:ss." };
  }
  return {
    source,
    seconds: customSeconds,
    label: "Custom 5K",
    detail: `${formatDuration(customSeconds)} entered`
  };
}

function splitRowsByDateGap(rows, maxGapDays = INTERVAL_LINE_GAP_DAYS) {
  const segments = [];
  let current = [];

  rows.forEach((row) => {
    const previous = current[current.length - 1];
    const gapDays = previous
      ? (parseDate(row.date).getTime() - parseDate(previous.date).getTime()) / (24 * 60 * 60 * 1000)
      : 0;

    if (previous && gapDays > maxGapDays) {
      segments.push(current);
      current = [];
    }
    current.push(row);
  });

  if (current.length) segments.push(current);
  return segments;
}

function formatDateInputValue(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function dataDateBounds() {
  const recordTimes = DATA.records.map((row) => parseDate(row.date).getTime());
  const weekTimes = DATA.weeks.map((week) => parseDate(week.week).getTime());
  const fallback = parseDate(DATA.meta.startDate).getTime();
  const earliestTime = Math.min(...recordTimes, ...weekTimes, fallback);
  const latestTime = Math.max(...recordTimes, ...weekTimes, fallback);

  return {
    earliest: formatDateInputValue(new Date(earliestTime)),
    latest: formatDateInputValue(new Date(latestTime)),
    earliestTime,
    latestTime
  };
}

function selectedCustomDateRange() {
  const bounds = dataDateBounds();
  const startValue = document.getElementById("customStartDate")?.value || bounds.earliest;
  const endValue = document.getElementById("customEndDate")?.value || bounds.latest;
  const startTime = parseDate(startValue).getTime();
  const endTime = parseDate(endValue).getTime();

  return {
    startTime: Math.min(startTime, endTime),
    endTime: Math.max(startTime, endTime)
  };
}

function rangeFiltered() {
  const value = document.getElementById("rangeSelect").value;
  if (value === "all") {
    return {
      records: DATA.records,
      weeks: DATA.weeks
    };
  }

  if (value === "custom") {
    const { startTime, endTime } = selectedCustomDateRange();
    return {
      records: DATA.records.filter((row) => {
        const time = parseDate(row.date).getTime();
        return time >= startTime && time <= endTime;
      }),
      weeks: DATA.weeks.filter((week) => {
        const weekStart = parseDate(week.week).getTime();
        const weekEnd = weekStart + 6 * DAY_MS;
        return weekStart <= endTime && weekEnd >= startTime;
      })
    };
  }

  const days = Number(value);
  const latest = dataDateBounds().latestTime;
  const cutoff = latest - days * DAY_MS;

  return {
    records: DATA.records.filter((row) => parseDate(row.date).getTime() >= cutoff),
    weeks: DATA.weeks.filter((week) => parseDate(week.week).getTime() >= cutoff)
  };
}

function svgEl(name, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
  return el;
}

function ensureChartTooltip() {
  if (chartTooltip) return chartTooltip;
  chartTooltip = document.createElement("div");
  chartTooltip.className = "chart-tooltip";
  chartTooltip.hidden = true;
  document.body.appendChild(chartTooltip);
  return chartTooltip;
}

function tooltipPoint(event) {
  if (Number.isFinite(event.clientX) && Number.isFinite(event.clientY)) {
    return { x: event.clientX, y: event.clientY };
  }
  const rect = event.currentTarget.getBoundingClientRect();
  return {
    x: rect.left + rect.width / 2,
    y: rect.top + rect.height / 2
  };
}

function positionChartTooltip(event) {
  const tooltip = ensureChartTooltip();
  const point = tooltipPoint(event);
  const margin = 12;
  const offset = 14;
  const rect = tooltip.getBoundingClientRect();
  let left = point.x + offset;
  let top = point.y + offset;

  if (left + rect.width + margin > window.innerWidth) {
    left = point.x - rect.width - offset;
  }
  if (top + rect.height + margin > window.innerHeight) {
    top = point.y - rect.height - offset;
  }

  tooltip.style.left = `${Math.max(margin, left)}px`;
  tooltip.style.top = `${Math.max(margin, top)}px`;
}

function showChartTooltip(event, text) {
  const tooltip = ensureChartTooltip();
  tooltip.textContent = text;
  tooltip.hidden = false;
  positionChartTooltip(event);
}

function hideChartTooltip() {
  if (chartTooltip) {
    chartTooltip.hidden = true;
  }
}

function addSvgHover(svg, visual, hitName, hitAttrs, tooltipText) {
  visual.classList.add("chart-hoverable");
  const hit = svgEl(hitName, {
    ...hitAttrs,
    class: "chart-hit",
    "aria-hidden": "true"
  });

  const show = (event) => {
    visual.classList.add("is-hovered");
    showChartTooltip(event, tooltipText);
  };
  const hide = () => {
    visual.classList.remove("is-hovered");
    hideChartTooltip();
  };

  hit.addEventListener("pointerenter", show);
  hit.addEventListener("pointermove", positionChartTooltip);
  hit.addEventListener("pointerdown", show);
  hit.addEventListener("pointerleave", hide);
  hit.addEventListener("pointercancel", hide);
  svg.appendChild(hit);
  return hit;
}

function svgPoint(svg, event) {
  const point = svg.createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;
  return point.matrixTransform(svg.getScreenCTM().inverse());
}

function setCustomRangeFromTimes(startTime, endTime) {
  const bounds = dataDateBounds();
  const lower = Math.max(bounds.earliestTime, Math.min(startTime, endTime));
  const upper = Math.min(bounds.latestTime, Math.max(startTime, endTime));
  const rangeSelect = document.getElementById("rangeSelect");
  const customControls = document.getElementById("customRangeControls");
  const startInput = document.getElementById("customStartDate");
  const endInput = document.getElementById("customEndDate");

  if (!rangeSelect || !startInput || !endInput) return;

  rangeSelect.value = "custom";
  if (customControls) customControls.hidden = false;
  startInput.value = formatDateInputValue(new Date(lower));
  endInput.value = formatDateInputValue(new Date(upper));
  resetRecentPageAndRender();
}

function addChartZoom(svg, plot, startTime, endTime) {
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime)) return;

  const minTime = Math.min(startTime, endTime);
  const maxTime = Math.max(startTime, endTime);
  const timeSpan = Math.max(DAY_MS, maxTime - minTime);
  let drag = null;
  let selection = null;

  svg.classList.add("chart-zoomable");
  const surface = svgEl("rect", {
    x: plot.x,
    y: plot.y,
    width: plot.w,
    height: plot.h,
    class: "chart-zoom-surface",
    "aria-hidden": "true"
  });
  svg.insertBefore(surface, svg.firstChild);

  const clampX = (value) => clamp(value, plot.x, plot.x + plot.w);
  const timeForX = (value) => {
    const ratio = (clampX(value) - plot.x) / plot.w;
    return minTime + ratio * timeSpan;
  };
  const removeSelection = () => {
    selection?.remove();
    selection = null;
  };

  svg.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    const point = svgPoint(svg, event);
    if (
      point.x < plot.x ||
      point.x > plot.x + plot.w ||
      point.y < plot.y ||
      point.y > plot.y + plot.h
    ) {
      return;
    }

    drag = {
      pointerId: event.pointerId,
      startX: clampX(point.x),
      currentX: clampX(point.x),
      active: false
    };
    svg.setPointerCapture(event.pointerId);
  });

  svg.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const point = svgPoint(svg, event);
    drag.currentX = clampX(point.x);
    const width = Math.abs(drag.currentX - drag.startX);
    if (width < 5 && !drag.active) return;

    drag.active = true;
    hideChartTooltip();
    if (!selection) {
      selection = svgEl("rect", {
        class: "chart-zoom-selection",
        y: plot.y,
        height: plot.h
      });
      svg.appendChild(selection);
    }
    selection.setAttribute("x", Math.min(drag.startX, drag.currentX));
    selection.setAttribute("width", width);
    event.preventDefault();
  });

  const finish = (event) => {
    if (!drag) return;
    const width = Math.abs(drag.currentX - drag.startX);
    const shouldZoom = drag.active && width >= 10;
    const start = timeForX(drag.startX);
    const end = timeForX(drag.currentX);

    try {
      svg.releasePointerCapture(drag.pointerId);
    } catch {
      // Pointer capture may already be released by the browser.
    }
    drag = null;
    removeSelection();

    if (shouldZoom) {
      setCustomRangeFromTimes(start, end);
    }
  };

  svg.addEventListener("pointerup", finish);
  svg.addEventListener("pointercancel", finish);
  svg.addEventListener("lostpointercapture", () => {
    if (!drag) return;
    drag = null;
    removeSelection();
  });
}

function clear(node) {
  node.replaceChildren();
}

function minMax(values, pad = 0) {
  const finite = values.filter((value) => Number.isFinite(value));
  if (!finite.length) return [0, 1];
  let min = Math.min(...finite);
  let max = Math.max(...finite);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  return [min - pad, max + pad];
}

function addText(svg, text, x, y, className = "chart-label", anchor = "start") {
  const node = svgEl("text", { x, y, class: className, "text-anchor": anchor });
  node.textContent = text;
  svg.appendChild(node);
  return node;
}

function addEmpty(container, text) {
  clear(container);
  const empty = document.createElement("div");
  empty.className = "empty";
  empty.textContent = text;
  container.appendChild(empty);
}

function makeSvg(width = 760, height = 280) {
  return svgEl("svg", {
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-hidden": "false"
  });
}

function drawYGrid(svg, plot, ticks, scale, formatter) {
  ticks.forEach((tick) => {
    const y = scale(tick);
    svg.appendChild(svgEl("line", {
      x1: plot.x,
      x2: plot.x + plot.w,
      y1: y,
      y2: y,
      class: "grid-line"
    }));
    addText(svg, formatter(tick), plot.x - 8, y + 4, "chart-label", "end");
  });
}

function niceTicks(min, max, count = 5) {
  const span = max - min;
  if (!Number.isFinite(span) || span <= 0) return [min, max];
  const rough = span / Math.max(1, count - 1);
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const residual = rough / magnitude;
  const step = residual >= 5 ? 5 * magnitude : residual >= 2 ? 2 * magnitude : magnitude;
  const first = Math.ceil(min / step) * step;
  const ticks = [];
  for (let value = first; value <= max + step * 0.5; value += step) {
    ticks.push(Number(value.toFixed(6)));
  }
  return ticks;
}

function renderMeta() {
  const meta = DATA.meta;
  const built = new Date(meta.builtAt);
  document.getElementById("metaLine").textContent =
    `Since ${formatDate(meta.startDate, { year: "numeric" })} | max HR ${meta.maxHr} | easy ceiling <${meta.easyHrDisplayThreshold} bpm | built ${built.toLocaleString()}`;
}

function summarize(records, weeks) {
  const easy = records.filter((row) => EASY_CATEGORIES.has(row.category));
  const trials = records.filter((row) => row.category === "5k_time_trial" && row.fastest5kSec);
  const intervals = records.filter((row) =>
    ["short_interval", "medium_interval", "long_interval"].includes(row.category)
  );

  const easyWeight = easy.reduce((sum, row) => sum + (row.easyHrTotalMin || row.minutes || 0), 0);
  const easyPct = easyWeight
    ? easy.reduce((sum, row) => sum + (row.easyHrUnderPct || 0) * (row.easyHrTotalMin || row.minutes || 0), 0) / easyWeight
    : null;

  const bestTrial = trials.length ? trials.reduce((best, row) => row.fastest5kSec < best.fastest5kSec ? row : best) : null;
  const latestTrial = trials.length ? trials[trials.length - 1] : null;
  const lastFour = weeks.slice(-4);
  const lastFourAvg = lastFour.length
    ? lastFour.reduce((sum, week) => sum + week.runMiles, 0) / lastFour.length
    : null;

  return {
    runMiles: records.filter((row) => row.isRun).reduce((sum, row) => sum + row.miles, 0),
    lastFourAvg,
    easyPct,
    bestTrial,
    latestTrial,
    intervalCount: intervals.length,
    crossHours: records.filter((row) => row.isCrossTrain).reduce((sum, row) => sum + row.minutes / 60, 0)
  };
}

function renderKpis(records, weeks) {
  const kpis = document.getElementById("kpis");
  clear(kpis);
  const summary = summarize(records, weeks);
  const cards = [
    {
      label: "Run volume",
      value: `${formatNumber(summary.runMiles, 1)} mi`,
      note: `${formatNumber(summary.lastFourAvg, 1)} mi/wk over last 4 weeks`
    },
    {
      label: "Easy HR discipline",
      value: summary.easyPct == null ? "-" : `${formatNumber(summary.easyPct, 0)}%`,
      note: `time below ${DATA.meta.easyHrDisplayThreshold} bpm on easy runs`
    },
    {
      label: "Best 5K trial",
      value: summary.bestTrial ? formatDuration(summary.bestTrial.fastest5kSec) : "-",
      note: summary.bestTrial ? formatDate(summary.bestTrial.date, { year: "numeric" }) : "no trials in range"
    },
    {
      label: "Latest 5K trial",
      value: summary.latestTrial ? formatDuration(summary.latestTrial.fastest5kSec) : "-",
      note: summary.latestTrial ? formatDate(summary.latestTrial.date, { year: "numeric" }) : "no trials in range"
    },
    {
      label: "Intervals",
      value: `${formatNumber(summary.intervalCount, 0)}`,
      note: "short, medium, and long sessions"
    },
    {
      label: "Cross-training",
      value: `${formatNumber(summary.crossHours, 1)} h`,
      note: "cycling, elliptical, swim, and rides"
    }
  ];

  cards.forEach((card) => {
    const el = document.createElement("article");
    el.className = "kpi";
    el.innerHTML = `
      <div class="kpi-label">${card.label}</div>
      <div class="kpi-value">${card.value}</div>
      <div class="kpi-note">${card.note}</div>
    `;
    kpis.appendChild(el);
  });
}

function renderWeeklyChart(weeks) {
  const container = document.getElementById("weeklyChart");
  if (!weeks.length) return addEmpty(container, "No weekly data");
  clear(container);

  const metricKey = getWeeklyMetric();
  const metric = WEEKLY_METRICS[metricKey];
  const svg = makeSvg(1040, 300);
  const plot = { x: 48, y: 24, w: 952, h: 218 };
  const values = weeks.map(metric.value);
  const maxValue = Math.max(1, ...values);
  const y = (value) => plot.y + plot.h - (value / maxValue) * plot.h;
  const slot = plot.w / weeks.length;
  const barW = Math.max(3, Math.min(14, slot * 0.58));

  const injuryStart = parseDate(DATA.meta.injuryStart).getTime();
  const returnStart = parseDate(DATA.meta.returnToIntervals).getTime();
  const first = parseDate(weeks[0].week).getTime();
  const last = parseDate(weeks[weeks.length - 1].week).getTime();
  const timeToX = (time) => plot.x + ((time - first) / Math.max(1, last - first)) * plot.w;
  const bandX = Math.max(plot.x, timeToX(injuryStart));
  const bandW = Math.max(0, Math.min(plot.x + plot.w, timeToX(returnStart)) - bandX);
  if (bandW > 0) {
    svg.appendChild(svgEl("rect", {
      x: bandX,
      y: plot.y,
      width: bandW,
      height: plot.h,
      fill: "#f7efe3",
      opacity: "0.75"
    }));
    addText(svg, "injury / rebuild", bandX + 8, plot.y + 16, "chart-label");
  }

  drawYGrid(svg, plot, niceTicks(0, maxValue, 5), y, metric.format);

  weeks.forEach((week, index) => {
    const value = values[index];
    const x = plot.x + index * slot + (slot - barW) / 2;
    const barY = y(value);
    const bar = svgEl("rect", {
      x,
      y: barY,
      width: barW,
      height: plot.y + plot.h - barY,
      rx: 2,
      fill: metric.color
    });
    const tooltip = `${formatDate(week.week)}: ${metric.tooltip(value, week)}, ${formatNumber(week.runMiles, 1)} run mi, ${formatNumber((week.runMinutes || 0) / 60, 1)} run h`;
    svg.appendChild(bar);
    addSvgHover(svg, bar, "rect", {
      x: plot.x + index * slot,
      y: plot.y,
      width: slot,
      height: plot.h
    }, tooltip);
  });

  [0, Math.floor(weeks.length / 3), Math.floor((weeks.length * 2) / 3), weeks.length - 1]
    .filter((value, index, list) => list.indexOf(value) === index)
    .forEach((index) => {
      const x = plot.x + index * slot + slot / 2;
      addText(svg, formatDate(weeks[index].week), x, plot.y + plot.h + 24, "chart-label", "middle");
    });

  addText(svg, metric.label, plot.x, 14, "chart-label");
  svg.appendChild(svgEl("line", { x1: plot.x, x2: plot.x + plot.w, y1: plot.y + plot.h, y2: plot.y + plot.h, class: "axis-line" }));
  addChartZoom(svg, plot, first, last + 6 * DAY_MS);
  container.appendChild(svg);
}

function renderRecoveryChart(weeks) {
  const container = document.getElementById("recoveryChart");
  const recoveryWeeks = weeks.filter((week) =>
    week.sleepHoursAvg != null || week.restingHrAvg != null || week.hrvAvg != null
  );
  if (!recoveryWeeks.length) return addEmpty(container, "No weekly recovery data");
  clear(container);

  const svg = makeSvg(1040, 390);
  const plot = { x: 70, y: 24, w: 920, h: 290 };
  const lanes = [
    {
      key: "sleepHoursAvg",
      label: "Sleep",
      unit: "h",
      color: COLORS.blue,
      y: plot.y,
      h: 82,
      format: (value) => `${formatNumber(value, 1)}h`
    },
    {
      key: "restingHrAvg",
      label: "Rest HR",
      unit: "bpm",
      color: COLORS.hard,
      y: plot.y + 104,
      h: 82,
      format: (value) => `${formatNumber(value, 0)}`
    },
    {
      key: "hrvAvg",
      label: "HRV",
      unit: "ms",
      color: COLORS.run,
      y: plot.y + 208,
      h: 82,
      format: (value) => `${formatNumber(value, 0)}`
    }
  ];

  const weekTimes = recoveryWeeks.map((week) => parseDate(week.week).getTime());
  const [first, last] = minMax(weekTimes);
  const x = (week) => plot.x + ((parseDate(week.week).getTime() - first) / Math.max(1, last - first)) * plot.w;

  lanes.forEach((lane) => {
    const values = recoveryWeeks.map((week) => week[lane.key]).filter((value) => value != null);
    const [minValue, maxValue] = minMax(values, lane.key === "sleepHoursAvg" ? 0.35 : 3);
    const y = (value) => lane.y + lane.h - ((value - minValue) / Math.max(0.1, maxValue - minValue)) * lane.h;

    svg.appendChild(svgEl("line", {
      x1: plot.x,
      x2: plot.x + plot.w,
      y1: lane.y + lane.h,
      y2: lane.y + lane.h,
      class: "axis-line"
    }));
    svg.appendChild(svgEl("line", {
      x1: plot.x,
      x2: plot.x + plot.w,
      y1: lane.y,
      y2: lane.y,
      class: "grid-line"
    }));
    addText(svg, lane.label, plot.x - 12, lane.y + 14, "chart-label", "end");
    addText(svg, lane.unit, plot.x - 12, lane.y + 30, "chart-label", "end");
    addText(svg, lane.format(maxValue), plot.x + plot.w + 8, lane.y + 5, "chart-label");
    addText(svg, lane.format(minValue), plot.x + plot.w + 8, lane.y + lane.h + 4, "chart-label");

    const rows = recoveryWeeks.filter((week) => week[lane.key] != null);
    const path = rows
      .map((week, index) => `${index ? "L" : "M"} ${x(week).toFixed(1)} ${y(week[lane.key]).toFixed(1)}`)
      .join(" ");
    if (rows.length > 1) {
      svg.appendChild(svgEl("path", {
        d: path,
        fill: "none",
        stroke: lane.color,
        "stroke-width": 2.5
      }));
    }
    rows.forEach((week) => {
      const cx = x(week);
      const cy = y(week[lane.key]);
      const dot = svgEl("circle", {
        cx,
        cy,
        r: 3.2,
        fill: lane.color
      });
      svg.appendChild(dot);
      addSvgHover(svg, dot, "circle", { cx, cy, r: 12 }, `${formatDate(week.week)} ${lane.label}: ${lane.format(week[lane.key])}`);
    });
  });

  [0, Math.floor(recoveryWeeks.length / 3), Math.floor((recoveryWeeks.length * 2) / 3), recoveryWeeks.length - 1]
    .filter((value, index, list) => list.indexOf(value) === index)
    .forEach((index) => {
      addText(svg, formatDate(recoveryWeeks[index].week), x(recoveryWeeks[index]), plot.y + plot.h + 28, "chart-label", "middle");
    });

  addChartZoom(svg, plot, first, last + 6 * DAY_MS);
  container.appendChild(svg);
}

function renderEasyChart(records) {
  const container = document.getElementById("easyChart");
  const easy = records.filter((row) => EASY_CATEGORIES.has(row.category) && row.avgHr);
  if (!easy.length) return addEmpty(container, "No easy sessions");
  clear(container);

  const svg = makeSvg(760, 300);
  const plot = { x: 48, y: 24, w: 660, h: 218 };
  const dates = easy.map((row) => parseDate(row.date).getTime());
  const [first, last] = minMax(dates);
  const [minHr, maxHr] = minMax(easy.map((row) => row.avgHr).concat([DATA.meta.easyHrDisplayThreshold]), 5);
  const x = (value) => plot.x + ((parseDate(value).getTime() - first) / Math.max(1, last - first)) * plot.w;
  const y = (value) => plot.y + plot.h - ((value - minHr) / Math.max(1, maxHr - minHr)) * plot.h;

  drawYGrid(svg, plot, niceTicks(minHr, maxHr, 5), y, (value) => formatNumber(value, 0));
  const thresholdY = y(DATA.meta.easyHrDisplayThreshold);
  svg.appendChild(svgEl("line", {
    x1: plot.x,
    x2: plot.x + plot.w,
    y1: thresholdY,
    y2: thresholdY,
    stroke: COLORS.hard,
    "stroke-width": 2,
    "stroke-dasharray": "6 5"
  }));
  addText(svg, `<${DATA.meta.easyHrDisplayThreshold} bpm`, plot.x + plot.w - 4, thresholdY - 6, "chart-label", "end");

  easy.forEach((row) => {
    const under = row.easyHrUnderPct == null ? 0 : row.easyHrUnderPct;
    const color = under >= 90 ? COLORS.easy : under >= 75 ? COLORS.cross : COLORS.hard;
    const cx = x(row.date);
    const cy = y(row.avgHr);
    const r = Math.max(3.5, Math.min(7, row.miles / 1.2));
    const circle = svgEl("circle", {
      cx,
      cy,
      r,
      fill: color,
      opacity: "0.9"
    });
    svg.appendChild(circle);
    addSvgHover(svg, circle, "circle", { cx, cy, r: Math.max(12, r + 6) }, `${formatDate(row.date)} ${row.name}: avg HR ${row.avgHr}, ${formatNumber(under, 0)}% under ceiling`);
  });

  [0, Math.floor(easy.length / 2), easy.length - 1]
    .filter((value, index, list) => list.indexOf(value) === index)
    .forEach((index) => addText(svg, formatDate(easy[index].date), x(easy[index].date), plot.y + plot.h + 24, "chart-label", "middle"));
  svg.appendChild(svgEl("line", { x1: plot.x, x2: plot.x + plot.w, y1: plot.y + plot.h, y2: plot.y + plot.h, class: "axis-line" }));
  addChartZoom(svg, plot, first, last);
  container.appendChild(svg);
}

function renderEasyPaceChart(records) {
  const container = document.getElementById("easyPaceChart");
  const mode = getEasyPaceMode();
  const easy = easyPaceRows(records, mode === "intensity");
  if (!easy.length) {
    return addEmpty(container, mode === "intensity" ? "No easy pace and HR data" : "No easy pace data");
  }
  clear(container);

  const model = mode === "intensity" ? buildEasyIntensityModel(records) : null;
  const points = easy
    .map((row) => {
      const observedPace = adjustedPaceForRow(row, row.paceSecPerMile);
      const intensity = easyRunIntensity(row);
      const value = mode === "intensity"
        ? intensityNormalizedEasyPace(row, model)
        : observedPace;
      return { row, observedPace, intensity, value };
    })
    .filter((point) => Number.isFinite(point.value));

  if (!points.length) {
    return addEmpty(container, mode === "intensity" ? "No easy pace and HR data" : "No easy pace data");
  }

  const svg = makeSvg(760, 330);
  const plot = { x: 58, y: 26, w: 644, h: 230 };
  const dates = points.map((point) => parseDate(point.row.date).getTime());
  const [first, last] = minMax(dates);
  const minPace = EASY_PACE_MIN_SEC;
  const maxPace = EASY_PACE_MAX_SEC;
  const x = (value) => plot.x + ((parseDate(value).getTime() - first) / Math.max(1, last - first)) * plot.w;
  const y = (value) => plot.y + ((value - minPace) / Math.max(1, maxPace - minPace)) * plot.h;
  const colors = {
    easy: COLORS.easy,
    easy_long: COLORS.blue
  };
  const rangeRows = rollingEasyPaceRange(points);
  const rangePath = (key) => rangeRows
    .map((row, index) => {
      const cx = x(row.date);
      const cy = clamp(y(row[key]), plot.y, plot.y + plot.h);
      return `${index ? "L" : "M"} ${cx.toFixed(1)} ${cy.toFixed(1)}`;
    })
    .join(" ");
  const latestRange = rangeRows.at(-1);

  drawYGrid(svg, plot, EASY_PACE_TICKS, y, formatPace);

  if (rangeRows.length) {
    const lowerPath = rangePath("lower");
    const upperPath = rangePath("upper");
    const rangeTooltip = latestRange
      ? `Current regular easy range: ${formatPace(latestRange.lower)}-${formatPace(latestRange.upper)} from last ${latestRange.count} regular easy runs`
      : "Regular easy range";
    const lowerLine = svgEl("path", {
      d: lowerPath,
      fill: "none",
      stroke: COLORS.run,
      "stroke-width": 2.2,
      "stroke-linecap": "round",
      "stroke-linejoin": "round"
    });
    const upperLine = svgEl("path", {
      d: upperPath,
      fill: "none",
      stroke: COLORS.run,
      "stroke-width": 2.2,
      "stroke-dasharray": "5 5",
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
      opacity: "0.82"
    });
    svg.appendChild(lowerLine);
    svg.appendChild(upperLine);
    addSvgHover(svg, lowerLine, "path", { d: lowerPath, fill: "none", "stroke-width": 16 }, rangeTooltip);
    addSvgHover(svg, upperLine, "path", { d: upperPath, fill: "none", "stroke-width": 16 }, rangeTooltip);
  }

  points.forEach((point) => {
    const { row, observedPace, intensity, value } = point;
    const cx = x(row.date);
    const offScale = value < minPace || value > maxPace;
    const cy = clamp(y(value), plot.y, plot.y + plot.h);
    const r = EASY_PACE_MARKER_RADIUS;
    const markerAttrs = {
      fill: colors[row.category] || COLORS.easy,
      opacity: row.easyHrUnderPct != null && row.easyHrUnderPct < 75 ? "0.64" : "0.9",
      ...(offScale ? { stroke: COLORS.text, "stroke-width": 1.2, "stroke-dasharray": "2 2" } : {})
    };
    const dot = isTrailRun(row)
      ? svgEl("path", { d: trianglePath(cx, cy, r), ...markerAttrs })
      : svgEl("circle", { cx, cy, r, ...markerAttrs });
    const under = row.easyHrUnderPct == null ? "-" : `${formatNumber(row.easyHrUnderPct, 0)}%`;
    const observedTitle = runPaceAdjustmentTitle(row, row.paceSecPerMile, observedPace);
    const scaleNote = offScale ? ", outside 7:00-10:00 axis" : "";
    const tooltip = mode === "intensity"
      ? `${formatDate(row.date)} ${row.name}: ${runSurfaceLabel(row)}, ${formatPace(value)} at ${formatNumber(model.targetIntensity * 100, 0)}% HRR equivalent${scaleNote}; observed ${observedTitle}, avg HR ${row.avgHr || "-"} (${formatNumber((intensity || 0) * 100, 0)}% HRR), ${under} under ceiling`
      : `${formatDate(row.date)} ${row.name}: ${runSurfaceLabel(row)}, ${observedTitle}${scaleNote}, ${formatNumber(row.miles, 2)} mi, avg HR ${row.avgHr || "-"}, ${under} under ceiling`;
    svg.appendChild(dot);
    addSvgHover(svg, dot, "circle", { cx, cy, r: Math.max(12, r + 6) }, tooltip);
  });

  [0, Math.floor(points.length / 2), points.length - 1]
    .filter((value, index, list) => list.indexOf(value) === index)
    .forEach((index) => addText(svg, formatDate(points[index].row.date), x(points[index].row.date), plot.y + plot.h + 24, "chart-label", "middle"));

  svg.appendChild(svgEl("circle", { cx: plot.x, cy: plot.y + plot.h + 42, r: 5, fill: COLORS.easy }));
  addText(svg, "Easy", plot.x + 10, plot.y + plot.h + 46, "chart-label");
  svg.appendChild(svgEl("circle", { cx: plot.x + 84, cy: plot.y + plot.h + 42, r: 5, fill: COLORS.blue }));
  addText(svg, "Easy Long", plot.x + 94, plot.y + plot.h + 46, "chart-label");
  svg.appendChild(svgEl("circle", { cx: plot.x + 212, cy: plot.y + plot.h + 42, r: 5, fill: COLORS.muted }));
  addText(svg, "Regular run", plot.x + 222, plot.y + plot.h + 46, "chart-label");
  svg.appendChild(svgEl("path", { d: trianglePath(plot.x + 352, plot.y + plot.h + 42, 6), fill: COLORS.muted }));
  addText(svg, "Trail run", plot.x + 363, plot.y + plot.h + 46, "chart-label");
  if (rangeRows.length) {
    svg.appendChild(svgEl("line", {
      x1: plot.x + 460,
      x2: plot.x + 486,
      y1: plot.y + plot.h + 42,
      y2: plot.y + plot.h + 42,
      stroke: COLORS.run,
      "stroke-width": 2.2,
      "stroke-dasharray": "5 5"
    }));
    addText(svg, "Regular range", plot.x + 494, plot.y + plot.h + 46, "chart-label");
  }
  if (latestRange) {
    addText(svg, `current ${formatPace(latestRange.lower)}-${formatPace(latestRange.upper)}`, plot.x, 14, "chart-label");
  }
  if (mode === "intensity") {
    addText(svg, `typical ${formatNumber(model.targetIntensity * 100, 0)}% HRR`, plot.x + plot.w, 14, "chart-label", "end");
  }
  const adjustmentLabels = activeAdjustmentLabels();
  if (adjustmentLabels.length) {
    addText(svg, `adjusted: ${adjustmentLabels.join(" + ")}`, plot.x + plot.w, mode === "intensity" ? 30 : 14, "chart-label", "end");
  }
  svg.appendChild(svgEl("line", { x1: plot.x, x2: plot.x + plot.w, y1: plot.y + plot.h, y2: plot.y + plot.h, class: "axis-line" }));
  addChartZoom(svg, plot, first, last);
  container.appendChild(svg);
}

function renderIntervalChart(records) {
  const container = document.getElementById("intervalChart");
  if (getIntervalPaceMode() === "intensity") {
    renderEfficiencyChart(records, container);
    return;
  }

  const intervals = records.filter((row) =>
    ["short_interval", "medium_interval", "long_interval"].includes(row.category) &&
    row.intervalPaceSecPerMile
  );
  if (!intervals.length) return addEmpty(container, "No interval sessions");
  clear(container);

  const svg = makeSvg(760, 330);
  const plot = { x: 58, y: 26, w: 644, h: 230 };
  const points = [];

  Object.keys(INTERVAL_COLORS).forEach((category) => {
    const rows = intervals.filter((row) => row.category === category);
    splitRowsByDateGap(rows).forEach((segment, segmentIndex) => {
      segment.forEach((row, index) => {
        const value = adjustedIntervalPace(row);
        const windowRows = segment.slice(Math.max(0, index - 4), index + 1);
        const rollingPaces = windowRows
          .map(adjustedIntervalPace)
          .filter((pace) => Number.isFinite(pace));
        if (!Number.isFinite(value) || !rollingPaces.length) return;
        points.push({
          row,
          category,
          segment: `${category}-${segmentIndex}`,
          date: row.date,
          value,
          rollingValue: mean(rollingPaces),
          count: rollingPaces.length
        });
      });
    });
  });
  if (!points.length) return addEmpty(container, "No interval sessions");

  const dates = points.map((row) => parseDate(row.date).getTime());
  const values = points
    .flatMap((row) => [row.value, row.rollingValue])
    .filter((value) => Number.isFinite(value));
  const [first, last] = minMax(dates);
  const [minPace, maxPace] = minMax(values, 20);
  const x = (value) => plot.x + ((parseDate(value).getTime() - first) / Math.max(1, last - first)) * plot.w;
  const y = (value) => plot.y + ((value - minPace) / Math.max(1, maxPace - minPace)) * plot.h;

  drawYGrid(svg, plot, niceTicks(minPace, maxPace, 5), y, formatPace);

  Object.entries(INTERVAL_COLORS).forEach(([category, color], legendIndex) => {
    const rows = points.filter((row) => row.category === category && row.value);
    [...new Set(rows.map((row) => row.segment))].forEach((segmentId) => {
      const segment = rows.filter((row) => row.segment === segmentId);
      const path = segment
        .filter((row) => Number.isFinite(row.rollingValue))
        .map((row, index) => `${index ? "L" : "M"} ${x(row.date).toFixed(1)} ${y(row.rollingValue).toFixed(1)}`)
        .join(" ");
      if (segment.length > 1) {
        svg.appendChild(svgEl("path", { d: path, fill: "none", stroke: color, "stroke-width": 2.5 }));
      }
    });
    rows.forEach((point) => {
      const row = point.row;
      const pace = point.value;
      const cx = x(row.date);
      const cy = y(pace);
      const dot = svgEl("circle", {
        cx,
        cy,
        r: 3.2,
        fill: color
      });
      svg.appendChild(dot);
      addSvgHover(svg, dot, "circle", { cx, cy, r: 12 }, `${formatDate(row.date)} ${row.categoryLabel}: ${paceAdjustmentTitle(row, pace)} across ${row.intervalCount || "-"} reps; rolling trend ${formatPace(point.rollingValue)} (${point.count} workouts)`);
    });

    const lx = plot.x + legendIndex * 150;
    svg.appendChild(svgEl("circle", { cx: lx, cy: plot.y + plot.h + 42, r: 5, fill: color }));
    addText(svg, DATA.labels[category], lx + 10, plot.y + plot.h + 46, "chart-label");
  });

  [0, Math.floor(intervals.length / 2), intervals.length - 1]
    .filter((value, index, list) => list.indexOf(value) === index)
    .forEach((index) => addText(svg, formatDate(intervals[index].date), x(intervals[index].date), plot.y + plot.h + 24, "chart-label", "middle"));
  const adjustmentLabels = activeAdjustmentLabels();
  if (adjustmentLabels.length) {
    addText(svg, `adjusted: ${adjustmentLabels.join(" + ")}`, plot.x + plot.w, 14, "chart-label", "end");
  }
  svg.appendChild(svgEl("line", { x1: plot.x, x2: plot.x + plot.w, y1: plot.y + plot.h, y2: plot.y + plot.h, class: "axis-line" }));
  addChartZoom(svg, plot, first, last);
  container.appendChild(svg);
}

function renderEfficiencyChart(records, container = document.getElementById("intervalChart")) {
  const intervals = intervalRows(records);
  if (!intervals.length) return addEmpty(container, "No interval pace and HR data");
  clear(container);

  const svg = makeSvg(760, 330);
  const plot = { x: 58, y: 26, w: 644, h: 230 };
  const points = [];
  const intensityModel = buildIntensityModel(intervals);

  Object.keys(INTERVAL_COLORS).forEach((category) => {
    const rows = intervals.filter((row) => row.category === category);
    splitRowsByDateGap(rows).forEach((segment, segmentIndex) => {
      segment.forEach((row, index) => {
        const value = intensityNormalizedPace(row, intensityModel);
        const windowRows = segment.slice(Math.max(0, index - 4), index + 1);
        const normalizedPaces = windowRows
          .map((windowRow) => intensityNormalizedPace(windowRow, intensityModel))
          .filter((value) => Number.isFinite(value));
        if (!Number.isFinite(value) || !normalizedPaces.length) return;
        const intensity = intervalIntensity(row);
        const targetIntensity = intensityModel.targets[category] ?? intensityModel.overallTarget;
        const beta = intensityModel.betas[category] ?? intensityModel.overallBeta;
        points.push({
          category,
          segment: `${category}-${segmentIndex}`,
          date: row.date,
          value,
          rollingValue: mean(normalizedPaces),
          count: normalizedPaces.length,
          intensity,
          targetIntensity,
          beta
        });
      });
    });
  });
  if (!points.length) return addEmpty(container, "No interval HR reserve data");

  const dates = points.map((row) => parseDate(row.date).getTime());
  const values = points
    .flatMap((row) => [row.value, row.rollingValue])
    .filter((value) => Number.isFinite(value));
  const [first, last] = minMax(dates);
  const [minValue, maxValue] = minMax(values, 12);
  const x = (value) => plot.x + ((parseDate(value).getTime() - first) / Math.max(1, last - first)) * plot.w;
  const y = (value) => plot.y + ((value - minValue) / Math.max(1, maxValue - minValue)) * plot.h;

  drawYGrid(svg, plot, niceTicks(minValue, maxValue, 5), y, formatPace);

  Object.entries(INTERVAL_COLORS).forEach(([category, color], legendIndex) => {
    const rows = points.filter((row) => row.category === category && row.value);
    [...new Set(rows.map((row) => row.segment))].forEach((segmentId) => {
      const segment = rows.filter((row) => row.segment === segmentId);
      const path = segment
        .filter((row) => Number.isFinite(row.rollingValue))
        .map((row, index) => `${index ? "L" : "M"} ${x(row.date).toFixed(1)} ${y(row.rollingValue).toFixed(1)}`)
        .join(" ");
      if (segment.length > 1) {
        svg.appendChild(svgEl("path", { d: path, fill: "none", stroke: color, "stroke-width": 2.5 }));
      }
    });
    rows.forEach((row) => {
      const cx = x(row.date);
      const cy = y(row.value);
      const dot = svgEl("circle", {
        cx,
        cy,
        r: 3.2,
        fill: color
      });
      svg.appendChild(dot);
      addSvgHover(svg, dot, "circle", { cx, cy, r: 12 }, `${formatDate(row.date)} ${DATA.labels[category]}: ${formatPace(row.value)} at ${formatNumber(row.targetIntensity * 100, 0)}% HRR equivalent; rolling trend ${formatPace(row.rollingValue)} (${row.count} workouts); observed ${formatNumber(row.intensity * 100, 0)}% HRR, beta ${formatNumber(row.beta, 2)}`);
    });

    const lx = plot.x + legendIndex * 150;
    svg.appendChild(svgEl("circle", { cx: lx, cy: plot.y + plot.h + 42, r: 5, fill: color }));
    addText(svg, DATA.labels[category], lx + 10, plot.y + plot.h + 46, "chart-label");
  });

  [0, Math.floor(intervals.length / 2), intervals.length - 1]
    .filter((value, index, list) => list.indexOf(value) === index)
    .forEach((index) => addText(svg, formatDate(intervals[index].date), x(intervals[index].date), plot.y + plot.h + 24, "chart-label", "middle"));
  const adjustmentLabels = activeAdjustmentLabels();
  addText(svg, "faster @ typical HRR", plot.x, 14, "chart-label");
  if (adjustmentLabels.length) {
    addText(svg, `adjusted: ${adjustmentLabels.join(" + ")}`, plot.x + plot.w, 14, "chart-label", "end");
  }
  svg.appendChild(svgEl("line", { x1: plot.x, x2: plot.x + plot.w, y1: plot.y + plot.h, y2: plot.y + plot.h, class: "axis-line" }));
  addChartZoom(svg, plot, first, last);
  container.appendChild(svg);
}

function addTrialLegendToggle(svg, seriesGroup, options) {
  const { key, label, x, y, width, color, dasharray, marker = "line" } = options;
  const toggle = svgEl("g", {
    class: "chart-legend-toggle",
    role: "button",
    tabindex: "0"
  });
  toggle.appendChild(svgEl("rect", {
    x: x - 6,
    y: y - 13,
    width,
    height: 24,
    rx: 3,
    class: "chart-legend-toggle-hit"
  }));

  if (marker === "dot") {
    toggle.appendChild(svgEl("circle", {
      cx: x,
      cy: y,
      r: 5,
      fill: color,
      class: "chart-legend-toggle-mark"
    }));
  } else {
    toggle.appendChild(svgEl("line", {
      x1: x,
      x2: x + 26,
      y1: y,
      y2: y,
      stroke: color,
      "stroke-width": 2.5,
      ...(dasharray ? { "stroke-dasharray": dasharray } : {}),
      class: "chart-legend-toggle-mark"
    }));
  }

  const labelX = marker === "dot" ? x + 10 : x + 34;
  addText(toggle, label, labelX, y + 4, "chart-label chart-legend-toggle-label");

  const sync = () => {
    const visible = trialSeriesVisibility[key];
    seriesGroup.style.display = visible ? "" : "none";
    toggle.classList.toggle("is-disabled", !visible);
    toggle.setAttribute("aria-pressed", String(visible));
    toggle.setAttribute("aria-label", `${visible ? "Hide" : "Show"} ${label}`);
  };
  const change = () => {
    trialSeriesVisibility[key] = !trialSeriesVisibility[key];
    hideChartTooltip();
    sync();
  };

  toggle.addEventListener("click", change);
  toggle.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    change();
  });
  sync();
  svg.appendChild(toggle);
}

function renderTrialChart(records) {
  const container = document.getElementById("trialChart");
  const trials = records.filter((row) => row.category === "5k_time_trial" && row.fastest5kSec);
  const trialPoints = trials
    .map((row) => ({ row, value: adjustedTrialTime(row) }))
    .filter((item) => item.value);
  const mode = getPredictionMode();
  const intervalPredictions = buildPredicted5kSeries(records, DATA.records, mode);
  const easyPredictions = buildEasyPredicted5kSeries(records, DATA.records, mode);
  if (!trialPoints.length && !intervalPredictions.length && !easyPredictions.length) {
    return addEmpty(container, "No 5K trials or predictions");
  }
  clear(container);

  const svg = makeSvg(760, 330);
  const plot = { x: 58, y: 26, w: 644, h: 230 };
  const dates = [
    ...trialPoints.map((item) => parseDate(item.row.date).getTime()),
    ...intervalPredictions.map((row) => parseDate(row.date).getTime()),
    ...easyPredictions.map((row) => parseDate(row.date).getTime())
  ];
  const [first, last] = minMax(dates);
  const [minTime, maxTime] = minMax([
    ...trialPoints.map((item) => item.value),
    ...intervalPredictions.map((row) => row.value),
    ...easyPredictions.map((row) => row.value)
  ], 20);
  const x = (value) => plot.x + ((parseDate(value).getTime() - first) / Math.max(1, last - first)) * plot.w;
  const y = (value) => plot.y + ((value - minTime) / Math.max(1, maxTime - minTime)) * plot.h;

  drawYGrid(svg, plot, niceTicks(minTime, maxTime, 5), y, formatDuration);

  const intervalGroup = svgEl("g", { "data-trial-series": "interval" });
  svg.appendChild(intervalGroup);
  splitRowsByDateGap(intervalPredictions).forEach((segment) => {
    const predictedPath = segment
      .map((row, index) => `${index ? "L" : "M"} ${x(row.date).toFixed(1)} ${y(row.value).toFixed(1)}`)
      .join(" ");
    if (segment.length > 1) {
      intervalGroup.appendChild(svgEl("path", {
        d: predictedPath,
        fill: "none",
        stroke: COLORS.blue,
        "stroke-width": 2.5,
        "stroke-dasharray": "7 5"
      }));
    }
  });
  intervalPredictions.forEach((row) => {
    const cx = x(row.date);
    const cy = y(row.value);
    const dot = svgEl("circle", {
      cx,
      cy,
      r: 3.2,
      fill: COLORS.blue,
      opacity: "0.72"
    });
    intervalGroup.appendChild(dot);
    addSvgHover(intervalGroup, dot, "circle", { cx, cy, r: 12 }, `${formatDate(row.date)} interval prediction (${predictionModeLabel(mode)}): ${formatDuration(row.value)} from ${row.sources}; calibrated from ${row.calibrationCount} trials (${formatNumber(row.calibrationRatio, 3)}x)`);
  });

  const easyGroup = svgEl("g", { "data-trial-series": "easy" });
  svg.appendChild(easyGroup);
  splitRowsByDateGap(easyPredictions, EASY_PACE_RANGE_GAP_DAYS).forEach((segment) => {
    const predictedPath = segment
      .map((row, index) => `${index ? "L" : "M"} ${x(row.date).toFixed(1)} ${y(row.value).toFixed(1)}`)
      .join(" ");
    if (segment.length > 1) {
      easyGroup.appendChild(svgEl("path", {
        d: predictedPath,
        fill: "none",
        stroke: COLORS.easy,
        "stroke-width": 2.5,
        "stroke-dasharray": "2 5",
        "stroke-linecap": "round"
      }));
    }
  });
  easyPredictions.forEach((row) => {
    const cx = x(row.date);
    const cy = y(row.value);
    const dot = svgEl("circle", {
      cx,
      cy,
      r: 2.6,
      fill: COLORS.easy,
      opacity: "0.64"
    });
    easyGroup.appendChild(dot);
    addSvgHover(easyGroup, dot, "circle", { cx, cy, r: 12 }, `${formatDate(row.date)} outdoor easy-speed prediction (${predictionModeLabel(mode)}): ${formatDuration(row.value)} from a ${formatPace(row.easyPaceSecPerMile)} rolling median across ${row.count} runs; calibrated from ${row.calibrationCount} trials (${formatNumber(row.calibrationRatio, 3)}x)`);
  });

  const actualGroup = svgEl("g", { "data-trial-series": "actual" });
  svg.appendChild(actualGroup);
  const path = trialPoints.map((item, index) => `${index ? "L" : "M"} ${x(item.row.date).toFixed(1)} ${y(item.value).toFixed(1)}`).join(" ");
  if (trialPoints.length > 1) {
    actualGroup.appendChild(svgEl("path", { d: path, fill: "none", stroke: COLORS.hard, "stroke-width": 2.5 }));
  }
  trialPoints.forEach(({ row, value }) => {
    const cx = x(row.date);
    const cy = y(value);
    const dot = svgEl("circle", { cx, cy, r: 3.2, fill: COLORS.hard });
    const sourceLabel = row.fastest5kSource === "fit_rolling_distance" ? "best rolling 5K" : "Garmin fastest 5K";
    const windowLabel = row.fastest5kStartOffsetSec != null && row.fastest5kEndOffsetSec != null
      ? ` (${formatDuration(row.fastest5kStartOffsetSec)}-${formatDuration(row.fastest5kEndOffsetSec)})`
      : "";
    actualGroup.appendChild(dot);
    addSvgHover(actualGroup, dot, "circle", { cx, cy, r: 12 }, `${formatDate(row.date, { year: "numeric" })}: ${adjustedTrialTitle(row, value)} ${sourceLabel}${windowLabel}`);
    addText(actualGroup, formatDuration(value), cx, cy - 10, "chart-label", "middle");
  });
  trialPoints.forEach(({ row }) => addText(svg, formatDate(row.date), x(row.date), plot.y + plot.h + 24, "chart-label", "middle"));
  const legendY = plot.y + plot.h + 42;
  addTrialLegendToggle(svg, actualGroup, {
    key: "actual",
    label: "Best rolling 5K",
    x: plot.x,
    y: legendY,
    width: 136,
    color: COLORS.hard,
    marker: "dot"
  });
  addTrialLegendToggle(svg, intervalGroup, {
    key: "interval",
    label: "Interval prediction",
    x: plot.x + 150,
    y: legendY,
    width: 174,
    color: COLORS.blue,
    dasharray: "7 5"
  });
  addTrialLegendToggle(svg, easyGroup, {
    key: "easy",
    label: "Easy-speed prediction",
    x: plot.x + 334,
    y: legendY,
    width: 194,
    color: COLORS.easy,
    dasharray: "2 5"
  });
  const adjustmentLabels = activeAdjustmentLabels();
  addText(svg, `${predictionModeLabel(mode)} predictions`, plot.x, 14, "chart-label");
  if (adjustmentLabels.length) {
    addText(svg, `adjusted: ${adjustmentLabels.join(" + ")}`, plot.x + plot.w, 14, "chart-label", "end");
  }
  svg.appendChild(svgEl("line", { x1: plot.x, x2: plot.x + plot.w, y1: plot.y + plot.h, y2: plot.y + plot.h, class: "axis-line" }));
  addChartZoom(svg, plot, first, last);
  container.appendChild(svg);
}

function renderIntervalTargets() {
  const container = document.getElementById("intervalTargets");
  if (!container) return;
  clear(container);

  const customWrap = document.getElementById("customTargetTimeWrap");
  if (customWrap) {
    customWrap.hidden = getTargetSource() !== "custom";
  }

  const basis = selectedTargetBasis();
  if (basis.error) {
    const empty = document.createElement("div");
    empty.className = "target-empty";
    empty.textContent = basis.error;
    container.appendChild(empty);
    return;
  }

  const targets = intervalTargetsFrom5k(basis.seconds);
  const targetConditions = getTargetConditions();
  const showAdjustedTargets = hasTargetConditions(targetConditions);
  const showElevationBasis = targetConditions.elevationGainFeet != null || targetConditions.elevationLossFeet != null;
  const adjustedBasis5k = showAdjustedTargets
    ? adjustedTargetRacePrediction({
      label: "5K",
      distanceMeters: FIVE_K_METERS,
      seconds: basis.seconds,
      paceSecPerMile: basis.seconds / FIVE_K_MILES
    }, targetConditions)
    : null;
  const mileageByTarget = latestIntervalMileageByTarget();
  const summary = document.createElement("div");
  summary.className = "target-summary";
  summary.innerHTML = `
    <div>
      <div class="target-summary-label">${basis.label}</div>
      <div class="target-summary-value">${basis.detail}</div>
    </div>
    <div>
      <div class="target-summary-label">VDOT</div>
      <div class="target-summary-value">${formatNumber(targets.vdot, 1)}</div>
    </div>
    ${adjustedBasis5k ? `
      <div>
        <div class="target-summary-label">Adjusted 5K</div>
        <div class="target-summary-value" title="${adjustedBasis5k.title}">${formatRaceTime(adjustedBasis5k.seconds)} (${formatSignedDuration(adjustedBasis5k.deltaSeconds)})</div>
      </div>
    ` : ""}
    ${showAdjustedTargets ? `
      <div>
        <div class="target-summary-label">Conditions</div>
        <div class="target-summary-value">${targetConditionsLabel(targetConditions)}</div>
      </div>
    ` : ""}
  `;

  const table = document.createElement("table");
  table.className = `target-table${showAdjustedTargets ? " has-adjusted-targets" : ""}${showElevationBasis ? " has-elevation-targets" : ""}`;
  table.innerHTML = `
    <thead>
      <tr>
        <th>Session</th>
        <th>Rep model</th>
        <th>FVDOT basis</th>
        <th>Target pace</th>
        ${showElevationBasis ? "<th>Basis mi</th>" : ""}
        ${showAdjustedTargets ? "<th>Adjusted pace</th><th>Change</th>" : ""}
      </tr>
    </thead>
    <tbody></tbody>
  `;

  const body = table.querySelector("tbody");
  targets.rows.forEach((row) => {
    const tr = document.createElement("tr");
    const mileageBasis = mileageByTarget[row.key];
    const adjustedPace = adjustedTargetPace(row.paceSecPerMile, targetConditions, mileageBasis);
    const delta = adjustedPace - row.paceSecPerMile;
    const adjustmentTitle = targetAdjustmentTitle(row.paceSecPerMile, targetConditions, mileageBasis);
    const mileageTitle = mileageBasis
      ? `${formatNumber(mileageBasis.miles, 2)} mi ${mileageBasis.source} from ${formatDate(mileageBasis.date)}: ${mileageBasis.name}`
      : "No recent matching interval workout found";
    tr.innerHTML = `
      <td>${row.label}</td>
      <td>${row.reps}</td>
      <td>${row.durationMin}-min race pace</td>
      <td>${formatPace(row.paceSecPerMile)}</td>
      ${showElevationBasis ? `<td title="${mileageTitle}">${mileageBasis ? `${formatNumber(mileageBasis.miles, 2)} mi` : "-"}</td>` : ""}
      ${showAdjustedTargets ? `
        <td title="${adjustmentTitle}">${formatPace(adjustedPace)}</td>
        <td title="${adjustmentTitle}">${formatSignedSecondsPerMile(delta)}</td>
      ` : ""}
    `;
    body.appendChild(tr);
  });

  const raceTable = document.createElement("table");
  raceTable.className = `target-table race-prediction-table${showAdjustedTargets ? " has-adjusted-races" : ""}`;
  raceTable.innerHTML = `
    <thead>
      <tr>
        <th>Race</th>
        <th>Predicted time</th>
        <th>Pace</th>
        ${showAdjustedTargets ? "<th>Adjusted time</th><th>Adjusted pace</th><th>Change</th>" : ""}
      </tr>
    </thead>
    <tbody></tbody>
  `;

  const raceBody = raceTable.querySelector("tbody");
  racePredictionsFromVdot(targets.vdot).forEach((race) => {
    const tr = document.createElement("tr");
    const adjustedRace = showAdjustedTargets
      ? adjustedTargetRacePrediction(race, targetConditions)
      : null;
    tr.innerHTML = `
      <td>${race.label}</td>
      <td>${formatRaceTime(race.seconds)}</td>
      <td>${formatPace(race.paceSecPerMile)}</td>
      ${adjustedRace ? `
        <td title="${adjustedRace.title}">${formatRaceTime(adjustedRace.seconds)}</td>
        <td title="${adjustedRace.title}">${formatPace(adjustedRace.paceSecPerMile)}</td>
        <td title="${adjustedRace.title}">${formatSignedDuration(adjustedRace.deltaSeconds)}</td>
      ` : ""}
    `;
    raceBody.appendChild(tr);
  });

  const customRaceRow = document.createElement("tr");
  customRaceRow.className = "custom-race-row";
  const customRaceCell = document.createElement("td");
  const customDistanceControl = document.createElement("label");
  customDistanceControl.className = "custom-race-distance-control";
  const customDistanceInput = document.createElement("input");
  customDistanceInput.type = "number";
  customDistanceInput.inputMode = "decimal";
  customDistanceInput.min = "0";
  customDistanceInput.step = "any";
  customDistanceInput.placeholder = "Distance";
  customDistanceInput.setAttribute("aria-label", "Custom race distance in miles");
  customDistanceInput.value = customRaceDistanceMiles;
  const customDistanceUnit = document.createElement("span");
  customDistanceUnit.textContent = "mi";
  customDistanceControl.append(customDistanceInput, customDistanceUnit);
  customRaceCell.appendChild(customDistanceControl);
  customRaceRow.appendChild(customRaceCell);

  const customValueCells = Array.from(
    { length: showAdjustedTargets ? 5 : 2 },
    () => {
      const cell = document.createElement("td");
      cell.textContent = "-";
      customRaceRow.appendChild(cell);
      return cell;
    }
  );

  const updateCustomRacePrediction = () => {
    customRaceDistanceMiles = customDistanceInput.value;
    const distanceMiles = Number(customRaceDistanceMiles);
    const hasDistance = customRaceDistanceMiles.trim() !== "";
    const isValid = hasDistance && Number.isFinite(distanceMiles) && distanceMiles > 0;
    customDistanceInput.setAttribute("aria-invalid", hasDistance && !isValid ? "true" : "false");

    if (!isValid) {
      customValueCells.forEach((cell) => {
        cell.textContent = "-";
        cell.removeAttribute("title");
      });
      return;
    }

    const race = racePredictionFromVdot({
      label: `${formatNumber(distanceMiles, 2)} mi`,
      distanceMeters: distanceMiles * METERS_PER_MILE
    }, targets.vdot);
    customValueCells[0].textContent = formatRaceTime(race.seconds);
    customValueCells[1].textContent = formatPace(race.paceSecPerMile);

    if (showAdjustedTargets) {
      const adjustedRace = adjustedTargetRacePrediction(race, targetConditions);
      customValueCells[2].textContent = formatRaceTime(adjustedRace.seconds);
      customValueCells[3].textContent = formatPace(adjustedRace.paceSecPerMile);
      customValueCells[4].textContent = formatSignedDuration(adjustedRace.deltaSeconds);
      customValueCells.slice(2).forEach((cell) => {
        cell.title = adjustedRace.title;
      });
    }
  };

  customDistanceInput.addEventListener("input", updateCustomRacePrediction);
  updateCustomRacePrediction();
  raceBody.appendChild(customRaceRow);

  container.appendChild(summary);
  container.appendChild(table);
  const heading = document.createElement("div");
  heading.className = "target-section-heading";
  heading.textContent = "Equivalent race predictions";
  container.appendChild(heading);
  container.appendChild(raceTable);
}

function renderRecentTable(records) {
  const container = document.getElementById("recentTable");
  clear(container);
  const selectedType = getRecentTypeFilter();
  const filtered = selectedType === "all"
    ? records
    : records.filter((row) => row.category === selectedType);
  const sorted = [...filtered].sort((a, b) => b.datetime.localeCompare(a.datetime));
  const totalPages = Math.max(1, Math.ceil(sorted.length / RECENT_PAGE_SIZE));
  recentPage = clamp(recentPage, 0, totalPages - 1);
  const startIndex = recentPage * RECENT_PAGE_SIZE;
  const recent = sorted.slice(startIndex, startIndex + RECENT_PAGE_SIZE);
  if (!recent.length) return addEmpty(container, selectedType === "all" ? "No sessions in range" : "No sessions match this filter");

  const table = document.createElement("table");
  table.className = "recent-table";
  table.innerHTML = `
    <thead>
      <tr>
        <th>Date</th>
        <th>Session</th>
        <th>Type</th>
        <th>Distance</th>
        <th>Pace</th>
        <th>Avg HR</th>
        <th>Easy HR</th>
        <th>Elev</th>
        <th>Temp</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;
  const body = table.querySelector("tbody");
  recent.forEach((row) => {
    const tr = document.createElement("tr");
    const isInterval = INTERVAL_CATEGORIES.has(row.category);
    const paceInfo = recentPaceInfo(row);
    const avgHr = isInterval && row.intervalAvgHr
      ? row.intervalAvgHr
      : row.avgHr;
    const easyHr = EASY_CATEGORIES.has(row.category) && row.easyHrUnderPct != null
      ? `${formatNumber(row.easyHrUnderPct, 0)}%`
      : "-";
    tr.innerHTML = `
      <td>${formatDate(row.date)}</td>
      <td class="session-name">${row.name}</td>
      <td><span class="tag ${row.category}">${row.categoryLabel}</span></td>
      <td>${row.miles ? `${formatNumber(row.miles, 2)} mi` : "-"}</td>
      <td title="${paceInfo.title}">${formatPace(paceInfo.pace)}</td>
      <td>${avgHr || "-"}</td>
      <td>${easyHr}</td>
      <td title="${elevationTitle(row)}">${formatElevation(row)}</td>
      <td title="${weatherTitle(row)}">${formatTemperature(row)}</td>
    `;
    body.appendChild(tr);
  });
  container.appendChild(table);

  const pager = document.createElement("div");
  pager.className = "pager";
  pager.innerHTML = `
    <button type="button" data-page="prev" ${recentPage === 0 ? "disabled" : ""}>Newer</button>
    <span>Showing ${formatNumber(startIndex + 1, 0)}-${formatNumber(startIndex + recent.length, 0)} of ${formatNumber(sorted.length, 0)} · Page ${formatNumber(recentPage + 1, 0)} of ${formatNumber(totalPages, 0)}</span>
    <button type="button" data-page="next" ${recentPage >= totalPages - 1 ? "disabled" : ""}>Older</button>
  `;
  pager.querySelector('[data-page="prev"]')?.addEventListener("click", () => {
    recentPage = Math.max(0, recentPage - 1);
    render();
  });
  pager.querySelector('[data-page="next"]')?.addEventListener("click", () => {
    recentPage = Math.min(totalPages - 1, recentPage + 1);
    render();
  });
  container.appendChild(pager);
}

function render() {
  hideChartTooltip();
  const { records, weeks } = rangeFiltered();
  renderKpis(records, weeks);
  renderWeeklyChart(weeks);
  renderRecoveryChart(weeks);
  renderEasyPaceChart(records);
  renderEasyChart(records);
  renderIntervalChart(records);
  renderTrialChart(records);
  renderIntervalTargets();
  renderRecentTable(records);
}

function setupPaceAdjustmentControls() {
  const allInput = document.querySelector('[data-adjust="all"]');
  const inputs = PACE_ADJUSTMENT_KEYS
    .map((key) => document.querySelector(`[data-adjust="${key}"]`))
    .filter(Boolean);

  const syncAllInput = () => {
    if (!allInput) return;
    const checkedCount = inputs.filter((input) => input.checked).length;
    allInput.checked = checkedCount === inputs.length;
    allInput.indeterminate = checkedCount > 0 && checkedCount < inputs.length;
  };

  if (allInput) {
    allInput.addEventListener("change", () => {
      inputs.forEach((input) => {
        input.checked = allInput.checked;
      });
      allInput.indeterminate = false;
      render();
    });
  }

  inputs.forEach((input) => {
    input.addEventListener("change", () => {
      syncAllInput();
      render();
    });
  });

  syncAllInput();
}

function setupWeeklyMetricControls() {
  document.querySelectorAll('input[name="weeklyMetric"]').forEach((input) => {
    input.addEventListener("change", render);
  });
}

function setupPredictionModeControls() {
  document.querySelectorAll('input[name="predictionMode"]').forEach((input) => {
    input.addEventListener("change", render);
  });
}

function setupIntervalPaceModeControls() {
  document.querySelectorAll('input[name="intervalPaceMode"]').forEach((input) => {
    input.addEventListener("change", render);
  });
}

function setupEasyPaceModeControls() {
  document.querySelectorAll('input[name="easyPaceMode"]').forEach((input) => {
    input.addEventListener("change", render);
  });
}

function setupIntervalTargetControls() {
  document.querySelectorAll('input[name="targetSource"]').forEach((input) => {
    input.addEventListener("change", render);
  });
  document.getElementById("customTargetTime")?.addEventListener("input", render);
  ["targetTemperatureF", "targetHumidityPct", "targetElevationGainFeet", "targetElevationLossFeet"].forEach((id) => {
    document.getElementById(id)?.addEventListener("input", render);
  });
}

function setupRefreshControl() {
  const button = document.getElementById("refreshButton");
  const status = document.getElementById("refreshStatus");
  const logPanel = document.getElementById("refreshLogPanel");
  const dismissLogButton = document.getElementById("refreshLogDismiss");
  const details = document.getElementById("refreshDetails");
  const log = document.getElementById("refreshLog");
  if (!button || !status || !logPanel || !dismissLogButton || !details || !log) return;

  let reloadWhenComplete = false;
  let pollTimer = null;
  let currentLogRun = null;
  let dismissedLogRun = null;
  try {
    dismissedLogRun = window.sessionStorage.getItem("dismissedRefreshLogRun");
  } catch (error) {
    dismissedLogRun = null;
  }

  const showServerRequired = () => {
    button.disabled = true;
    button.title = "Run dashboard_server.py and open its localhost URL to refresh data here.";
    status.textContent = "Local server required";
    logPanel.hidden = true;
  };

  const renderRefreshState = (state) => {
    const lines = Array.isArray(state.log) ? state.log : [];
    currentLogRun = state.startedAt || null;
    log.textContent = lines.join("\n");
    logPanel.hidden = !lines.length || (currentLogRun && currentLogRun === dismissedLogRun);
    button.disabled = Boolean(state.running);
    button.title = state.running ? "A dashboard update is already running." : "Run update_dashboard.py and reload the dashboard.";

    if (state.status === "running") {
      status.textContent = state.step || "Updating";
    } else if (state.status === "succeeded") {
      status.textContent = "Last update succeeded";
    } else if (state.status === "failed") {
      status.textContent = state.step || "Update failed";
      details.open = true;
    } else {
      status.textContent = "Ready";
    }
  };

  const fetchRefreshState = async () => {
    const response = await fetch("./api/refresh", {
      cache: "no-store",
      headers: { Accept: "application/json" }
    });
    if (!response.ok) throw new Error(`Refresh status returned ${response.status}`);
    return response.json();
  };

  const schedulePoll = () => {
    window.clearTimeout(pollTimer);
    pollTimer = window.setTimeout(pollRefreshState, REFRESH_POLL_MS);
  };

  const pollRefreshState = async () => {
    try {
      const state = await fetchRefreshState();
      renderRefreshState(state);
      if (state.running) {
        reloadWhenComplete = true;
        schedulePoll();
      } else if (reloadWhenComplete && state.status === "succeeded") {
        reloadWhenComplete = false;
        button.disabled = true;
        status.textContent = "Updated. Reloading…";
        window.setTimeout(() => window.location.reload(), 500);
      } else {
        reloadWhenComplete = false;
      }
    } catch (error) {
      reloadWhenComplete = false;
      showServerRequired();
    }
  };

  button.addEventListener("click", async () => {
    button.disabled = true;
    status.textContent = "Starting update…";
    details.open = false;
    logPanel.hidden = true;
    try {
      const response = await fetch("./api/refresh", {
        method: "POST",
        cache: "no-store",
        headers: {
          Accept: "application/json",
          "X-Garmin-Dashboard": "refresh"
        }
      });
      const state = await response.json();
      if (!response.ok && response.status !== 409) {
        throw new Error(state.error || `Refresh request returned ${response.status}`);
      }
      reloadWhenComplete = true;
      renderRefreshState(state);
      schedulePoll();
    } catch (error) {
      button.disabled = false;
      status.textContent = "Could not start update";
      log.textContent = error.message;
      currentLogRun = "client-error";
      logPanel.hidden = false;
      details.open = true;
    }
  });

  dismissLogButton.addEventListener("click", () => {
    dismissedLogRun = currentLogRun;
    logPanel.hidden = true;
    if (!dismissedLogRun) return;
    try {
      window.sessionStorage.setItem("dismissedRefreshLogRun", dismissedLogRun);
    } catch (error) {
      // The in-memory dismissal still works if storage is unavailable.
    }
  });

  if (window.location.protocol === "file:") {
    showServerRequired();
    return;
  }
  pollRefreshState();
}

function setupRecentTypeFilter() {
  const select = document.getElementById("recentTypeFilter");
  if (!select) return;

  const categories = new Set(DATA.records.map((row) => row.category));
  const ordered = Object.keys(DATA.labels).filter((category) => categories.has(category));
  [...categories]
    .filter((category) => !ordered.includes(category))
    .sort()
    .forEach((category) => ordered.push(category));

  select.replaceChildren();
  const allOption = document.createElement("option");
  allOption.value = "all";
  allOption.textContent = "All";
  select.appendChild(allOption);

  ordered.forEach((category) => {
    const option = document.createElement("option");
    option.value = category;
    option.textContent = DATA.labels[category] || category;
    select.appendChild(option);
  });

  select.addEventListener("change", resetRecentPageAndRender);
}

function setupRangeControls() {
  const rangeSelect = document.getElementById("rangeSelect");
  const customControls = document.getElementById("customRangeControls");
  const startInput = document.getElementById("customStartDate");
  const endInput = document.getElementById("customEndDate");
  const bounds = dataDateBounds();

  [startInput, endInput].forEach((input) => {
    if (!input) return;
    input.min = bounds.earliest;
    input.max = bounds.latest;
  });
  if (startInput && !startInput.value) startInput.value = bounds.earliest;
  if (endInput && !endInput.value) endInput.value = bounds.latest;

  const syncCustomControls = () => {
    if (!customControls) return;
    customControls.hidden = rangeSelect.value !== "custom";
  };

  rangeSelect.addEventListener("change", () => {
    syncCustomControls();
    resetRecentPageAndRender();
  });
  [startInput, endInput].forEach((input) => {
    input?.addEventListener("change", resetRecentPageAndRender);
  });

  syncCustomControls();
}

renderMeta();
setupRangeControls();
setupWeeklyMetricControls();
setupPredictionModeControls();
setupIntervalPaceModeControls();
setupEasyPaceModeControls();
setupIntervalTargetControls();
setupRefreshControl();
setupRecentTypeFilter();
setupPaceAdjustmentControls();
render();
