#!/usr/bin/env python3
"""Build local dashboard data from downloaded Garmin activity metadata."""

from __future__ import annotations

import json
import math
import os
import re
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import fitdecode


SOURCE_INDEX = Path("data/activities/activities-index.json")
HEALTH_SUMMARY = Path("data/health/daily-summary.json")
WEATHER_SUMMARY = Path("data/activity-weather/activity-weather-summary.json")
STATION_WEATHER_SUMMARY = Path("data/station-weather/activity-station-weather-summary.json")
ELEVATION_SUMMARY = Path("data/activity-elevation/activity-elevation-summary.json")
ORIGINAL_DIR = Path("data/activities/original")
DASHBOARD_DIR = Path("dashboard")
DATA_JS = DASHBOARD_DIR / "data.js"
FIT_CACHE_PATH = Path("data/activities/fit-cache.json")
FIT_CACHE_VERSION = 3

MAX_HR = 191
EASY_HR_THRESHOLD = MAX_HR * 0.70
EASY_LONG_MINUTES = 63
START_DATE = date(2025, 6, 1)
INJURY_START = date(2025, 12, 11)
RETURN_TO_INTERVALS = date(2026, 3, 30)

RUN_TYPES = {"running", "treadmill_running", "trail_running"}
OUTDOOR_ELEVATION_TYPES = {"running", "trail_running", "cycling", "mountain_biking", "hiking", "walking"}
CROSS_TRAIN_TYPES = {
    "cycling",
    "indoor_cycling",
    "virtual_ride",
    "elliptical",
    "lap_swimming",
    "mountain_biking",
}

CATEGORY_LABELS = {
    "easy": "Easy",
    "easy_long": "Easy Long",
    "short_interval": "Short intervals",
    "medium_interval": "Medium intervals",
    "long_interval": "Long intervals",
    "5k_time_trial": "5K time trial",
    "warmup": "Warmup",
    "rebuild_run": "Rebuild run",
    "cross_train": "Cross-train",
    "cross_interval": "Cross-train intervals",
    "strength": "Strength",
    "other_run": "Other run",
    "other": "Other",
}

EASY_CATEGORIES = {"easy", "easy_long"}


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def type_key(activity: dict[str, Any]) -> str:
    value = activity.get("activityType")
    if isinstance(value, dict):
        return str(value.get("typeKey") or "")
    return str(value or "")


def miles_from_meters(value: float | int | None) -> float:
    return float(value or 0) / 1609.344


def feet_from_meters(value: float | int | None) -> float:
    return float(value or 0) * 3.28084


def seconds(value: float | int | None) -> float | None:
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def is_run(activity_type: str) -> bool:
    return activity_type in RUN_TYPES


def is_cross_train(activity_type: str) -> bool:
    return activity_type in CROSS_TRAIN_TYPES


def classify(activity: dict[str, Any], local_date: date) -> str:
    name = str(activity.get("activityName") or "").lower()
    activity_type = type_key(activity)
    avg_hr = activity.get("averageHR")

    if "5k" in name and "time trial" in name:
        return "5k_time_trial"
    if "5k" in name and ("warm" in name or "warm-up" in name):
        return "warmup"
    if is_cross_train(activity_type):
        return "cross_interval" if "interval" in name else "cross_train"
    if "interval" in name and is_run(activity_type):
        if "short" in name:
            return "short_interval"
        if "medium" in name or "med" in name:
            return "medium_interval"
        if "long" in name:
            return "long_interval"
        return "other_run"
    if activity_type == "strength_training":
        return "strength"
    if is_run(activity_type):
        if any(token in name for token in ("easy", "recovery", "base")):
            return "easy"
        if INJURY_START <= local_date < RETURN_TO_INTERVALS:
            if avg_hr is not None and float(avg_hr) < EASY_HR_THRESHOLD:
                return "easy"
            return "rebuild_run"
        if avg_hr is not None and float(avg_hr) < EASY_HR_THRESHOLD:
            return "easy"
        return "other_run"
    return "other"


def activity_file_map() -> dict[str, Path]:
    files: dict[str, Path] = {}
    if not ORIGINAL_DIR.exists():
        return files
    for path in ORIGINAL_DIR.glob("*.zip"):
        match = re.search(r"_([0-9]+)\.zip$", path.name)
        if match:
            files[match.group(1)] = path
    return files


