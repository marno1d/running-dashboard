#!/usr/bin/env python3
"""Download daily Garmin health data: sleep, resting HR, and HRV."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


DASHBOARD_START = date(2025, 6, 1)
DEFAULT_OUT = Path("data") / "health"
DEFAULT_TOKENSTORE = Path(".garmin-tokens")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Garmin sleep, resting HR, and HRV data."
    )
    parser.add_argument(
        "--email",
        default=os.getenv("GARMIN_EMAIL"),
        help="Garmin account email. Defaults to GARMIN_EMAIL or interactive prompt.",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("GARMIN_PASSWORD"),
        help="Garmin account password. Defaults to GARMIN_PASSWORD or secure prompt.",
    )
    parser.add_argument(
        "--start",
        default=DASHBOARD_START.isoformat(),
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
        "--tokenstore",
        type=Path,
        default=DEFAULT_TOKENSTORE,
        help="Directory for reusable Garmin auth tokens.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Seconds to wait between Garmin API requests.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download files that already exist.",
    )
    parser.add_argument(
        "--kinds",
        nargs="+",
        choices=["sleep", "rhr", "hrv"],
        default=["sleep", "rhr", "hrv"],
        help="Health data kinds to download.",
    )
    return parser.parse_args()


def parse_date(value: str, name: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{name} must be YYYY-MM-DD") from exc


def date_range(start: date, end: date) -> list[date]:
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def prompt_mfa() -> str:
    return input("Garmin MFA code: ").strip()


def login(args: argparse.Namespace) -> Garmin:
    tokenstore = args.tokenstore.expanduser()
    tokenstore.mkdir(parents=True, exist_ok=True)

    email = args.email
    password = args.password

    if not email and not any(tokenstore.iterdir()):
        email = input("Garmin email: ").strip()
    if not password and not any(tokenstore.iterdir()):
        password = getpass.getpass("Garmin password: ")

    client = Garmin(email=email, password=password, prompt_mfa=prompt_mfa)
    client.login(str(tokenstore))
    return client


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


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


def download_kind(
    client: Garmin,
    kind: str,
    day: str,
) -> Any:
    calls: dict[str, Callable[[str], Any]] = {
        "sleep": client.get_sleep_data,
        "rhr": client.get_rhr_day,
        "hrv": client.get_hrv_data,
    }
    return calls[kind](day)


def main() -> int:
    args = parse_args()
    try:
        start = parse_date(args.start, "--start")
        end = parse_date(args.end, "--end")
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    if end < start:
        print("--end must be on or after --start", file=sys.stderr)
        return 2
    if args.delay < 0:
        print("--delay must be zero or greater", file=sys.stderr)
        return 2

    days = date_range(start, end)
    args.out.mkdir(parents=True, exist_ok=True)

    try:
        client = login(args)
        downloaded = 0
        skipped = 0
        failed = 0
        summaries: list[dict[str, Any]] = []

        for index, current_day in enumerate(days, start=1):
            day = current_day.isoformat()
            raw_by_kind: dict[str, Any] = {}

            for kind in args.kinds:
                path = args.out / kind / f"{day}.json"
                if path.exists() and not args.overwrite:
                    try:
                        raw_by_kind[kind] = json.loads(path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        raw_by_kind[kind] = None
                    skipped += 1
                    continue

                try:
                    data = download_kind(client, kind, day)
                    write_json(path, data)
                    raw_by_kind[kind] = data
                    downloaded += 1
                    if args.delay:
                        time.sleep(args.delay)
                except Exception as exc:  # noqa: BLE001 - keep long pulls resumable.
                    failed += 1
                    raw_by_kind[kind] = None
                    print(f"[{day}] Failed {kind}: {exc}", file=sys.stderr)

            summaries.append(merged_summary(day, raw_by_kind))
            if index % 10 == 0 or index == len(days):
                print(
                    f"[{index}/{len(days)}] through {day} "
                    f"downloaded={downloaded} skipped={skipped} failed={failed}",
                    flush=True,
                )

        write_json(
            args.out / "daily-summary.json",
            {
                "builtAt": datetime.now().isoformat(timespec="seconds"),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "kinds": args.kinds,
                "days": summaries,
            },
        )
        print(
            f"Done. downloaded={downloaded} skipped={skipped} failed={failed} "
            f"summary={args.out / 'daily-summary.json'}"
        )
        return 1 if failed else 0

    except GarminConnectTooManyRequestsError as exc:
        print(f"Garmin rate limited the request: {exc}", file=sys.stderr)
        return 3
    except GarminConnectAuthenticationError as exc:
        print(f"Garmin authentication failed: {exc}", file=sys.stderr)
        return 4
    except GarminConnectConnectionError as exc:
        print(f"Garmin connection failed: {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
