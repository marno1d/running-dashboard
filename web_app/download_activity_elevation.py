#!/usr/bin/env python3
"""Download DEM-based elevation summaries for Garmin activity routes."""

from __future__ import annotations

import argparse
import json
import math
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import fitdecode

try:
    import certifi
except ImportError:  # pragma: no cover - optional dependency fallback
    certifi = None


SOURCE_INDEX = Path("data/activities/activities-index.json")
ORIGINAL_DIR = Path("data/activities/original")
ELEVATION_DIR = Path("data/activity-elevation")
RAW_DIR = ELEVATION_DIR / "raw"
SUMMARY_PATH = ELEVATION_DIR / "activity-elevation-summary.json"

DEFAULT_START = "2025-06-01"
DEFAULT_DATASET = "ned10m,srtm30m"
DEFAULT_API_BASE = "https://api.opentopodata.org/v1"
SEMICIRCLE_SCALE = 180 / 2**31
OUTDOOR_ELEVATION_TYPES = {"running", "trail_running", "cycling", "mountain_biking", "hiking", "walking"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Look up route elevations from OpenTopoData and cache activity summaries."
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
        "--dataset",
        default=DEFAULT_DATASET,
        help="OpenTopoData dataset name. Defaults to ned10m,srtm30m.",
    )
    parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="OpenTopoData API base URL.",
    )
    parser.add_argument(
        "--sample-distance",
        type=float,
        default=75.0,
        help="Target spacing between route samples in meters. Defaults to 75.",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=500,
        help="Maximum samples per activity. Longer routes use wider spacing. Defaults to 500.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=100,
        help="Maximum coordinate samples per API request. Defaults to 100.",
    )
    parser.add_argument(
        "--min-elevation-change",
        type=float,
        default=1.0,
        help="Ignore smaller up/down changes when totaling gain/loss, in meters. Defaults to 1.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Seconds to wait between API requests. Defaults to 0.2.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="API request timeout in seconds. Defaults to 30.",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="Maximum uncached activities to query.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-query activities that already have cached elevation files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse routes and report planned API work without calling OpenTopoData.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print cached and skipped activity rows. By default only API work and errors are printed.",
    )
    return parser.parse_args()


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    return None


def type_key(activity: dict[str, Any]) -> str:
    value = activity.get("activityType")
    if isinstance(value, dict):
        return str(value.get("typeKey") or "")
    return str(value or "")


def activity_file_map() -> dict[str, Path]:
    files: dict[str, Path] = {}
    if not ORIGINAL_DIR.exists():
        return files
    for path in ORIGINAL_DIR.glob("*.zip"):
        activity_id = path.stem.rsplit("_", 1)[-1]
        if activity_id.isdigit():
            files[activity_id] = path
    return files


def fit_value(frame: fitdecode.FitDataMessage, field_name: str) -> Any:
    try:
        return frame.get_value(field_name)
    except Exception:
        return None


def number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def seconds(value: Any) -> float | None:
    parsed = number(value)
    return parsed if parsed is not None and parsed > 0 else None


def position_degrees(value: Any) -> float | None:
    parsed = number(value)
    if parsed is None:
        return None
    if abs(parsed) > 180:
        return parsed * SEMICIRCLE_SCALE
    return parsed


def haversine_meters(
    lat_a: float,
    lng_a: float,
    lat_b: float,
    lng_b: float,
) -> float:
    radius = 6_371_000.0
    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    delta_phi = math.radians(lat_b - lat_a)
    delta_lambda = math.radians(lng_b - lng_a)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def fit_name_from_zip(zip_path: Path) -> str | None:
    with zipfile.ZipFile(zip_path) as archive:
        return next((name for name in archive.namelist() if name.lower().endswith(".fit")), None)


def route_points_from_fit(zip_path: Path) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    with zipfile.ZipFile(zip_path) as archive:
        fit_name = fit_name_from_zip(zip_path)
        if fit_name is None:
            return []

        with archive.open(fit_name) as fit_file:
            last_distance: float | None = None
            previous: dict[str, Any] | None = None
            for frame in fitdecode.FitReader(fit_file):
                if not isinstance(frame, fitdecode.FitDataMessage) or frame.name != "record":
                    continue

                timestamp = fit_value(frame, "timestamp")
                lat = position_degrees(fit_value(frame, "position_lat"))
                lng = position_degrees(fit_value(frame, "position_long"))
                if timestamp is None or lat is None or lng is None:
                    continue
                if not -90 <= lat <= 90 or not -180 <= lng <= 180:
                    continue

                fit_distance = number(fit_value(frame, "distance"))
                segment_distance = (
                    haversine_meters(previous["lat"], previous["lng"], lat, lng)
                    if previous
                    else 0.0
                )
                if (
                    fit_distance is not None
                    and fit_distance >= 0
                    and (last_distance is None or fit_distance >= last_distance)
                ):
                    distance_meters = fit_distance
                else:
                    distance_meters = (last_distance or 0.0) + segment_distance

                point = {
                    "timestamp": timestamp,
                    "lat": lat,
                    "lng": lng,
                    "distanceMeters": distance_meters,
                }
                last_distance = distance_meters
                previous = point

                if not points or distance_meters - points[-1]["distanceMeters"] >= 2:
                    points.append(point)

    return points


