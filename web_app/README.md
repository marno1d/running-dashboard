# Garmin Activity Downloader

This downloads Garmin Connect activities to local files using the `garminconnect`
Python package.

## Setup

From the repository root, run the following commands. Run all subsequent
commands in this guide from `web_app/`. The Python environment lives at the
repository root.

```sh
cd web_app
python3 -m venv ../.venv
../.venv/bin/python -m pip install -r requirements.txt
```

## Run the dashboard

Start the local dashboard server to enable the in-page **Refresh** button:

```sh
../.venv/bin/python dashboard_server.py
```

Then open `http://127.0.0.1:8000`. The Refresh button runs
`update_dashboard.py`, displays the current update step and log, and reloads the
page when the update succeeds. Only one update can run at a time. The server
listens on localhost only and the refresh endpoint can run only the fixed
dashboard updater command.

You can also open `dashboard/index.html` directly, but browsers cannot launch
local Python scripts from a static page, so the Refresh button is disabled in
that mode.

## Download everything as original Garmin files

```sh
../.venv/bin/python download_garmin_activities.py
```

The script prompts for your Garmin email, password, and MFA code if needed. It
stores reusable auth tokens in `.garmin-tokens/`, which is ignored by git, so
later runs usually do not need your password again.

Files are written under `data/activities/original/`. Garmin's "original" export
is usually a ZIP per activity containing the original uploaded FIT file. The
script also writes `data/activities/activities-index.json` with Garmin's
activity metadata.

## Useful options

```sh
# Test the flow with only five activities.
../.venv/bin/python download_garmin_activities.py --max 5

# Download GPX instead of original files.
../.venv/bin/python download_garmin_activities.py --format gpx

# Extract each original ZIP after download.
../.venv/bin/python download_garmin_activities.py --extract-original

# Re-download files that already exist.
../.venv/bin/python download_garmin_activities.py --overwrite
```

Do not put your Garmin password in shell history unless you are comfortable with
that. Prefer the interactive prompt.

## Update all dashboard data

Run the one-step updater whenever you want to pull new Garmin data and rebuild
the dashboard:

```sh
../.venv/bin/python update_dashboard.py
```

This runs, in order:

1. `download_garmin_activities.py`
2. `download_garmin_health.py`
3. `download_garmin_weather.py`
4. `download_station_weather.py`
5. `download_activity_elevation.py`
6. `build_dashboard.py`

The downloader scripts reuse `.garmin-tokens/`, so after the first login this
usually runs without asking for your Garmin password. The route elevation step
uploads sampled GPS coordinates to OpenTopoData, caches the response under
`data/activity-elevation/`, and later dashboard builds reuse that cache. The
station weather step downloads KPVU and KSLC ASOS observations from the Iowa
Environmental Mesonet, caches the raw CSV under `data/station-weather/raw/`,
and the dashboard prefers those observations for nearby outdoor runs while
falling back to Garmin weather when needed. The updater attempts the dashboard
build even if a health, weather, station weather, or elevation request has a
partial failure, then exits nonzero and prints the failed step.

Useful updater options:

```sh
# Rebuild from already-downloaded data without calling Garmin, IEM, or OpenTopoData.
../.venv/bin/python update_dashboard.py --skip-activities --skip-health --skip-weather --skip-station-weather --skip-elevation

# Re-download weather only, then rebuild the dashboard.
../.venv/bin/python update_dashboard.py --skip-activities --skip-health --skip-station-weather --skip-elevation --overwrite-weather

# Pull health and weather for a narrower date range.
../.venv/bin/python update_dashboard.py --start 2026-01-01 --end 2026-05-30

# Force all existing local downloads to be refreshed.
../.venv/bin/python update_dashboard.py --overwrite
```

## Build the progress dashboard

```sh
../.venv/bin/python build_dashboard.py
```

Open `dashboard/index.html` in your browser. The dashboard is static and reads
the generated `dashboard/data.js` file, so it does not need a server.

The first dashboard build parses FIT files to calculate easy-run HR compliance
and writes `data/activities/fit-cache.json`. Later builds reuse that cache and
should be much faster unless activity ZIP files change.

## Download route elevation

```sh
../.venv/bin/python download_activity_elevation.py
```

This parses GPS routes from the downloaded original FIT files, samples each
outdoor route activity, and looks up terrain elevation through OpenTopoData.
Indoor and virtual activities are skipped even if their FIT files contain
coordinate-like data. Cached and skipped rows are quiet by default; pass
`--verbose` if you want per-activity cache/skip output. By default it uses
`ned10m,srtm30m`, which prefers the
higher-resolution U.S. NED dataset and falls back to SRTM where NED has no
coverage. Raw sampled profiles are cached under `data/activity-elevation/raw/`, and
`data/activity-elevation/activity-elevation-summary.json` is used by the
dashboard build. If this summary is missing for an activity, the dashboard
falls back to Garmin's elevation fields.

## Download sleep, resting HR, and HRV

```sh
../.venv/bin/python download_garmin_health.py
```

By default this pulls daily data from `2025-06-01` through today, reuses
`.garmin-tokens/`, writes raw JSON under `data/health/sleep/`,
`data/health/rhr/`, and `data/health/hrv/`, and writes a compact
`data/health/daily-summary.json` with sleep hours, sleep score, resting HR,
and HRV fields.

## Download activity weather

```sh
../.venv/bin/python download_garmin_weather.py
```

By default this pulls weather for indexed activities from `2025-06-01` onward,
writes raw JSON under `data/activity-weather/raw/`, and writes
`data/activity-weather/activity-weather-summary.json`.

## Download station weather

```sh
../.venv/bin/python download_station_weather.py
```

By default this matches outdoor runs whose start point is within 15 miles of
KPVU or KSLC. It keeps merged per-station caches under
`data/station-weather/cache/`, determines which UTC dates are needed by the
indexed runs, and requests only dates that are not already covered. Existing
full-range CSV files are migrated into this cache without downloading them
again, while new response chunks remain under `data/station-weather/raw/`.
Successful responses are cached even when they contain no usable observation,
so known missing historical data is not requested repeatedly. Current-day data
uses a short provisional cache because it may still change. HTTP 429 and
temporary server errors honor `Retry-After` when supplied and otherwise use
exponential backoff. The generated
`data/station-weather/activity-station-weather-summary.json` is used by the
dashboard, which falls back to Garmin weather when no station match is
available.
