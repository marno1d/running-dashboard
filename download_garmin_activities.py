#!/usr/bin/env python3
"""Download Garmin Connect activities to local files."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


FORMAT_MAP = {
    "original": Garmin.ActivityDownloadFormat.ORIGINAL,
    "tcx": Garmin.ActivityDownloadFormat.TCX,
    "gpx": Garmin.ActivityDownloadFormat.GPX,
    "kml": Garmin.ActivityDownloadFormat.KML,
    "csv": Garmin.ActivityDownloadFormat.CSV,
}

EXTENSION_MAP = {
    "original": "zip",
    "tcx": "tcx",
    "gpx": "gpx",
    "kml": "kml",
    "csv": "csv",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Garmin Connect activities into a local folder."
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
        "--format",
        choices=sorted(FORMAT_MAP),
        default="original",
        help="Download format. 'original' is usually a ZIP containing the uploaded FIT.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data") / "activities",
        help="Output directory.",
    )
    parser.add_argument(
        "--tokenstore",
        type=Path,
        default=Path(".garmin-tokens"),
        help="Directory for reusable Garmin auth tokens.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Activities to fetch per Garmin API page. Max supported by library is 1000.",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="Stop after this many activities. Useful for a test run.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds to wait between activity downloads.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download files that already exist.",
    )
    parser.add_argument(
        "--extract-original",
        action="store_true",
        help="For --format original, also extract each downloaded ZIP safely.",
    )
    return parser.parse_args()


def prompt_mfa() -> str:
    return input("Garmin MFA code: ").strip()


def sanitize(value: Any, fallback: str = "unknown") -> str:
    text = str(value or fallback).strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return text or fallback


def activity_type(activity: dict[str, Any]) -> str:
    value = activity.get("activityType")
    if isinstance(value, dict):
        return value.get("typeKey") or value.get("typeId") or "activity"
    return value or "activity"


def activity_filename(activity: dict[str, Any], extension: str) -> str:
    activity_id = activity.get("activityId") or activity.get("id")
    start = activity.get("startTimeLocal") or activity.get("beginTimestamp") or "unknown-time"
    start = sanitize(str(start).replace(":", "").replace("T", "_"))
    kind = sanitize(activity_type(activity), "activity")
    name = sanitize(activity.get("activityName"), kind)
    return f"{start}_{kind}_{name}_{activity_id}.{extension}"


def safe_extract(zip_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = (dest / member.filename).resolve()
            if not str(target).startswith(str(dest.resolve()) + os.sep):
                raise ValueError(f"Refusing unsafe ZIP member path: {member.filename}")
        archive.extractall(dest)


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


def fetch_activities(
    client: Garmin, page_size: int, max_activities: int | None
) -> list[dict[str, Any]]:
    activities: list[dict[str, Any]] = []
    start = 0

    while True:
        remaining = None
        if max_activities is not None:
            remaining = max_activities - len(activities)
            if remaining <= 0:
                break

        limit = min(page_size, remaining) if remaining is not None else page_size
        page = client.get_activities(start, limit)
        if not page:
            break
        if not isinstance(page, list):
            raise TypeError(f"Expected Garmin activities list, got {type(page).__name__}")

        activities.extend(page)
        print(f"Fetched {len(activities)} activities...", flush=True)

        if len(page) < limit:
            break
        start += len(page)

    return activities


def write_index(out_dir: Path, activities: list[dict[str, Any]]) -> None:
    index_path = out_dir / "activities-index.json"
    index_path.write_text(json.dumps(activities, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    args = parse_args()

    if args.page_size < 1 or args.page_size > 1000:
        print("--page-size must be between 1 and 1000", file=sys.stderr)
        return 2
    if args.delay < 0:
        print("--delay must be zero or greater", file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)

    try:
        client = login(args)
        activities = fetch_activities(client, args.page_size, args.max)
        write_index(args.out, activities)

        dl_fmt = FORMAT_MAP[args.format]
        extension = EXTENSION_MAP[args.format]

        downloaded = 0
        skipped = 0
        failed = 0

        for number, activity in enumerate(activities, start=1):
            activity_id = activity.get("activityId") or activity.get("id")
            if not activity_id:
                failed += 1
                print(f"[{number}/{len(activities)}] Missing activity id; skipped")
                continue

            filename = activity_filename(activity, extension)
            path = args.out / args.format / filename
            path.parent.mkdir(parents=True, exist_ok=True)

            if path.exists() and path.stat().st_size > 0 and not args.overwrite:
                skipped += 1
                print(f"[{number}/{len(activities)}] Exists: {path}")
                continue

            try:
                data = client.download_activity(str(activity_id), dl_fmt)
                path.write_bytes(data)
                downloaded += 1
                print(f"[{number}/{len(activities)}] Downloaded: {path}")

                if args.format == "original" and args.extract_original:
                    extract_dest = args.out / "original-extracted" / str(activity_id)
                    safe_extract(path, extract_dest)
                    print(f"[{number}/{len(activities)}] Extracted: {extract_dest}")

                if args.delay:
                    time.sleep(args.delay)
            except Exception as exc:  # noqa: BLE001 - keep long backups moving.
                failed += 1
                print(
                    f"[{number}/{len(activities)}] Failed activity {activity_id}: {exc}",
                    file=sys.stderr,
                )

        print(
            f"Done. downloaded={downloaded} skipped={skipped} failed={failed} "
            f"index={args.out / 'activities-index.json'}"
        )
        return 1 if failed else 0

    except GarminConnectTooManyRequestsError as exc:
        print(f"Garmin rate limited the login/download: {exc}", file=sys.stderr)
        return 3
    except GarminConnectAuthenticationError as exc:
        print(f"Garmin authentication failed: {exc}", file=sys.stderr)
        return 4
    except GarminConnectConnectionError as exc:
        print(f"Garmin connection failed: {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
