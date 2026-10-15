"""Garmin response normalization shared by the web and Android apps."""
from __future__ import annotations
from typing import Any

def first_number(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def find_by_keys(data: Any, keys: tuple[str, ...]) -> Any:
    normalized_keys = {key.lower().replace("_", "").replace("-", "") for key in keys}
    if isinstance(data, dict):
        for key, value in data.items():
            normalized = key.lower().replace("_", "").replace("-", "")
            if normalized in normalized_keys and not isinstance(value, (dict, list)):
                return value
        for value in data.values():
            found = find_by_keys(value, keys)
            if found is not None:
                return found
    elif isinstance(data, list):
        for value in data:
            found = find_by_keys(value, keys)
            if found is not None:
                return found
    return None


def summarize_weather(activity: dict[str, Any], weather: Any) -> dict[str, Any]:
    activity_id = str(activity.get("activityId") or activity.get("id") or "")
    temperature = first_number(
        find_by_keys(weather, ("temp", "temperature")),
        activity.get("averageTemperature"),
    )
    apparent = first_number(
        find_by_keys(weather, ("apparentTemp", "apparentTemperature", "feelsLike"))
    )
    dew_point = first_number(find_by_keys(weather, ("dewPoint", "dewpoint")))
    humidity = first_number(find_by_keys(weather, ("relativeHumidity", "humidity")))
    wind_speed = first_number(find_by_keys(weather, ("windSpeed", "windVelocity")))
    wind_direction = first_number(find_by_keys(weather, ("windDirection", "windBearing")))
    weather_desc = find_by_keys(weather, ("desc", "weatherDescription"))
    station = find_by_keys(weather, ("name", "stationName"))

    return {
        "activityId": activity_id,
        "date": str(activity.get("startTimeLocal") or "")[:10],
        "startTimeLocal": activity.get("startTimeLocal"),
        "activityName": activity.get("activityName"),
        "activityType": (activity.get("activityType") or {}).get("typeKey")
        if isinstance(activity.get("activityType"), dict)
        else activity.get("activityType"),
        "temperature": temperature,
        "apparentTemperature": apparent,
        "dewPoint": dew_point,
        "humidity": humidity,
        "windSpeed": wind_speed,
        "windDirection": wind_direction,
        "weatherDescription": weather_desc,
        "weatherStation": station,
        "hasWeather": weather is not None,
        "rawKeys": sorted(weather.keys()) if isinstance(weather, dict) else None,
    }
