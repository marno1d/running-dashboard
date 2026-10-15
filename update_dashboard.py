#!/usr/bin/env python3
"""Update Garmin data downloads and rebuild the local dashboard."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_START = "2025-06-01"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Garmin activity, health, weather, station weather, and route elevation data, then rebuild the dashboard."
    )
    parser.add_argument(
        "--start",
        default=DEFAULT_START,
        help="Start date for health, weather, station weather, and elevation data, YYYY-MM-DD. Defaults to 2025-06-01.",
    )
    parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="End date for health, weather, station weather, and elevation data, YYYY-MM-DD. Defaults to today.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable to use for child scripts. Defaults to the current interpreter.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download all existing activity, health, weather, station weather, and elevation files.",
    )
    parser.add_argument(
        "--overwrite-activities",
        action="store_true",
        help="Re-download existing activity files.",
    )
    parser.add_argument(
        "--overwrite-health",
        action="store_true",
        help="Re-download existing health JSON files.",
    )
    parser.add_argument(
        "--overwrite-weather",
        action="store_true",
        help="Re-download existing activity weather JSON files.",
    )
    parser.add_argument(
        "--overwrite-station-weather",
        action="store_true",
        help="Re-download existing station weather CSV files.",
    )
    parser.add_argument(
        "--overwrite-elevation",
        action="store_true",
        help="Re-download existing external activity elevation JSON files.",
    )
    parser.add_argument(
        "--skip-activities",
        action="store_true",
        help="Skip activity index and activity file downloads.",
    )
    parser.add_argument(
        "--skip-health",
        action="store_true",
        help="Skip sleep, resting HR, and HRV downloads.",
    )
    parser.add_argument(
        "--skip-weather",
        action="store_true",
        help="Skip activity weather downloads.",
    )
    parser.add_argument(
        "--skip-station-weather",
        action="store_true",
        help="Skip KPVU/KSLC station weather downloads.",
    )
    parser.add_argument(
        "--skip-elevation",
        action="store_true",
        help="Skip external route elevation lookups.",
    )
    parser.add_argument(
        "--activity-delay",
        type=float,
        default=None,
        help="Override seconds to wait between activity downloads.",
    )
    parser.add_argument(
        "--health-delay",
        type=float,
        default=None,
        help="Override seconds to wait between health API requests.",
    )
    parser.add_argument(
        "--weather-delay",
        type=float,
        default=None,
        help="Override seconds to wait between weather API requests.",
    )
    parser.add_argument(
        "--station-weather-delay",
        type=float,
        default=None,
        help="Override seconds to wait between station weather requests.",
    )
    parser.add_argument(
        "--elevation-delay",
        type=float,
        default=None,
        help="Override seconds to wait between external elevation API requests.",
    )
    return parser.parse_args()


def script(name: str) -> str:
    path = ROOT / name
    if not path.exists():
        raise FileNotFoundError(f"Missing required script: {path}")
    return str(path)


def display_command(command: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in command)


def run_step(label: str, command: list[str]) -> int:
    print(f"\n== {label} ==", flush=True)
    print(display_command(command), flush=True)
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        print(f"{label} failed with exit code {result.returncode}.", file=sys.stderr)
    return result.returncode


def main() -> int:
    args = parse_args()
    failures: list[tuple[str, int]] = []

    try:
        if not args.skip_activities:
            command = [
                args.python,
                script("download_garmin_activities.py"),
                "--format",
                "original",
            ]
            if args.overwrite or args.overwrite_activities:
                command.append("--overwrite")
            if args.activity_delay is not None:
                command.extend(["--delay", str(args.activity_delay)])
            code = run_step("Download activities", command)
            if code:
                failures.append(("Download activities", code))

        if not args.skip_health:
            command = [
                args.python,
                script("download_garmin_health.py"),
                "--start",
                args.start,
                "--end",
                args.end,
            ]
            if args.overwrite or args.overwrite_health:
                command.append("--overwrite")
            if args.health_delay is not None:
                command.extend(["--delay", str(args.health_delay)])
            code = run_step("Download health data", command)
            if code:
                failures.append(("Download health data", code))

        if not args.skip_weather:
            command = [
                args.python,
                script("download_garmin_weather.py"),
                "--start",
                args.start,
                "--end",
                args.end,
            ]
            if args.overwrite or args.overwrite_weather:
                command.append("--overwrite")
            if args.weather_delay is not None:
                command.extend(["--delay", str(args.weather_delay)])
            code = run_step("Download activity weather", command)
            if code:
                failures.append(("Download activity weather", code))

        if not args.skip_station_weather:
            command = [
                args.python,
                script("download_station_weather.py"),
                "--start",
                args.start,
                "--end",
                args.end,
            ]
            if args.overwrite or args.overwrite_station_weather:
                command.append("--overwrite")
            if args.station_weather_delay is not None:
                command.extend(["--delay", str(args.station_weather_delay)])
            code = run_step("Download station weather", command)
            if code:
                failures.append(("Download station weather", code))

        if not args.skip_elevation:
            command = [
                args.python,
                script("download_activity_elevation.py"),
                "--start",
                args.start,
                "--end",
                args.end,
            ]
            if args.overwrite or args.overwrite_elevation:
                command.append("--overwrite")
            if args.elevation_delay is not None:
                command.extend(["--delay", str(args.elevation_delay)])
            code = run_step("Download route elevation", command)
            if code:
                failures.append(("Download route elevation", code))

        code = run_step("Build dashboard", [args.python, script("build_dashboard.py")])
        if code:
            failures.append(("Build dashboard", code))

    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2

    if failures:
        print("\nCompleted with failures:", file=sys.stderr)
        for label, code in failures:
            print(f"- {label}: exit code {code}", file=sys.stderr)
        print("Dashboard build was attempted with the data available.", file=sys.stderr)
        return 1

    print("\nDone. Open dashboard/index.html in your browser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