def load_health_days() -> dict[str, dict[str, Any]]:
    if not HEALTH_SUMMARY.exists():
        return {}
    try:
        payload = json.loads(HEALTH_SUMMARY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    days = payload.get("days")
    if not isinstance(days, list):
        return {}
    return {
        str(day["date"]): day
        for day in days
        if isinstance(day, dict) and day.get("date")
    }


def load_activity_weather() -> dict[str, dict[str, Any]]:
    if not WEATHER_SUMMARY.exists():
        return {}
    try:
        payload = json.loads(WEATHER_SUMMARY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    activities = payload.get("activities")
    if not isinstance(activities, list):
        return {}
    return {
        str(row["activityId"]): row
        for row in activities
        if isinstance(row, dict) and row.get("activityId")
    }


def load_station_weather() -> dict[str, dict[str, Any]]:
    if not STATION_WEATHER_SUMMARY.exists():
        return {}
    try:
        payload = json.loads(STATION_WEATHER_SUMMARY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    activities = payload.get("activities")
    if not isinstance(activities, list):
        return {}
    return {
        str(row["activityId"]): row
        for row in activities
        if isinstance(row, dict)
        and row.get("activityId")
        and row.get("status") == "ok"
    }


def load_activity_elevation() -> dict[str, dict[str, Any]]:
    if not ELEVATION_SUMMARY.exists():
        return {}
    try:
        payload = json.loads(ELEVATION_SUMMARY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    activities = payload.get("activities")
    if not isinstance(activities, list):
        return {}
    return {
        str(row["activityId"]): row
        for row in activities
        if isinstance(row, dict) and row.get("activityId") and row.get("status") == "ok"
    }


def load_fit_cache() -> dict[str, Any]:
    if not FIT_CACHE_PATH.exists():
        return {"version": FIT_CACHE_VERSION, "files": {}}
    try:
        cache = json.loads(FIT_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": FIT_CACHE_VERSION, "files": {}}
    if cache.get("version") != FIT_CACHE_VERSION or not isinstance(cache.get("files"), dict):
        return {"version": FIT_CACHE_VERSION, "files": {}}
    return cache


def save_fit_cache(cache: dict[str, Any]) -> None:
    FIT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = FIT_CACHE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(FIT_CACHE_PATH)


def cached_fit_metric(
    cache: dict[str, Any],
    activity_id: str,
    zip_path: Path,
    metric_name: str,
    compute: Any,
) -> Any:
    stat = zip_path.stat()
    signature = {
        "path": str(zip_path),
        "size": stat.st_size,
        "mtimeNs": stat.st_mtime_ns,
    }

    files = cache.setdefault("files", {})
    entry = files.get(activity_id)
    if (
        not isinstance(entry, dict)
        or entry.get("path") != signature["path"]
        or entry.get("size") != signature["size"]
        or entry.get("mtimeNs") != signature["mtimeNs"]
    ):
        entry = {**signature, "metrics": {}}
        files[activity_id] = entry

    metrics = entry.setdefault("metrics", {})
    if metric_name not in metrics:
        metrics[metric_name] = compute()
    return metrics[metric_name]


def fit_value(frame: fitdecode.FitDataMessage, field_name: str) -> Any:
    try:
        return frame.get_value(field_name)
    except Exception:
        return None


def hr_time_from_fit(zip_path: Path, threshold: float) -> dict[str, float] | None:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            fit_names = [name for name in archive.namelist() if name.lower().endswith(".fit")]
            if not fit_names:
                return None
            with archive.open(fit_names[0]) as fit_file:
                samples: list[tuple[datetime, float]] = []
                for frame in fitdecode.FitReader(fit_file):
                    if not isinstance(frame, fitdecode.FitDataMessage) or frame.name != "record":
                        continue
                    timestamp = fit_value(frame, "timestamp")
                    heart_rate = fit_value(frame, "heart_rate")
                    if timestamp is None or heart_rate is None:
                        continue
                    try:
                        samples.append((timestamp, float(heart_rate)))
                    except (TypeError, ValueError):
                        continue

        if len(samples) < 2:
            return None

        total = 0.0
        under = 0.0
        over = 0.0
        hr_weighted = 0.0

        for (timestamp, heart_rate), (next_timestamp, _) in zip(samples, samples[1:]):
            delta = (next_timestamp - timestamp).total_seconds()
            if delta <= 0:
                continue
            # FIT files are usually second-by-second. Capping avoids paused gaps
            # from dominating HR-zone time when records are sparse.
            delta = min(delta, 10.0)
            total += delta
            hr_weighted += heart_rate * delta
            if heart_rate < threshold:
                under += delta
            else:
                over += delta

        if total <= 0:
            return None

        return {
            "totalSec": total,
            "underSec": under,
            "overSec": over,
            "underPct": under / total * 100.0,
            "fitAvgHr": hr_weighted / total,
        }
    except Exception:
        return None


def best_rolling_distance_from_fit(
    zip_path: Path, target_distance_meters: float
) -> dict[str, Any] | None:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            fit_names = [name for name in archive.namelist() if name.lower().endswith(".fit")]
            if not fit_names:
                return None

            samples: list[tuple[datetime, float]] = []
            with archive.open(fit_names[0]) as fit_file:
                for frame in fitdecode.FitReader(fit_file):
                    if not isinstance(frame, fitdecode.FitDataMessage) or frame.name != "record":
                        continue
                    timestamp = fit_value(frame, "timestamp")
                    distance = fit_value(frame, "distance")
                    if timestamp is None or distance is None:
                        continue
                    try:
                        distance_float = float(distance)
                    except (TypeError, ValueError):
                        continue
                    if not samples or distance_float >= samples[-1][1]:
                        samples.append((timestamp, distance_float))

        if len(samples) < 2 or samples[-1][1] < target_distance_meters:
            return None

        def interpolated_time(target_distance: float) -> datetime | None:
            low = 0
            high = len(samples) - 1
            while low < high:
                middle = (low + high) // 2
                if samples[middle][1] < target_distance:
                    low = middle + 1
                else:
                    high = middle

            index = low
            timestamp, distance = samples[index]
            if distance == target_distance or index == 0:
                return timestamp

            previous_timestamp, previous_distance = samples[index - 1]
            distance_delta = distance - previous_distance
            if distance_delta <= 0:
                return timestamp

            fraction = (target_distance - previous_distance) / distance_delta
            elapsed = (timestamp - previous_timestamp).total_seconds()
            return previous_timestamp + timedelta(seconds=elapsed * fraction)

        best: dict[str, Any] | None = None
        for start_time, start_distance in samples:
            end_distance = start_distance + target_distance_meters
            if end_distance > samples[-1][1]:
                break
            end_time = interpolated_time(end_distance)
            if end_time is None:
                continue
            duration = (end_time - start_time).total_seconds()
            if duration <= 0:
                continue
            if best is None or duration < best["durationSec"]:
                best = {
                    "durationSec": duration,
                    "distanceMeters": target_distance_meters,
                    "startOffsetSec": (start_time - samples[0][0]).total_seconds(),
                    "endOffsetSec": (end_time - samples[0][0]).total_seconds(),
                    "startDistanceMeters": start_distance,
                    "endDistanceMeters": end_distance,
                    "source": "fit_rolling_distance",
                }

        return best
    except Exception:
        return None


def interval_pace_from_split_summaries(activity: dict[str, Any]) -> dict[str, float] | None:
    summaries = activity.get("splitSummaries") or []
    active = [
        split
        for split in summaries
        if split.get("splitType") == "INTERVAL_ACTIVE"
        and float(split.get("distance") or 0) > 0
        and float(split.get("duration") or 0) > 0
    ]
    if not active:
        return None

    distance = sum(float(split.get("distance") or 0) for split in active)
    duration = sum(float(split.get("duration") or 0) for split in active)
    count = sum(int(split.get("noOfSplits") or 0) for split in active)
    if distance <= 0 or duration <= 0:
        return None

    return {
        "distanceMeters": distance,
        "durationSec": duration,
        "count": count or len(active),
        "source": "split_summary",
    }


def interval_laps_from_fit(zip_path: Path) -> dict[str, float] | None:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            fit_names = [name for name in archive.namelist() if name.lower().endswith(".fit")]
            if not fit_names:
                return None

            distance = 0.0
            duration = 0.0
            count = 0
            hr_weighted = 0.0
            hr_duration = 0.0
            ascent = 0.0
            descent = 0.0
            with archive.open(fit_names[0]) as fit_file:
                for frame in fitdecode.FitReader(fit_file):
                    if not isinstance(frame, fitdecode.FitDataMessage) or frame.name != "lap":
                        continue
                    if str(fit_value(frame, "intensity")).lower() != "active":
                        continue
                    lap_distance = float(fit_value(frame, "total_distance") or 0)
                    lap_duration = float(fit_value(frame, "total_timer_time") or 0)
                    if lap_distance <= 0 or lap_duration <= 0:
                        continue
                    distance += lap_distance
                    duration += lap_duration
                    count += 1
                    ascent += float(fit_value(frame, "total_ascent") or 0)
                    descent += float(fit_value(frame, "total_descent") or 0)
                    lap_hr = fit_value(frame, "avg_heart_rate")
                    if lap_hr is not None:
                        try:
                            hr_weighted += float(lap_hr) * lap_duration
                            hr_duration += lap_duration
                        except (TypeError, ValueError):
                            pass

        if distance <= 0 or duration <= 0:
            return None

        return {
            "distanceMeters": distance,
            "durationSec": duration,
            "count": count,
            "avgHr": hr_weighted / hr_duration if hr_duration > 0 else None,
            "ascentMeters": ascent,
            "descentMeters": descent,
            "source": "fit_laps",
        }
    except Exception:
        return None


def week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


def round_or_none(value: float | None, digits: int = 1) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def weather_source_label(station_fields: list[str], garmin_fields: list[str], station_weather: dict[str, Any]) -> str | None:
    if station_fields and garmin_fields:
        return f"{station_weather.get('source') or 'station'}+garmin"
    if station_fields:
        return station_weather.get("source") or "station"
    if garmin_fields:
        return "garmin"
    return None


def merged_weather(
    garmin_weather: dict[str, Any],
    station_weather: dict[str, Any],
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    station_fields: list[str] = []
    garmin_fields: list[str] = []
    for key in ("temperature", "apparentTemperature", "dewPoint", "humidity"):
        if station_weather.get(key) is not None:
            values[key] = station_weather.get(key)
            station_fields.append(key)
        elif garmin_weather.get(key) is not None:
            values[key] = garmin_weather.get(key)
            garmin_fields.append(key)
        else:
            values[key] = None

    using_station = bool(station_fields)
    values.update(
        {
            "weatherDescription": garmin_weather.get("weatherDescription"),
            "weatherStation": station_weather.get("stationName")
            if using_station
            else garmin_weather.get("weatherStation"),
            "weatherSource": weather_source_label(station_fields, garmin_fields, station_weather),
            "weatherStationId": station_weather.get("station") if using_station else None,
            "weatherStationRoute": station_weather.get("stationRoute") if using_station else None,
            "weatherStationDistanceMiles": station_weather.get("stationDistanceMiles")
            if using_station
            else None,
            "weatherObservationTime": station_weather.get("observationTimeUtc")
            if using_station
            else None,
            "weatherObservationOffsetMinutes": station_weather.get("observationOffsetMinutes")
            if using_station
            else None,
        }
    )
    return values


def build_records(
    activities: list[dict[str, Any]],
    fit_cache: dict[str, Any],
    weather_by_activity: dict[str, dict[str, Any]],
    station_weather_by_activity: dict[str, dict[str, Any]],
    elevation_by_activity: dict[str, dict[str, Any]],
    health_days: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    files = activity_file_map()
    records: list[dict[str, Any]] = []

    for activity in activities:
        local_dt = parse_dt(activity.get("startTimeLocal"))
        if local_dt is None or local_dt.date() < START_DATE:
            continue

        activity_type = type_key(activity)
        local_date = local_dt.date()
        category = classify(activity, local_date)
        activity_id = str(activity.get("activityId") or activity.get("id") or "")
        weather = merged_weather(
            weather_by_activity.get(activity_id, {}),
            station_weather_by_activity.get(activity_id, {}),
        )
        health = health_days.get(local_date.isoformat(), {})
        elevation = (
            elevation_by_activity.get(activity_id, {})
            if activity_type in OUTDOOR_ELEVATION_TYPES
            else {}
        )

        distance_miles = miles_from_meters(activity.get("distance"))
        elevation_gain_m = (
            elevation.get("elevationGainMeters")
            if elevation.get("elevationGainMeters") is not None
            else activity.get("elevationGain")
        )
        elevation_loss_m = (
            elevation.get("elevationLossMeters")
            if elevation.get("elevationLossMeters") is not None
            else activity.get("elevationLoss")
        )
        elevation_source = (
            f"{elevation.get('source')}:{elevation.get('dataset')}"
            if elevation.get("source") and elevation.get("dataset")
            else ("garmin" if elevation_gain_m is not None or elevation_loss_m is not None else None)
        )
        duration_sec = seconds(activity.get("movingDuration")) or seconds(activity.get("duration")) or 0
        if category == "easy" and duration_sec > EASY_LONG_MINUTES * 60:
            category = "easy_long"
        pace_sec_per_mile = duration_sec / distance_miles if distance_miles > 0 else None
        garmin_fastest_5k = seconds(activity.get("fastestSplit_5000"))
        fit_rolling_5k = None
        if category == "5k_time_trial" and activity_id in files:
            fit_rolling_5k = cached_fit_metric(
                fit_cache,
                activity_id,
                files[activity_id],
                "best_rolling_5000m_v1",
                lambda path=files[activity_id]: best_rolling_distance_from_fit(path, 5000.0),
            )
        fastest_5k = (
            seconds(fit_rolling_5k.get("durationSec"))
            if fit_rolling_5k
            else garmin_fastest_5k
        )
        fastest_5k_pace = fastest_5k / 3.106855 if fastest_5k else None
        avg_hr = activity.get("averageHR")
        max_hr = activity.get("maxHR")
        interval_summary = None
        interval_laps = None
        if category in {"short_interval", "medium_interval", "long_interval"}:
            interval_summary = interval_pace_from_split_summaries(activity)
            if activity_id in files:
                interval_laps = cached_fit_metric(
                    fit_cache,
                    activity_id,
                    files[activity_id],
                    "interval_active_laps_v2",
                    lambda path=files[activity_id]: interval_laps_from_fit(path),
                )
            if interval_summary is None:
                interval_summary = interval_laps

        interval_distance_miles = (
            miles_from_meters(interval_summary["distanceMeters"]) if interval_summary else None
        )
        interval_duration_sec = interval_summary["durationSec"] if interval_summary else None
        interval_avg_hr = interval_laps.get("avgHr") if interval_laps else None
        interval_pace = (
            interval_duration_sec / interval_distance_miles
            if interval_duration_sec and interval_distance_miles and interval_distance_miles > 0
            else None
        )
        interval_ascent_m = (
            elevation.get("intervalElevationGainMeters")
            if elevation.get("intervalElevationGainMeters") is not None
            else (interval_laps.get("ascentMeters") if interval_laps else None)
        )
        interval_descent_m = (
            elevation.get("intervalElevationLossMeters")
            if elevation.get("intervalElevationLossMeters") is not None
            else (interval_laps.get("descentMeters") if interval_laps else None)
        )
        interval_elevation_source = (
            elevation_source
            if elevation.get("intervalElevationGainMeters") is not None
            or elevation.get("intervalElevationLossMeters") is not None
            else (interval_laps["source"] if interval_laps else None)
        )

        hr_summary = None
        if category in EASY_CATEGORIES and activity_id in files:
            hr_summary = cached_fit_metric(
                fit_cache,
                activity_id,
                files[activity_id],
                f"easy_hr_under_{EASY_HR_THRESHOLD:.1f}",
                lambda path=files[activity_id]: hr_time_from_fit(
                    path, EASY_HR_THRESHOLD
                ),
            )

        if hr_summary:
            hr_under_pct = hr_summary["underPct"]
            hr_over_min = hr_summary["overSec"] / 60
            hr_total_min = hr_summary["totalSec"] / 60
            hr_source = "fit"
        elif category in EASY_CATEGORIES and avg_hr is not None:
            hr_under_pct = 100.0 if float(avg_hr) < EASY_HR_THRESHOLD else 0.0
            hr_over_min = 0.0 if float(avg_hr) < EASY_HR_THRESHOLD else duration_sec / 60
            hr_total_min = duration_sec / 60
            hr_source = "average"
        else:
            hr_under_pct = None
            hr_over_min = None
            hr_total_min = None
            hr_source = None

        records.append(
            {
                "id": activity_id,
                "date": local_date.isoformat(),
                "datetime": local_dt.isoformat(timespec="seconds"),
                "name": activity.get("activityName") or "Activity",
                "type": activity_type,
                "category": category,
                "categoryLabel": CATEGORY_LABELS.get(category, category),
                "isRun": is_run(activity_type),
                "isCrossTrain": is_cross_train(activity_type),
                "miles": round(distance_miles, 2),
                "elevationGainMeters": round_or_none(float(elevation_gain_m), 1)
                if elevation_gain_m is not None
                else None,
                "elevationGainFeet": round_or_none(feet_from_meters(elevation_gain_m), 0)
                if elevation_gain_m is not None
                else None,
                "elevationLossMeters": round_or_none(float(elevation_loss_m), 1)
                if elevation_loss_m is not None
                else None,
                "elevationLossFeet": round_or_none(feet_from_meters(elevation_loss_m), 0)
                if elevation_loss_m is not None
                else None,
                "elevationSource": elevation_source,
                "elevationSampleCount": elevation.get("sampleCount"),
                "minutes": round(duration_sec / 60, 1),
                "paceSecPerMile": round_or_none(pace_sec_per_mile, 1),
                "avgHr": round_or_none(float(avg_hr), 0) if avg_hr is not None else None,
                "maxHr": round_or_none(float(max_hr), 0) if max_hr is not None else None,
                "restingHr": round_or_none(float(health["restingHeartRate"]), 0)
                if health.get("restingHeartRate") is not None
                else None,
                "trainingLoad": round_or_none(float(activity.get("activityTrainingLoad")), 1)
                if activity.get("activityTrainingLoad") is not None
                else None,
                "fastest5kSec": round_or_none(fastest_5k, 1),
                "fastest5kPaceSecPerMile": round_or_none(fastest_5k_pace, 1),
                "garminFastest5kSec": round_or_none(garmin_fastest_5k, 1),
                "fastest5kSource": fit_rolling_5k["source"]
                if fit_rolling_5k
                else ("garmin_fastest_split" if garmin_fastest_5k else None),
                "fastest5kStartOffsetSec": round_or_none(
                    fit_rolling_5k.get("startOffsetSec"), 1
                )
                if fit_rolling_5k
                else None,
                "fastest5kEndOffsetSec": round_or_none(fit_rolling_5k.get("endOffsetSec"), 1)
                if fit_rolling_5k
                else None,
                "intervalPaceSecPerMile": round_or_none(interval_pace, 1),
                "intervalDistanceMiles": round_or_none(interval_distance_miles, 2),
                "intervalMinutes": round_or_none(interval_duration_sec / 60, 1)
                if interval_duration_sec
                else None,
                "intervalCount": interval_summary["count"] if interval_summary else None,
                "intervalPaceSource": interval_summary["source"] if interval_summary else None,
                "intervalAvgHr": round_or_none(interval_avg_hr, 0),
                "intervalHrSource": interval_laps["source"] if interval_laps else None,
                "intervalAscentFeet": round_or_none(
                    feet_from_meters(interval_ascent_m), 0
                )
                if interval_ascent_m is not None
                else None,
                "intervalDescentFeet": round_or_none(
                    feet_from_meters(interval_descent_m), 0
                )
                if interval_descent_m is not None
                else None,
                "intervalElevationSource": interval_elevation_source,
                "temperatureF": round_or_none(float(weather["temperature"]), 0)
                if weather.get("temperature") is not None
                else None,
                "apparentTemperatureF": round_or_none(float(weather["apparentTemperature"]), 0)
                if weather.get("apparentTemperature") is not None
                else None,
                "dewPointF": round_or_none(float(weather["dewPoint"]), 0)
                if weather.get("dewPoint") is not None
                else None,
                "humidity": round_or_none(float(weather["humidity"]), 0)
                if weather.get("humidity") is not None
                else None,
                "weatherDescription": weather.get("weatherDescription"),
                "weatherStation": weather.get("weatherStation"),
                "weatherSource": weather.get("weatherSource"),
                "weatherStationId": weather.get("weatherStationId"),
                "weatherStationRoute": weather.get("weatherStationRoute"),
                "weatherStationDistanceMiles": round_or_none(
                    float(weather["weatherStationDistanceMiles"]), 1
                )
                if weather.get("weatherStationDistanceMiles") is not None
                else None,
                "weatherObservationTime": weather.get("weatherObservationTime"),
                "weatherObservationOffsetMinutes": round_or_none(
                    float(weather["weatherObservationOffsetMinutes"]), 1
                )
                if weather.get("weatherObservationOffsetMinutes") is not None
                else None,
                "easyHrUnderPct": round_or_none(hr_under_pct, 1),
                "easyHrOverMin": round_or_none(hr_over_min, 1),
                "easyHrTotalMin": round_or_none(hr_total_min, 1),
                "easyHrSource": hr_source,
            }
        )

    return sorted(records, key=lambda row: row["datetime"])


def build_weeks(
    records: list[dict[str, Any]], health_days: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    if not records and not health_days:
        return []

    first_week = week_start(START_DATE)
    record_dates = [datetime.fromisoformat(row["datetime"]).date() for row in records]
    health_dates = [
        date.fromisoformat(day)
        for day in health_days
        if day >= START_DATE.isoformat()
    ]
    last_date = max(record_dates + health_dates)
    last_week = week_start(last_date)

    buckets: dict[date, dict[str, Any]] = defaultdict(
        lambda: {
            "runMiles": 0.0,
            "easyMiles": 0.0,
            "totalMinutes": 0.0,
            "qualitySessions": 0,
            "intervalSessions": 0,
            "intervalMinutes": 0.0,
            "timeTrials": 0,
            "crossTrainHours": 0.0,
            "strengthSessions": 0,
            "runMinutes": 0.0,
            "trainingLoad": 0.0,
            "easyHrWeightedPct": 0.0,
            "easyHrWeight": 0.0,
            "easyAvgHrWeighted": 0.0,
            "easyAvgHrWeight": 0.0,
            "sleepHoursTotal": 0.0,
            "sleepHoursDays": 0,
            "sleepScoreTotal": 0.0,
            "sleepScoreDays": 0,
            "restingHrTotal": 0.0,
            "restingHrDays": 0,
            "hrvTotal": 0.0,
            "hrvDays": 0,
        }
    )

    for row in records:
        row_date = datetime.fromisoformat(row["datetime"]).date()
        bucket = buckets[week_start(row_date)]
        category = row["category"]

        bucket["totalMinutes"] += row["minutes"]
        if row["trainingLoad"] is not None:
            bucket["trainingLoad"] += row["trainingLoad"]
        if row["isRun"]:
            bucket["runMiles"] += row["miles"]
            bucket["runMinutes"] += row["minutes"]
        if category in EASY_CATEGORIES:
            bucket["easyMiles"] += row["miles"]
            if row["easyHrUnderPct"] is not None:
                weight = row["easyHrTotalMin"] or row["minutes"] or 1
                bucket["easyHrWeightedPct"] += row["easyHrUnderPct"] * weight
                bucket["easyHrWeight"] += weight
            if row["avgHr"] is not None:
                weight = row["minutes"] or 1
                bucket["easyAvgHrWeighted"] += row["avgHr"] * weight
                bucket["easyAvgHrWeight"] += weight
        if category in {"short_interval", "medium_interval", "long_interval", "5k_time_trial"}:
            bucket["qualitySessions"] += 1
        if category in {"short_interval", "medium_interval", "long_interval"}:
            bucket["intervalSessions"] += 1
            bucket["intervalMinutes"] += row["intervalMinutes"] or 0
        if category == "5k_time_trial":
            bucket["timeTrials"] += 1
        if row["isCrossTrain"]:
            bucket["crossTrainHours"] += row["minutes"] / 60
        if category == "strength":
            bucket["strengthSessions"] += 1

    for day, health in health_days.items():
        health_date = date.fromisoformat(day)
        if health_date < START_DATE:
            continue
        bucket = buckets[week_start(health_date)]

        if health.get("sleepHours") is not None:
            bucket["sleepHoursTotal"] += float(health["sleepHours"])
            bucket["sleepHoursDays"] += 1
        if health.get("sleepScore") is not None:
            bucket["sleepScoreTotal"] += float(health["sleepScore"])
            bucket["sleepScoreDays"] += 1
        if health.get("restingHeartRate") is not None:
            bucket["restingHrTotal"] += float(health["restingHeartRate"])
            bucket["restingHrDays"] += 1
        if health.get("hrvLastNightAvg") is not None:
            bucket["hrvTotal"] += float(health["hrvLastNightAvg"])
            bucket["hrvDays"] += 1

    weeks: list[dict[str, Any]] = []
    cursor = first_week
    while cursor <= last_week:
        bucket = buckets[cursor]
        easy_hr_pct = (
            bucket["easyHrWeightedPct"] / bucket["easyHrWeight"]
            if bucket["easyHrWeight"]
            else None
        )
        easy_avg_hr = (
            bucket["easyAvgHrWeighted"] / bucket["easyAvgHrWeight"]
            if bucket["easyAvgHrWeight"]
            else None
        )
        weeks.append(
            {
                "week": cursor.isoformat(),
                "runMiles": round(bucket["runMiles"], 1),
                "easyMiles": round(bucket["easyMiles"], 1),
                "totalMinutes": round(bucket["totalMinutes"], 1),
                "runMinutes": round(bucket["runMinutes"], 1),
                "trainingLoad": round(bucket["trainingLoad"], 1),
                "qualitySessions": bucket["qualitySessions"],
                "intervalSessions": bucket["intervalSessions"],
                "intervalMinutes": round(bucket["intervalMinutes"], 1),
                "timeTrials": bucket["timeTrials"],
                "crossTrainHours": round(bucket["crossTrainHours"], 1),
                "strengthSessions": bucket["strengthSessions"],
                "easyHrUnderPct": round_or_none(easy_hr_pct, 1),
                "easyAvgHr": round_or_none(easy_avg_hr, 0),
                "sleepHoursAvg": round_or_none(
                    bucket["sleepHoursTotal"] / bucket["sleepHoursDays"], 2
                )
                if bucket["sleepHoursDays"]
                else None,
                "sleepDays": bucket["sleepHoursDays"],
                "sleepScoreAvg": round_or_none(
                    bucket["sleepScoreTotal"] / bucket["sleepScoreDays"], 0
                )
                if bucket["sleepScoreDays"]
                else None,
                "restingHrAvg": round_or_none(
                    bucket["restingHrTotal"] / bucket["restingHrDays"], 0
                )
                if bucket["restingHrDays"]
                else None,
                "restingHrDays": bucket["restingHrDays"],
                "hrvAvg": round_or_none(bucket["hrvTotal"] / bucket["hrvDays"], 0)
                if bucket["hrvDays"]
                else None,
                "hrvDays": bucket["hrvDays"],
            }
        )
        cursor += timedelta(days=7)

    return weeks


def build_summary(records: list[dict[str, Any]], weeks: list[dict[str, Any]]) -> dict[str, Any]:
    trials = [row for row in records if row["category"] == "5k_time_trial" and row["fastest5kSec"]]
    intervals = [
        row
        for row in records
        if row["category"] in {"short_interval", "medium_interval", "long_interval"}
        and row["intervalPaceSecPerMile"]
    ]
    easy = [row for row in records if row["category"] in EASY_CATEGORIES]

    total_easy_weight = sum((row["easyHrTotalMin"] or row["minutes"] or 0) for row in easy)
    easy_under = (
        sum((row["easyHrUnderPct"] or 0) * (row["easyHrTotalMin"] or row["minutes"] or 0) for row in easy)
        / total_easy_weight
        if total_easy_weight
        else None
    )

    first_trial = trials[0] if trials else None
    best_trial = min(trials, key=lambda row: row["fastest5kSec"]) if trials else None
    latest_trial = trials[-1] if trials else None
    first_interval_pace = (
        sum(row["intervalPaceSecPerMile"] for row in intervals[:5]) / min(len(intervals), 5)
        if intervals
        else None
    )
    latest_interval_pace = (
        sum(row["intervalPaceSecPerMile"] for row in intervals[-5:]) / min(len(intervals), 5)
        if intervals
        else None
    )

    injury_records = [
        row
        for row in records
        if INJURY_START <= date.fromisoformat(row["date"]) < RETURN_TO_INTERVALS
    ]

    return {
        "activityCount": len(records),
        "runMiles": round(sum(row["miles"] for row in records if row["isRun"]), 1),
        "easyMiles": round(sum(row["miles"] for row in easy), 1),
        "crossTrainHours": round(sum(row["minutes"] / 60 for row in records if row["isCrossTrain"]), 1),
        "injuryCrossTrainHours": round(
            sum(row["minutes"] / 60 for row in injury_records if row["isCrossTrain"]), 1
        ),
        "injuryRunMiles": round(sum(row["miles"] for row in injury_records if row["isRun"]), 1),
        "easyHrUnderPct": round_or_none(easy_under, 1),
        "firstTrial": first_trial,
        "bestTrial": best_trial,
        "latestTrial": latest_trial,
        "trialImprovementSec": round_or_none(
            first_trial["fastest5kSec"] - best_trial["fastest5kSec"]
            if first_trial and best_trial
            else None,
            1,
        ),
        "firstIntervalPaceSecPerMile": round_or_none(first_interval_pace, 1),
        "latestIntervalPaceSecPerMile": round_or_none(latest_interval_pace, 1),
        "intervalPaceDeltaSecPerMile": round_or_none(
            first_interval_pace - latest_interval_pace
            if first_interval_pace and latest_interval_pace
            else None,
            1,
        ),
        "latestWeek": weeks[-1] if weeks else None,
        "lastFourWeeksAvgRunMiles": round_or_none(
            sum(week["runMiles"] for week in weeks[-4:]) / min(4, len(weeks)) if weeks else None,
            1,
        ),
    }


def main() -> int:
    if not SOURCE_INDEX.exists():
        print(f"Missing {SOURCE_INDEX}. Run download_garmin_activities.py first.")
        return 1

    activities = json.loads(SOURCE_INDEX.read_text(encoding="utf-8"))
    health_days = load_health_days()
    weather_by_activity = load_activity_weather()
    station_weather_by_activity = load_station_weather()
    elevation_by_activity = load_activity_elevation()
    fit_cache = load_fit_cache()
    records = build_records(
        activities,
        fit_cache,
        weather_by_activity,
        station_weather_by_activity,
        elevation_by_activity,
        health_days,
    )
    weeks = build_weeks(records, health_days)
    payload = {
        "meta": {
            "builtAt": datetime.now().isoformat(timespec="seconds"),
            "startDate": START_DATE.isoformat(),
            "maxHr": MAX_HR,
            "easyHrThreshold": round(EASY_HR_THRESHOLD, 1),
            "easyHrDisplayThreshold": math.ceil(EASY_HR_THRESHOLD),
            "injuryStart": INJURY_START.isoformat(),
            "returnToIntervals": RETURN_TO_INTERVALS.isoformat(),
            "sourceIndex": str(SOURCE_INDEX),
            "sourceHealthSummary": str(HEALTH_SUMMARY) if HEALTH_SUMMARY.exists() else None,
            "sourceWeatherSummary": str(WEATHER_SUMMARY) if WEATHER_SUMMARY.exists() else None,
            "sourceStationWeatherSummary": str(STATION_WEATHER_SUMMARY)
            if STATION_WEATHER_SUMMARY.exists()
            else None,
            "sourceElevationSummary": str(ELEVATION_SUMMARY) if ELEVATION_SUMMARY.exists() else None,
        },
        "labels": CATEGORY_LABELS,
        "summary": build_summary(records, weeks),
        "weeks": weeks,
        "records": records,
    }

    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    DATA_JS.write_text(
        "window.GARMIN_DASHBOARD_DATA = "
        + json.dumps(payload, indent=2, ensure_ascii=True)
        + ";\n",
        encoding="utf-8",
    )
    save_fit_cache(fit_cache)
    print(f"Wrote {DATA_JS} with {len(records)} activities and {len(weeks)} weeks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