def active_lap_windows_from_fit(zip_path: Path) -> list[tuple[datetime, datetime]]:
    windows: list[tuple[datetime, datetime]] = []
    with zipfile.ZipFile(zip_path) as archive:
        fit_name = fit_name_from_zip(zip_path)
        if fit_name is None:
            return []

        with archive.open(fit_name) as fit_file:
            for frame in fitdecode.FitReader(fit_file):
                if not isinstance(frame, fitdecode.FitDataMessage) or frame.name != "lap":
                    continue
                if str(fit_value(frame, "intensity")).lower() != "active":
                    continue
                start = fit_value(frame, "start_time")
                duration = seconds(fit_value(frame, "total_timer_time")) or seconds(
                    fit_value(frame, "total_elapsed_time")
                )
                if start is None or duration is None:
                    continue
                windows.append((start, start + timedelta(seconds=duration)))
    return windows


def interpolate_track_point(
    left: dict[str, Any],
    right: dict[str, Any],
    target_distance: float,
) -> dict[str, Any]:
    distance_delta = right["distanceMeters"] - left["distanceMeters"]
    fraction = 0.0 if distance_delta <= 0 else (target_distance - left["distanceMeters"]) / distance_delta
    timestamp = left["timestamp"] + (right["timestamp"] - left["timestamp"]) * fraction
    return {
        "timestamp": timestamp,
        "lat": left["lat"] + (right["lat"] - left["lat"]) * fraction,
        "lng": left["lng"] + (right["lng"] - left["lng"]) * fraction,
        "distanceMeters": target_distance,
    }


def sample_track(
    route: list[dict[str, Any]],
    sample_distance_meters: float,
    max_samples: int,
) -> list[dict[str, Any]]:
    if len(route) < 2:
        return []

    total_distance = route[-1]["distanceMeters"]
    if total_distance <= 0:
        return []

    sample_count_limit = max(2, max_samples)
    effective_step = max(sample_distance_meters, total_distance / (sample_count_limit - 1))
    targets: list[float] = []
    target = 0.0
    while target < total_distance:
        targets.append(target)
        target += effective_step
    if not targets or targets[-1] != total_distance:
        targets.append(total_distance)

    samples: list[dict[str, Any]] = []
    right_index = 1
    for target_distance in targets:
        while (
            right_index < len(route) - 1
            and route[right_index]["distanceMeters"] < target_distance
        ):
            right_index += 1
        samples.append(
            interpolate_track_point(route[right_index - 1], route[right_index], target_distance)
        )
    return samples


def api_url(api_base: str, dataset: str) -> str:
    quoted_dataset = urllib.parse.quote(dataset, safe=",")
    return f"{api_base.rstrip('/')}/{quoted_dataset}"


def https_context() -> ssl.SSLContext | None:
    if certifi is None:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def query_elevations(
    samples: list[dict[str, Any]],
    args: argparse.Namespace,
    request_json: Any = None,
) -> list[dict[str, Any]]:
    profile: list[dict[str, Any]] = []
    context = https_context()
    for start in range(0, len(samples), args.chunk_size):
        chunk = samples[start : start + args.chunk_size]
        locations = "|".join(f"{point['lat']:.7f},{point['lng']:.7f}" for point in chunk)
        payload = json.dumps(
            {
                "locations": locations,
                "interpolation": "bilinear",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            api_url(args.api_base, args.dataset),
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "garmin-dashboard-elevation/1.0",
            },
            method="POST",
        )

        try:
            if request_json is not None:
                result = request_json(request, args.timeout, context)
            else:
                with urllib.request.urlopen(request, timeout=args.timeout, context=context) as response:
                    result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
        if result.get("status") != "OK":
            raise RuntimeError(result.get("error") or f"OpenTopoData status {result.get('status')}")

        rows = result.get("results")
        if not isinstance(rows, list) or len(rows) != len(chunk):
            raise RuntimeError("OpenTopoData returned an unexpected result count")

        for sample, row in zip(chunk, rows):
            profile.append(
                {
                    **sample,
                    "elevationMeters": number(row.get("elevation")),
                    "dataset": row.get("dataset"),
                }
            )

        if args.delay > 0 and start + args.chunk_size < len(samples):
            time.sleep(args.delay)

    return profile


