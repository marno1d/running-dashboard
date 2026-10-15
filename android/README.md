# Run Dashboard for Android

A standalone native Android app with Java screens and embedded CPython through
Chaquopy 17. Garmin sign-in and downloads run inside the APK on a background
thread. Termux is used to build and install updates.

The Android source originally developed in `run_dashboard` now lives here in the
`running-dashboard` repository. Version **0.7.0** brings the web dashboard's
data sources, calibration history, and presentation into the native Trends, Sessions, and Profile screens.

## Dashboard

- The web app's six summary cards: run volume and four-week average, easy HR
  discipline, best and latest 5K trials, interval count, and cross-training time.
- Weekly load: Garmin training load (the web dashboard's TRIMP metric), total
  time, running time, active interval percentage, and running distance.
  Cross-training contributes to total time and load. Weekly bars use the web
  colours and shade the same injury/rebuild period.
- Interval and easy pace: observed or intensity-normalized, with independent
  controls. Intensity normalization requires activity/work HR and resting HR.
  Original FIT interval HR/elevation and Garmin split-summary work totals use the
  same readers as the web app. Easy pace includes the rolling 25–75% band, trail
  triangles, and the web's 7:00–10:00 min/mile default scale.
- 5K chart: measured fastest continuous 5 km, calibrated interval estimates,
  and outdoor easy-speed estimates. Each series can be hidden independently.
  Easy estimates require at least two trial calibrations. Treadmill activities
  and trail activities do not contribute to outdoor easy-speed estimates.
  When an original recording is unavailable, Garmin's recorded fastest 5K split
  can be used with an explicit source label.
- Easy HR control: average HR against the editable ceiling, with colours based
  on recorded time below it. Original FIT recordings are read into an aggregated
  HR histogram, then discarded. If no usable recording is available, the chart
  uses a labelled estimate from average HR.
- Interval targets: predicted 5K, latest measured trial, or a custom `mm:ss`
  time; short (3-minute), medium (5-minute), and long (10-minute) repetitions.
  Temperature, humidity, elevation gain/loss, equivalent race times, and an
  optional custom race distance use the web app's FVDOT and adjustment math.
- Weekly recovery: sleep, resting HR, and HRV appear in three lanes with a
  shared date axis. Missing days are excluded from averages; tap a measurement
  for its value and measured-day count.
- Sessions: search, category filters, pagination, run details, and category and
  work-lap corrections. Cross-training and strength sessions appear here too.
  Trends also includes the web's recent-sessions preview with category filtering,
  pace, distance, active HR, HR compliance, elevation, and temperature.

The date selector includes All (since June 2025), 7/30/45/90/180 days, one year,
18/24 calendar months, and custom dates. Pace defaults to min/mile; min/km is
available in Profile. Charts support pinch zoom, pan when zoomed, and reset.
Use **Filter to visible dates** after zooming to apply a chart's date window to
the whole dashboard. Range, adjustments, refresh status, and update-log access
stay above the scrolling content.

Elevation and temperature adjustments can be enabled independently. Recorded
paces are normalized toward flat/cool conditions; target paces are adjusted in
the opposite direction for the conditions entered. Missing measurements remain
unadjusted.

## Shared sources and remaining differences

The APK packages the repository's actual `build_dashboard.py`,
`download_station_weather.py`, and `download_activity_elevation.py` modules.
Classification, split-summary/FIT interval metrics, station matching, terrain
sampling and lookup, and weather merging use those same implementations.

- **Station weather** prefers KPVU/KSLC ASOS observations within 15 miles and
  90 minutes of the activity midpoint, with per-field Garmin fallback. Station
  dates are cached, including successful empty responses. Current-day results
  expire after six hours and are refreshed once they become historical.
- **Terrain elevation** uses the web's 75 m sampling, up to 500 samples, and
  `ned10m,srtm30m` datasets. It includes active-work elevation. Enable it explicitly
  in Profile: the provider receives sampled GPS coordinates. Android retains
  aggregate elevation only; it does not save the route or raw terrain profile.
- **Full history** is enabled by default. Sync covers June 2025 onward (or an
  earlier selected start); prediction calibration and target selection use that
  context even when the visible date range is short. Custom ranges include
  overlapping whole calendar weeks, matching the web's weekly summaries.
- **Web classification** is the default, including Easy Long and the existing
  injury/rebuild dates. Profile can restore the original Android suggestions.
  Manual category and lap corrections continue to take precedence.

Native gestures, phone layout, extra date windows, and run corrections remain
Android-specific. Rolling day windows are anchored to today rather than the web
snapshot's latest available date. Very small numeric differences can remain
because web output rounds records before chart calculations; Android retains
unrounded input. The native fastest-5K reader also preserves its stricter
handling of resets, pauses, and interpolated segment boundaries.

Automated comparisons execute the web JavaScript against synthetic data for
FVDOT, equivalent races, conditions, interval/easy predictions, intensity modes,
and easy-pace bands. Source/cache tests cover station precedence and expiry,
terrain aggregation, full-history calibration, classification, and overrides.
Real-account source availability and the new layouts still need on-device use.

## Build on this phone

From `running-dashboard/android`:

```sh
python -m venv .venv
.venv/bin/pip install --cache-dir .tools/pip-cache -r requirements.txt
python scripts/bootstrap.py
python scripts/build_apk.py
```

The existing phone setup uses ignored local `.venv` and `.tools` links to the
original project's dependencies and development signing key. Fresh checkouts
create those directories with the commands above. Keep `.tools/debug.jks` for
future updates signed with the same key; do not commit it.

The ARM64 Termux build uses JDK 21, Android's Java API, aapt, D8, and Chaquopy's
embedded runtime without requiring desktop Gradle binaries. The signed output
is `build/run-dashboard.apk`; building also verifies its signature. It targets
ARM64 Android 8+ and preserves the existing app package, so the same signing
key allows updating the installed app without clearing its data.

Install through Android's package installer:

```sh
python scripts/install_apk.py
```

This opens a local APK download in the phone's browser, available for 15 minutes.
Open the completed download and accept Android's installation prompt.

## Verification

```sh
.venv/bin/python -m unittest discover -s tests -v
python scripts/check_chart.py
python scripts/check_runtime.py
```

Build before running the last two commands. Node is needed for the comparisons
against the web app; those tests are skipped when it is unavailable. The runtime
probe checks the APK's packaged Python dependencies and Garmin's public sign-in
page without signing into an account. App launch, Garmin account sign-in, and
real-device interaction need an on-device check after installation.

## Sync and storage

Profile controls full history, health, Garmin/station weather, original FIT
metrics, and terrain lookups. The first
sync can take time: it fetches historical activities, missing laps/recordings,
and each selected day of recovery data. Subsequent syncs reuse saved history;
Refresh checks the latest three calendar days for activity changes and health
updates. Older edits/backdated activities are not found by that recent refresh.
Failed optional downloads retain available charts and show a retry warning.
Garmin authentication/rate limits pause further optional requests in that sync
while still returning charts from saved measurements.

A versioned, app-private SQLite cache contains summaries, lap metrics, fastest
5K segments, daily recovery values, weather, and aggregate HR histograms. It
retains no GPS coordinates, original archives, passwords, or authentication
tokens. Only a nearby station match/distance, public observations, and aggregate
terrain values are retained for external sources. The upgrade refreshes older cached summary coverage once to add GMT start
times, station matching, and split summaries. Sign-out clears account data and category/lap corrections.

Passwords are not saved. Session tokens use AES-GCM with Android Keystore and
app-private preferences. Android backup is disabled. Garmin requests use the
unofficial `garminconnect` library; MFA codes are supported, interactive CAPTCHA
and Garmin China accounts are not. See `THIRD_PARTY_NOTICES.md` for dependencies.

`../common/garmin_health.py` and `garmin_weather.py` normalize Garmin responses
for both apps. The build includes these modules in the APK's Python assets;
they are not duplicated in the Android source.

For optional development sample inspection, `python scripts/receive_sample.py --open` opens the existing in-app consent prompt. Samples exclude credentials,
location, and heart rate and are stored only in the ignored `.state` directory.
