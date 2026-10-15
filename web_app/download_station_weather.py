#!/usr/bin/env python3
"""Download ASOS station weather for common Garmin run locations."""

from __future__ import annotations

import argparse
import csv
import email.utils
import io
import json
import math
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from bisect import bisect_left
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import certifi
except ImportError:  # pragma: no cover - optional dependency fallback
    certifi = None


SOURCE_INDEX = Path("data/activities/activities-index.json")
DEFAULT_OUT = Path("data") / "station-weather"
RAW_DIR_NAME = "raw"
CACHE_DIR_NAME = "cache"
SUMMARY_NAME = "activity-station-weather-summary.json"
CACHE_SCHEMA_VERSION = 1
DEFAULT_START = "2025-06-01"
IEM_ASOS_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
RUN_TYPES = {"running", "trail_running"}
METERS_PER_MILE = 1609.344
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}
MISSING_DATE_MERGE_GAP_DAYS = 7
MAX_INCREMENTAL_REQUEST_RANGES = 4
PROVISIONAL_CACHE_HOURS = 6

STATIONS = {
    "KPVU": {
        "iemId": "PVU",
        "label": "Provo Airport",
        "lat": 40.2192,
        "lon": -111.7234,
        "route": "Provo",
    },
    "KSLC": {
        "iemId": "SLC",
        "label": "Salt Lake City Intl Airport",
        "lat": 40.7884,
        "lon": -111.9778,
        "route": "Salt Lake City",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download KPVU/KSLC ASOS weather and match it to outdoor Garmin runs."
    )
    parser.add_argument(
        "--start",
        default=DEFAULT_START,
        help="Start date, YYYY-MM-DD. Defaults to 2025-06-01.",
    )
    parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="End date, YYYY-MM-DD. Defaults to today.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Output directory.",
    )
    parser.add_argument(
        "--max-distance-miles",
        type=float,
        default=15.0,
        help="Only match runs within this distance of KPVU or KSLC. Defaults to 15.",
    )
    parser.add_argument(
        "--max-observation-age-minutes",
        type=float,
        default=90.0,
        help="Only use station observations within this many minutes of run midpoint. Defaults to 90.",
    )
    parser.add_argument(
        "--station",
        action="append",
        choices=sorted(STATIONS),
        default=[],
        help="Station to fetch. Can be repeated. Defaults to KPVU and KSLC.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download station dates required by indexed activities.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Seconds to wait between station requests. Defaults to 0.2.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=4,
        help="Retries for rate limits and temporary server errors. Defaults to 4.",
    )
    parser.add_argument(
        "--retry-base-delay",
        type=float,
        default=5.0,
        help="Initial retry delay in seconds. Doubles after each retry. Defaults to 5.",
    )
    return parser.parse_args()