def elevation_gain_loss(
    elevations: list[float],
    min_elevation_change: float,
) -> tuple[float, float]:
    if len(elevations) < 2:
        return 0.0, 0.0

    gain = 0.0
    loss = 0.0
    anchor = elevations[0]
    for elevation in elevations[1:]:
        delta = elevation - anchor
        if delta >= min_elevation_change:
            gain += delta
            anchor = elevation
        elif delta <= -min_elevation_change:
            loss -= delta
            anchor = elevation
    return gain, loss


def summarize_profile(
    profile: list[dict[str, Any]],
    min_elevation_change: float,
) -> dict[str, Any]:
    elevations = [
        point["elevationMeters"]
        for point in profile
        if point.get("elevationMeters") is not None
    ]
    if len(elevations) < 2:
        return {
            "elevationGainMeters": None,
            "elevationLossMeters": None,
            "minElevationMeters": None,
            "maxElevationMeters": None,
        }

    gain, loss = elevation_gain_loss(elevations, min_elevation_change)
    return {
        "elevationGainMeters": round(gain, 1),
        "elevationLossMeters": round(loss, 1),
        "minElevationMeters": round(min(elevations), 1),
        "maxElevationMeters": round(max(elevations), 1),
    }


def profile_in_windows(
    profile: list[dict[str, Any]],
    windows: list[tuple[datetime, datetime]],
) -> list[dict[str, Any]]:
    if not windows:
        return []
    return [
        point
        for point in profile
        if any(start <= point["timestamp"] <= end for start, end in windows)
    ]


def json_profile(profile: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": point["timestamp"].isoformat(),
            "distanceMeters": round(point["distanceMeters"], 1),
            "lat": round(point["lat"], 7),
            "lng": round(point["lng"], 7),
            "elevationMeters": point.get("elevationMeters"),
            "dataset": point.get("dataset"),
        }
        for point in profile
    ]


def cached_raw(activity_id: str) -> dict[str, Any] | None:
    path = RAW_DIR / f"{activity_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def summary_from_raw(raw: dict[str, Any]) -> dict[str, Any]:
    retired_keys = {"profile", "elevationCostRatio", "intervalElevationCostRatio"}
    return {key: value for key, value in raw.items() if key not in retired_keys}


def build_skip_summary(
    activity: dict[str, Any],
    activity_id: str,
    status: str,
    message: str,
) -> dict[str, Any]:
    return {
        "activityId": activity_id,
        "date": (parse_dt(activity.get("startTimeLocal")) or datetime.min).date().isoformat(),
        "name": activity.get("activityName") or "Activity",
        "status": status,
        "message": message,
    }


def should_print_activity(raw: dict[str, Any], args: argparse.Namespace) -> bool:
    return args.verbose or raw.get("status") in {"ok", "error", "dry_run"}


