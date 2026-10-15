#!/usr/bin/env python3
"""Download Garmin per-activity weather data."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from garmin_weather import first_number, find_by_keys, summarize_weather


from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


ACTIVITY_INDEX = Path("data/activities/activities-index.json")
DEFAULT_OUT = Path("data") / "activity-weather"
DEFAULT_TOKENSTORE = Path(".garmin-tokens")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Garmin activity weather JSON.")
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
        "--activity-id",
        action="append",
        default=[],
        help="Activity id to fetch. Can be repeated. Defaults to activities from the index.",
    )
    parser.add_argument(
        "--start",
        default="2025-06-01",
        help="Only fetch indexed activities on or after this date, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="Only fetch indexed activities on or before this date, YYYY-MM-DD.",
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
        "--summary-only",
        action="store_true",
        help="Only rebuild the summary from cached raw weather files; do not log in or download.",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="Stop after this many activities. Useful for testing.",
    )
    return parser.parse_args()


def parse_date(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"{name} must be YYYY-MM-DD") from exc


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


def load_activities(start: str | None, end: str | None) -> list[dict[str, Any]]:
    if not ACTIVITY_INDEX.exists():
        raise FileNotFoundError(f"Missing {ACTIVITY_INDEX}. Run download_garmin_activities.py first.")
    activities = json.loads(ACTIVITY_INDEX.read_text(encoding="utf-8"))
    selected = []
    for activity in activities:
        activity_id = activity.get("activityId") or activity.get("id")
        day = str(activity.get("startTimeLocal") or "")[:10]
        if not activity_id or not day:
            continue
        if start and day < start:
            continue
        if end and day > end:
            continue
        selected.append(activity)
    return sorted(selected, key=lambda row: row.get("startTimeLocal") or "", reverse=True)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def find_value(data: Any, needles: tuple[str, ...]) -> Any:
    if isinstance(data, dict):
        for key, value in data.items():
            normalized = key.lower().replace("_", "").replace("-", "")
            if any(needle in normalized for needle in needles):
                if not isinstance(value, (dict, list)):
                    return value
        for value in data.values():
            found = find_value(value, needles)
            if found is not None:
                return found
    elif isinstance(data, list):
        for value in data:
            found = find_value(value, needles)
            if found is not None:
                return found
    return None


def main() -> int:
    args = parse_args()
    try:
        start = parse_date(args.start, "--start")
        end = parse_date(args.end, "--end")
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.delay < 0:
        print("--delay must be zero or greater", file=sys.stderr)
        return 2

    try:
        if args.activity_id:
            indexed = {str(row.get("activityId") or row.get("id")): row for row in load_activities(None, None)}
            activities = [
                indexed.get(str(activity_id), {"activityId": str(activity_id)})
                for activity_id in args.activity_id
            ]
        else:
            activities = load_activities(start, end)
        if args.max is not None:
            activities = activities[: args.max]

        raw_dir = args.out / "raw"
        client = None if args.summary_only else login(args)
        downloaded = 0
        skipped = 0
        failed = 0
        summaries: list[dict[str, Any]] = []

        for index, activity in enumerate(activities, start=1):
            activity_id = str(activity.get("activityId") or activity.get("id") or "")
            path = raw_dir / f"{activity_id}.json"

            if path.exists() and (args.summary_only or not args.overwrite):
                try:
                    weather = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    weather = None
                skipped += 1
            elif args.summary_only:
                weather = None
                skipped += 1
            else:
                try:
                    if client is None:
                        raise RuntimeError("Garmin client was not initialized.")
                    weather = client.get_activity_weather(activity_id)
                    write_json(path, weather)
                    downloaded += 1
                    if args.delay:
                        time.sleep(args.delay)
                except Exception as exc:  # noqa: BLE001 - keep long pulls resumable.
                    failed += 1
                    weather = None
                    print(f"[{activity_id}] Failed weather: {exc}", file=sys.stderr)

            summaries.append(summarize_weather(activity, weather))
            if index % 25 == 0 or index == len(activities):
                print(
                    f"[{index}/{len(activities)}] downloaded={downloaded} "
                    f"skipped={skipped} failed={failed}",
                    flush=True,
                )

        write_json(
            args.out / "activity-weather-summary.json",
            {
                "builtAt": datetime.now().isoformat(timespec="seconds"),
                "start": start,
                "end": end,
                "activityCount": len(activities),
                "activities": summaries,
            },
        )
        print(
            f"Done. downloaded={downloaded} skipped={skipped} failed={failed} "
            f"summary={args.out / 'activity-weather-summary.json'}"
        )
        return 1 if failed else 0

    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2
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
