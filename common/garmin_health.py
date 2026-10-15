"""Garmin response normalization shared by the web and Android apps."""
from __future__ import annotations
from typing import Any

def get_nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first_number(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def hours_from_seconds(value: Any) -> float | None:
    seconds = first_number(value)
    if seconds is None:
        return None
    return round(seconds / 3600, 2)


def sleep_summary(day: str, data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"date": day}

    dto = data.get("dailySleepDTO") or data.get("dailySleepDto") or data
    scores = data.get("sleepScores") or dto.get("sleepScores") or {}

    sleep_seconds = first_number(
        dto.get("sleepTimeSeconds"),
        dto.get("sleepTime"),
        dto.get("durationInSeconds"),
    )

    return {
        "date": day,
        "sleepStart": dto.get("sleepStartTimestampLocal")
        or dto.get("sleepStartTimestampGMT"),
        "sleepEnd": dto.get("sleepEndTimestampLocal")
        or dto.get("sleepEndTimestampGMT"),
        "sleepSeconds": sleep_seconds,
        "sleepHours": hours_from_seconds(sleep_seconds),
        "deepSleepSeconds": first_number(dto.get("deepSleepSeconds")),
        "lightSleepSeconds": first_number(dto.get("lightSleepSeconds")),
        "remSleepSeconds": first_number(dto.get("remSleepSeconds")),
        "awakeSleepSeconds": first_number(dto.get("awakeSleepSeconds")),
        "sleepScore": first_number(
            get_nested(scores, "overall", "value"),
            dto.get("sleepScore"),
            dto.get("overallSleepScore"),
        ),
    }


def rhr_summary(day: str, data: Any) -> dict[str, Any]:
    resting_hr = None
    if isinstance(data, list) and data:
        for row in data:
            if not isinstance(row, dict):
                continue
            resting_hr = first_number(
                row.get("value"),
                row.get("calendarDateRestingHeartRate"),
                row.get("restingHeartRate"),
            )
            if resting_hr is not None:
                break
    elif isinstance(data, dict):
        metrics = data.get("allMetrics")
        if isinstance(metrics, list):
            for metric in metrics:
                if not isinstance(metric, dict):
                    continue
                resting_hr = first_number(
                    metric.get("value"),
                    metric.get("calendarDateRestingHeartRate"),
                    metric.get("restingHeartRate"),
                )
                if resting_hr is not None:
                    break
        elif isinstance(metrics, dict):
            metrics_map = metrics.get("metricsMap")
            if isinstance(metrics_map, dict):
                values = metrics_map.get("WELLNESS_RESTING_HEART_RATE") or []
                for metric in values:
                    if not isinstance(metric, dict):
                        continue
                    resting_hr = first_number(metric.get("value"))
                    if resting_hr is not None:
                        break
        resting_hr = first_number(
            resting_hr,
            data.get("calendarDateRestingHeartRate"),
            data.get("restingHeartRate"),
            data.get("value"),
        )

    return {"date": day, "restingHeartRate": resting_hr}


def hrv_summary(day: str, data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"date": day}

    summary = data.get("hrvSummary") or data.get("hrvDailySummary") or data
    return {
        "date": day,
        "lastNightAvg": first_number(
            summary.get("lastNightAvg"),
            summary.get("lastNightAverage"),
            summary.get("avgOvernightHrv"),
        ),
        "lastNight5MinHigh": first_number(
            summary.get("lastNight5MinHigh"),
            summary.get("lastNightFiveMinHigh"),
        ),
        "weeklyAvg": first_number(summary.get("weeklyAvg"), summary.get("weeklyAverage")),
        "status": summary.get("status"),
        "baselineLow": first_number(
            get_nested(summary, "baseline", "lowUpper"),
            get_nested(summary, "baseline", "low"),
            summary.get("baselineLow"),
        ),
        "baselineHigh": first_number(
            get_nested(summary, "baseline", "balancedUpper"),
            get_nested(summary, "baseline", "high"),
            summary.get("baselineHigh"),
        ),
    }


def merged_summary(day: str, raw: dict[str, Any]) -> dict[str, Any]:
    sleep = sleep_summary(day, raw.get("sleep"))
    rhr = rhr_summary(day, raw.get("rhr"))
    hrv = hrv_summary(day, raw.get("hrv"))
    return {
        "date": day,
        "sleepSeconds": sleep.get("sleepSeconds"),
        "sleepHours": sleep.get("sleepHours"),
        "deepSleepSeconds": sleep.get("deepSleepSeconds"),
        "lightSleepSeconds": sleep.get("lightSleepSeconds"),
        "remSleepSeconds": sleep.get("remSleepSeconds"),
        "awakeSleepSeconds": sleep.get("awakeSleepSeconds"),
        "sleepScore": sleep.get("sleepScore"),
        "restingHeartRate": rhr.get("restingHeartRate"),
        "hrvLastNightAvg": hrv.get("lastNightAvg"),
        "hrvLastNight5MinHigh": hrv.get("lastNight5MinHigh"),
        "hrvWeeklyAvg": hrv.get("weeklyAvg"),
        "hrvStatus": hrv.get("status"),
        "hrvBaselineLow": hrv.get("baselineLow"),
        "hrvBaselineHigh": hrv.get("baselineHigh"),
    }