def build_activity_elevation(
    activity: dict[str, Any],
    activity_id: str,
    zip_path: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    activity_type = type_key(activity)
    if activity_type not in OUTDOOR_ELEVATION_TYPES:
        return build_skip_summary(
            activity,
            activity_id,
            "skipped",
            f"External elevation is disabled for {activity_type or 'unknown'} activities.",
        )

    route = route_points_from_fit(zip_path)
    if len(route) < 2:
        return build_skip_summary(activity, activity_id, "skipped", "No GPS route in FIT file.")

    samples = sample_track(route, args.sample_distance, args.max_samples)
    if len(samples) < 2:
        return build_skip_summary(activity, activity_id, "skipped", "Route was too short to sample.")

    if args.dry_run:
        return {
            **build_skip_summary(activity, activity_id, "dry_run", "Route parsed; API not called."),
            "routePointCount": len(route),
            "sampleCount": len(samples),
            "distanceMeters": round(route[-1]["distanceMeters"], 1),
        }

    profile = query_elevations(samples, args)
    summary = summarize_profile(profile, args.min_elevation_change)
    active_profile = profile_in_windows(profile, active_lap_windows_from_fit(zip_path))
    active_summary = summarize_profile(active_profile, args.min_elevation_change)

    raw = {
        "activityId": activity_id,
        "date": (parse_dt(activity.get("startTimeLocal")) or datetime.min).date().isoformat(),
        "name": activity.get("activityName") or "Activity",
        "status": "ok",
        "source": "opentopodata",
        "dataset": args.dataset,
        "apiBase": args.api_base,
        "interpolation": "bilinear",
        "sampleDistanceMeters": args.sample_distance,
        "minElevationChangeMeters": args.min_elevation_change,
        "distanceMeters": round(route[-1]["distanceMeters"], 1),
        "routePointCount": len(route),
        "sampleCount": len(profile),
        "validElevationCount": sum(
            1 for point in profile if point.get("elevationMeters") is not None
        ),
        **summary,
        "intervalSampleCount": len(active_profile),
        "intervalElevationGainMeters": active_summary["elevationGainMeters"],
        "intervalElevationLossMeters": active_summary["elevationLossMeters"],
        "profile": json_profile(profile),
    }
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / f"{activity_id}.json").write_text(
        json.dumps(raw, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    return raw


def main() -> int:
    args = parse_args()
    if not SOURCE_INDEX.exists():
        print(f"Missing {SOURCE_INDEX}. Run download_garmin_activities.py first.")
        return 1
    if args.sample_distance <= 0:
        print("--sample-distance must be greater than 0.")
        return 2
    if args.max_samples < 2:
        print("--max-samples must be at least 2.")
        return 2
    if args.chunk_size < 1:
        print("--chunk-size must be at least 1.")
        return 2

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    activities = json.loads(SOURCE_INDEX.read_text(encoding="utf-8"))
    files = activity_file_map()
    summaries: list[dict[str, Any]] = []
    queried = 0
    cached_count = 0
    skipped_non_outdoor = 0

    for activity in activities:
        local_dt = parse_dt(activity.get("startTimeLocal"))
        if local_dt is None or not start_date <= local_dt.date() <= end_date:
            continue

        activity_id = str(activity.get("activityId") or activity.get("id") or "")
        if not activity_id:
            continue

        activity_type = type_key(activity)
        if activity_type not in OUTDOOR_ELEVATION_TYPES:
            skipped_non_outdoor += 1
            summaries.append(
                build_skip_summary(
                    activity,
                    activity_id,
                    "skipped",
                    f"External elevation is disabled for {activity_type or 'unknown'} activities.",
                )
            )
            continue

        if not args.overwrite:
            cached = cached_raw(activity_id)
            if cached:
                summaries.append(summary_from_raw(cached))
                cached_count += 1
                if args.verbose:
                    print(f"{activity_id}: cached {cached.get('name')}", flush=True)
                continue

        zip_path = files.get(activity_id)
        if zip_path is None:
            summaries.append(
                build_skip_summary(activity, activity_id, "skipped", "Missing original FIT ZIP.")
            )
            continue

        if args.max is not None and queried >= args.max:
            continue

        queried += 1
        try:
            raw = build_activity_elevation(activity, activity_id, zip_path, args)
        except (OSError, RuntimeError, urllib.error.URLError, zipfile.BadZipFile) as exc:
            raw = build_skip_summary(activity, activity_id, "error", str(exc))

        summaries.append(summary_from_raw(raw))
        if should_print_activity(raw, args):
            print(f"{activity_id}: {raw.get('status')} {raw.get('name')}", flush=True)

        if args.delay > 0 and raw.get("status") == "ok":
            time.sleep(args.delay)

    if args.dry_run:
        print(
            f"Dry run complete for {len(summaries)} activities; "
            f"skipped {skipped_non_outdoor} non-outdoor activities; no files written."
        )
        return 0

    ELEVATION_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "builtAt": datetime.now().isoformat(timespec="seconds"),
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "sourceIndex": str(SOURCE_INDEX),
            "sourceOriginalDir": str(ORIGINAL_DIR),
            "dataset": args.dataset,
            "apiBase": args.api_base,
            "sampleDistanceMeters": args.sample_distance,
            "maxSamples": args.max_samples,
            "minElevationChangeMeters": args.min_elevation_change,
            "cachedActivities": cached_count,
            "queriedActivities": queried,
            "skippedNonOutdoorActivities": skipped_non_outdoor,
        },
        "activities": summaries,
    }
    SUMMARY_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    ok_count = sum(1 for row in summaries if row.get("status") == "ok")
    print(f"Wrote {SUMMARY_PATH} with {ok_count} elevation summaries.")
    if skipped_non_outdoor:
        print(f"Skipped {skipped_non_outdoor} non-outdoor activities before route processing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