def parse_dt(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    return None


def type_key(activity: dict[str, Any]) -> str:
    value = activity.get("activityType")
    if isinstance(value, dict):
        return str(value.get("typeKey") or "")
    return str(value or "")


def number(value: Any) -> float | None:
    if value in (None, "", "M", "null"):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def round_or_none(value: float | None, digits: int = 1) -> float | None:
    return round(value, digits) if value is not None and math.isfinite(value) else None


def haversine_miles(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    radius_miles = 3958.8
    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    delta_phi = math.radians(lat_b - lat_a)
    delta_lambda = math.radians(lon_b - lon_a)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return radius_miles * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def nearest_station(
    activity: dict[str, Any],
    max_distance_miles: float,
    station_ids: list[str] | None = None,
) -> dict[str, Any] | None:
    lat = number(activity.get("startLatitude"))
    lon = number(activity.get("startLongitude"))
    if lat is None or lon is None:
        return None

    ranked = []
    selected_stations = station_ids or sorted(STATIONS)
    for station_id in selected_stations:
        station = STATIONS[station_id]
        distance = haversine_miles(lat, lon, station["lat"], station["lon"])
        ranked.append((distance, station_id, station))

    if not ranked:
        return None

    distance, station_id, station = min(ranked, key=lambda item: item[0])
    if distance > max_distance_miles:
        return None
    return {
        "station": station_id,
        "stationName": station["label"],
        "stationRoute": station["route"],
        "stationDistanceMiles": distance,
    }


def station_raw_path(out: Path, station: str, start_date: date, end_date: date) -> Path:
    return out / RAW_DIR_NAME / f"{station}_{start_date.isoformat()}_{end_date.isoformat()}.csv"


def station_cache_path(out: Path, station: str) -> Path:
    return out / CACHE_DIR_NAME / f"{station}.json"


def inclusive_dates(start_date: date, end_date: date) -> list[date]:
    day_count = (end_date - start_date).days + 1
    return [start_date + timedelta(days=offset) for offset in range(day_count)]


def request_url(station: str, start_date: date, end_date: date) -> str:
    # The IEM endpoint treats end-date as exclusive for the selected timezone.
    exclusive_end = end_date + timedelta(days=1)
    iem_station = STATIONS[station].get("iemId", station)
    params = [
        ("station", iem_station),
        ("data", "tmpf"),
        ("data", "dwpf"),
        ("data", "relh"),
        ("data", "feel"),
        ("data", "metar"),
        ("year1", start_date.year),
        ("month1", start_date.month),
        ("day1", start_date.day),
        ("year2", exclusive_end.year),
        ("month2", exclusive_end.month),
        ("day2", exclusive_end.day),
        ("tz", "Etc/UTC"),
        ("format", "onlycomma"),
        ("latlon", "no"),
        ("elev", "no"),
        ("missing", "M"),
        ("trace", "T"),
        ("direct", "no"),
        ("report_type", "3"),
        ("report_type", "4"),
    ]
    return f"{IEM_ASOS_URL}?{urllib.parse.urlencode(params)}"


def retry_after_seconds(headers: Any) -> float | None:
    value = headers.get("Retry-After") if headers is not None else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        pass
    try:
        retry_at = email.utils.parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def fetch_station_csv(
    station: str,
    start_date: date,
    end_date: date,
    retries: int = 4,
    retry_base_delay: float = 5.0,
) -> str:
    context = ssl.create_default_context(cafile=certifi.where()) if certifi else None
    request = urllib.request.Request(
        request_url(station, start_date, end_date),
        headers={"User-Agent": "garmin-dashboard-station-weather/1.0"},
    )
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, context=context, timeout=60) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRYABLE_HTTP_CODES or attempt >= retries:
                raise
            backoff = retry_base_delay * (2**attempt)
            delay = max(backoff, retry_after_seconds(exc.headers) or 0.0)
            print(
                f"{station}: HTTP {exc.code}; retrying in {delay:.1f}s "
                f"({attempt + 1}/{retries}).",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)

    raise RuntimeError("Station weather retry loop ended unexpectedly.")


def parse_station_csv(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    content = "\n".join(line for line in text.splitlines() if line and not line.startswith("#"))
    if not content.strip():
        return rows

    reader = csv.DictReader(io.StringIO(content))
    if not {"station", "valid"}.issubset(reader.fieldnames or []):
        raise ValueError("Station CSV is missing the station/valid columns.")

    for row in reader:
        valid = parse_dt(row.get("valid"))
        if valid is None:
            continue
        valid = valid.replace(tzinfo=timezone.utc)
        rows.append(
            {
                "station": row.get("station"),
                "valid": valid,
                "temperature": number(row.get("tmpf")),
                "dewPoint": number(row.get("dwpf")),
                "humidity": number(row.get("relh")),
                "apparentTemperature": number(row.get("feel")),
                "metar": row.get("metar") or None,
            }
        )
    return sorted(rows, key=lambda item: item["valid"])


def observation_to_json(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "valid": row["valid"].isoformat(),
    }


def observation_from_json(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    valid = parse_dt(row.get("valid"))
    if valid is None:
        return None
    return {
        "station": row.get("station"),
        "valid": valid.replace(tzinfo=timezone.utc),
        "temperature": number(row.get("temperature")),
        "dewPoint": number(row.get("dewPoint")),
        "humidity": number(row.get("humidity")),
        "apparentTemperature": number(row.get("apparentTemperature")),
        "metar": row.get("metar") or None,
    }


def merge_observations(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    replace_dates: set[date] | None = None,
) -> list[dict[str, Any]]:
    replaced = replace_dates or set()
    merged: dict[datetime, dict[str, Any]] = {
        row["valid"]: row
        for row in existing
        if row["valid"].date() not in replaced
    }
    for row in incoming:
        merged[row["valid"]] = row
    return sorted(merged.values(), key=lambda item: item["valid"])


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)


def write_station_cache(
    out: Path,
    station: str,
    covered_dates: set[date],
    observations: list[dict[str, Any]],
    provisional_attempts: dict[date, datetime] | None = None,
) -> None:
    payload = {
        "schemaVersion": CACHE_SCHEMA_VERSION,
        "station": station,
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
        "coveredDates": [value.isoformat() for value in sorted(covered_dates)],
        "provisionalAttempts": {
            value.isoformat(): attempted_at.isoformat()
            for value, attempted_at in sorted((provisional_attempts or {}).items())
        },
        "observations": [observation_to_json(row) for row in observations],
    }
    write_text_atomic(
        station_cache_path(out, station),
        json.dumps(payload, indent=2, ensure_ascii=True),
    )


def load_station_cache(
    out: Path,
    station: str,
) -> tuple[set[date], list[dict[str, Any]], dict[date, datetime]]:
    path = station_cache_path(out, station)
    if not path.exists():
        return set(), [], {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            payload.get("schemaVersion") != CACHE_SCHEMA_VERSION
            or payload.get("station") != station
        ):
            raise ValueError("unsupported station cache schema")
        covered_dates = {date.fromisoformat(value) for value in payload.get("coveredDates", [])}
        provisional_attempts = {
            date.fromisoformat(value): attempted_at
            for value, raw_attempted_at in payload.get("provisionalAttempts", {}).items()
            if (attempted_at := parse_dt(raw_attempted_at)) is not None
        }
        provisional_attempts = {
            value: attempted_at.replace(tzinfo=timezone.utc)
            for value, attempted_at in provisional_attempts.items()
        }
        observations = [
            parsed
            for row in payload.get("observations", [])
            if (parsed := observation_from_json(row)) is not None
        ]
        return covered_dates, merge_observations([], observations), provisional_attempts
    except (AttributeError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"Ignoring invalid station cache {path}: {exc}", file=sys.stderr)
        return set(), [], {}


def legacy_raw_ranges(out: Path, station: str) -> list[tuple[date, date, Path]]:
    raw_dir = out / RAW_DIR_NAME
    if not raw_dir.exists():
        return []
    pattern = re.compile(
        rf"^{re.escape(station)}_(\d{{4}}-\d{{2}}-\d{{2}})_(\d{{4}}-\d{{2}}-\d{{2}})\.csv$"
    )
    ranges = []
    for path in raw_dir.glob(f"{station}_*.csv"):
        match = pattern.match(path.name)
        if not match:
            continue
        try:
            start_date = date.fromisoformat(match.group(1))
            end_date = date.fromisoformat(match.group(2))
        except ValueError:
            continue
        if end_date >= start_date:
            ranges.append((start_date, end_date, path))
    return sorted(
        ranges,
        key=lambda row: ((row[1] - row[0]).days, row[1]),
        reverse=True,
    )


def load_or_migrate_station_cache(
    out: Path,
    station: str,
) -> tuple[set[date], list[dict[str, Any]], dict[date, datetime], bool]:
    cache_path = station_cache_path(out, station)
    if cache_path.exists():
        covered_dates, observations, provisional_attempts = load_station_cache(out, station)
        if (
            covered_dates
            or observations
            or provisional_attempts
            or not legacy_raw_ranges(out, station)
        ):
            return covered_dates, observations, provisional_attempts, False

    covered_dates: set[date] = set()
    provisional_attempts: dict[date, datetime] = {}
    observations: list[dict[str, Any]] = []
    imported_files = 0
    for start_date, end_date, path in legacy_raw_ranges(out, station):
        file_dates = set(inclusive_dates(start_date, end_date))
        if file_dates.issubset(covered_dates | set(provisional_attempts)):
            continue
        try:
            parsed = parse_station_csv(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"Skipping invalid legacy station file {path}: {exc}", file=sys.stderr)
            continue
        observations = merge_observations(observations, parsed)
        attempted_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        record_successful_dates(file_dates, covered_dates, provisional_attempts, attempted_at)
        imported_files += 1

    if imported_files:
        write_station_cache(out, station, covered_dates, observations, provisional_attempts)
        print(
            f"{station}: migrated {imported_files} legacy CSV cache file(s) "
            f"covering {len(covered_dates)} dates.",
            flush=True,
        )
    return covered_dates, observations, provisional_attempts, bool(imported_files)


def reusable_dates(
    covered_dates: set[date],
    provisional_attempts: dict[date, datetime],
    now: datetime | None = None,
) -> set[date]:
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(hours=PROVISIONAL_CACHE_HOURS)
    return covered_dates | {
        value
        for value, attempted_at in provisional_attempts.items()
        if value >= current.date() and attempted_at >= cutoff
    }


def record_successful_dates(
    requested_dates: set[date],
    covered_dates: set[date],
    provisional_attempts: dict[date, datetime],
    now: datetime | None = None,
) -> None:
    current = now or datetime.now(timezone.utc)
    for value in requested_dates:
        if value < current.date():
            covered_dates.add(value)
            provisional_attempts.pop(value, None)
        else:
            provisional_attempts[value] = current


def group_missing_dates(values: set[date]) -> list[tuple[date, date]]:
    if not values:
        return []
    ordered = sorted(values)
    ranges: list[tuple[date, date]] = []
    range_start = ordered[0]
    previous = ordered[0]
    for current in ordered[1:]:
        if (current - previous).days <= MISSING_DATE_MERGE_GAP_DAYS:
            previous = current
            continue
        ranges.append((range_start, previous))
        range_start = current
        previous = current
    ranges.append((range_start, previous))
    if len(ranges) > MAX_INCREMENTAL_REQUEST_RANGES:
        return [(ordered[0], ordered[-1])]
    return ranges


def required_station_dates(
    activity_rows: list[tuple[dict[str, Any], dict[str, Any] | None]],
    max_age_minutes: float,
) -> dict[str, set[date]]:
    required: dict[str, set[date]] = {}
    age = timedelta(minutes=max_age_minutes)
    for activity, station_match in activity_rows:
        if type_key(activity) not in RUN_TYPES or station_match is None:
            continue
        target = midpoint_utc(activity)
        if target is None:
            continue
        station_dates = required.setdefault(station_match["station"], set())
        station_dates.update(inclusive_dates((target - age).date(), (target + age).date()))
    return required


def nearest_observation(
    observations: list[dict[str, Any]],
    target: datetime,
    max_age_minutes: float,
) -> tuple[dict[str, Any] | None, float | None]:
    if not observations:
        return None, None
    times = [row["valid"] for row in observations]
    index = bisect_left(times, target)
    candidates = []
    if index < len(observations):
        candidates.append(observations[index])
    if index > 0:
        candidates.append(observations[index - 1])
    if not candidates:
        return None, None

    closest = min(candidates, key=lambda item: abs((item["valid"] - target).total_seconds()))
    offset_minutes = (closest["valid"] - target).total_seconds() / 60
    if abs(offset_minutes) > max_age_minutes:
        return None, offset_minutes
    return closest, offset_minutes


def midpoint_utc(activity: dict[str, Any]) -> datetime | None:
    start = parse_dt(activity.get("startTimeGMT"))
    if start is None:
        return None
    duration = number(activity.get("elapsedDuration")) or number(activity.get("duration")) or 0
    return start.replace(tzinfo=timezone.utc) + timedelta(seconds=duration / 2)


def build_activity_summary(
    activity: dict[str, Any],
    station_match: dict[str, Any] | None,
    station_observations: dict[str, list[dict[str, Any]]],
    max_age_minutes: float,
) -> dict[str, Any]:
    activity_id = str(activity.get("activityId") or activity.get("id") or "")
    activity_type = type_key(activity)
    base = {
        "activityId": activity_id,
        "date": str(activity.get("startTimeLocal") or "")[:10],
        "startTimeLocal": activity.get("startTimeLocal"),
        "activityName": activity.get("activityName"),
        "activityType": activity_type,
        "status": "skipped",
    }

    if activity_type not in RUN_TYPES:
        return {**base, "message": f"Station weather is only enabled for outdoor runs."}
    if station_match is None:
        return {**base, "message": "No configured station within max distance."}

    target = midpoint_utc(activity)
    if target is None:
        return {**base, **station_match, "message": "Missing startTimeGMT."}

    observation, offset = nearest_observation(
        station_observations.get(station_match["station"], []),
        target,
        max_age_minutes,
    )
    if observation is None:
        return {
            **base,
            **station_match,
            "status": "missing",
            "midpointUtc": target.isoformat(),
            "observationOffsetMinutes": round_or_none(offset, 1),
            "message": "No nearby station observation.",
        }

    return {
        **base,
        **station_match,
        "status": "ok",
        "source": f"iem-asos:{station_match['station']}",
        "midpointUtc": target.isoformat(),
        "observationTimeUtc": observation["valid"].isoformat(),
        "observationOffsetMinutes": round_or_none(offset, 1),
        "temperature": round_or_none(observation["temperature"], 1),
        "apparentTemperature": round_or_none(observation["apparentTemperature"], 1),
        "dewPoint": round_or_none(observation["dewPoint"], 1),
        "humidity": round_or_none(observation["humidity"], 1),
        "metar": observation["metar"],
    }


def main() -> int:
    args = parse_args()
    if not SOURCE_INDEX.exists():
        print(f"Missing {SOURCE_INDEX}. Run download_garmin_activities.py first.")
        return 1
    if args.max_distance_miles <= 0:
        print("--max-distance-miles must be greater than 0.")
        return 2
    if args.max_observation_age_minutes <= 0:
        print("--max-observation-age-minutes must be greater than 0.")
        return 2
    if args.delay < 0:
        print("--delay must be zero or greater.")
        return 2
    if args.retries < 0:
        print("--retries must be zero or greater.")
        return 2
    if args.retry_base_delay < 0:
        print("--retry-base-delay must be zero or greater.")
        return 2

    try:
        start_date = date.fromisoformat(args.start)
        end_date = date.fromisoformat(args.end)
    except ValueError:
        print("--start and --end must use YYYY-MM-DD dates.")
        return 2
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    activities = json.loads(SOURCE_INDEX.read_text(encoding="utf-8"))
    stations = args.station or sorted(STATIONS)
    activity_rows: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for activity in activities:
        local_dt = parse_dt(activity.get("startTimeLocal"))
        if local_dt is None or not start_date <= local_dt.date() <= end_date:
            continue
        activity_rows.append(
            (activity, nearest_station(activity, args.max_distance_miles, stations))
        )

    required_dates = required_station_dates(activity_rows, args.max_observation_age_minutes)
    station_observations: dict[str, list[dict[str, Any]]] = {}
    station_meta: dict[str, dict[str, Any]] = {}
    downloaded = 0
    cached = 0
    failed_requests: list[tuple[str, date, date, str]] = []

    for station in stations:
        covered_dates, observations, provisional_attempts, migrated = load_or_migrate_station_cache(
            args.out, station
        )
        needed_dates = required_dates.get(station, set())
        cached_dates = reusable_dates(covered_dates, provisional_attempts)
        missing_dates = needed_dates if args.overwrite else needed_dates - cached_dates
        request_ranges = group_missing_dates(missing_dates)
        downloaded_ranges: list[dict[str, str]] = []
        failed_ranges: list[dict[str, str]] = []

        if not request_ranges:
            cached += 1
            print(
                f"{station}: cache covers all {len(needed_dates)} required date(s); "
                "no request needed.",
                flush=True,
            )

        for request_start, request_end in request_ranges:
            request_dates = set(inclusive_dates(request_start, request_end))
            try:
                text = fetch_station_csv(
                    station,
                    request_start,
                    request_end,
                    retries=args.retries,
                    retry_base_delay=args.retry_base_delay,
                )
                parsed = parse_station_csv(text)
                write_text_atomic(
                    station_raw_path(args.out, station, request_start, request_end),
                    text,
                )
                observations = merge_observations(
                    observations,
                    parsed,
                    replace_dates=request_dates,
                )
                record_successful_dates(
                    request_dates,
                    covered_dates,
                    provisional_attempts,
                )
                write_station_cache(
                    args.out,
                    station,
                    covered_dates,
                    observations,
                    provisional_attempts,
                )
                downloaded += 1
                downloaded_ranges.append(
                    {"start": request_start.isoformat(), "end": request_end.isoformat()}
                )
                print(
                    f"{station}: downloaded {request_start} through {request_end} "
                    f"({len(parsed)} observations).",
                    flush=True,
                )
                if args.delay:
                    time.sleep(args.delay)
            except (OSError, TimeoutError, ValueError, urllib.error.URLError) as exc:
                message = str(exc)
                failed_requests.append((station, request_start, request_end, message))
                failed_ranges.append(
                    {
                        "start": request_start.isoformat(),
                        "end": request_end.isoformat(),
                        "error": message,
                    }
                )
                print(
                    f"{station}: failed to download {request_start} through "
                    f"{request_end}: {message}",
                    file=sys.stderr,
                    flush=True,
                )

        station_observations[station] = observations
        station_meta[station] = {
            **STATIONS[station],
            "observationCount": len(observations),
            "coveredDateCount": len(covered_dates),
            "provisionalDateCount": len(provisional_attempts),
            "requiredDateCount": len(needed_dates),
            "migratedLegacyCache": migrated,
            "downloadedRanges": downloaded_ranges,
            "failedRanges": failed_ranges,
        }

    summaries = []
    counts = {"ok": 0, "missing": 0, "skipped": 0}
    for activity, match in activity_rows:
        summary = build_activity_summary(
            activity,
            match,
            station_observations,
            args.max_observation_age_minutes,
        )
        counts[summary["status"]] = counts.get(summary["status"], 0) + 1
        summaries.append(summary)

    args.out.mkdir(parents=True, exist_ok=True)
    payload = {
        "builtAt": datetime.now().isoformat(timespec="seconds"),
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "source": "Iowa Environmental Mesonet ASOS archive",
        "sourceUrl": IEM_ASOS_URL,
        "stations": station_meta,
        "maxDistanceMiles": args.max_distance_miles,
        "maxObservationAgeMinutes": args.max_observation_age_minutes,
        "downloadedStationFiles": downloaded,
        "cachedStationFiles": cached,
        "failedStationRequests": len(failed_requests),
        "counts": counts,
        "activities": summaries,
    }
    write_text_atomic(
        args.out / SUMMARY_NAME,
        json.dumps(payload, indent=2, ensure_ascii=True),
    )
    print(
        f"Wrote {args.out / SUMMARY_NAME} with {counts.get('ok', 0)} matched runs "
        f"({counts.get('missing', 0)} missing, {counts.get('skipped', 0)} skipped); "
        f"network requests={downloaded}, failed requests={len(failed_requests)}."
    )
    return 1 if failed_requests else 0


if __name__ == "__main__":
    raise SystemExit(main())
