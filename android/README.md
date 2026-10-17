# Run Dashboard for Android

A standalone native Android app with Java screens and embedded CPython through
Chaquopy 17. Garmin sign-in and downloads run inside the APK on a background
thread. Termux is used to build and install updates.

The Android source originally developed in `run_dashboard` now lives here in the
`running-dashboard` repository. Version **0.14.0** brings the web dashboard's
data sources, calibration history, and presentation into the native Trends, Sessions, Targets, and Profile screens.

## Material 3 interface

The Java UI uses shared Material 3 color roles, consistent shapes and typography,
framework views, and outline icons. The four destinations have labelled icons
and a selected indicator. A compact app bar opens sync controls; active progress
and Pause appear above navigation. Routine status messages disappear after a
short delay, while errors stay visible. Logs remain available in sync controls
and Profile.

Profile offers **System**, **Light**, and **Dark** appearance. Chart axes,
inspectors, sheets, controls, and selection rings use the same theme. Text color
pairs and translucent chart markers are checked for contrast. Controls keep
48 dp touch targets. Buttons use their measured label widths to wrap or stack
on narrow screens and at larger font sizes. Date/adjustment chips wrap, and
segmented controls stack when equal-width segments would clip their labels.
The adaptive launcher icon includes a monochrome layer for themed Android icons;
its route mark stays within the safe area for circular and shaped masks.

Trends leads with the latest measured 5K, volume and easy-effort summaries.
The **5K / Pace / Load / Recovery** chips select a focused chart group, followed
by a three-session preview. Chart settings live in the card's overflow button;
legends use the same colors and shapes as the plotted measurements. Readable
pace/numeric ticks, lighter grid lines, and wider plotting areas reduce clutter.
Interval measurements are individual points; calibrated estimates retain their
dashed lines. Dense estimates use fewer visible symbols while keeping every
measurement available to selection and the data list. Date and trend
adjustment chips stay with Trends; Sessions has its own date chip. Targets uses
an inline Estimate / Latest trial / Custom selector, an inline custom-time field,
large pace cards, and a running-conditions bottom sheet. Equivalent race times
and calculation details expand on request. Target conditions are independent of
trend adjustments.

Sessions groups activities by date. Opening one presents a full-screen detail
page; its action menu contains category and work-lap corrections. Charts also
open full-screen, while the accessible data lists and original measurements
remain available.

## Dashboard

- A compact overview shows run volume/four-week average and time below the HR
  ceiling. Latest and best 5K trials share a tile; interval count and cross-training
  time sit below it. The underlying six web metrics are unchanged.
- Weekly load: Garmin training load (labelled TRIMP in the web dashboard), total
  time, running time, active interval percentage, and running distance.
  Cross-training contributes to total time and load. Weekly bars shade the same
  injury/rebuild period.
- Interval and easy pace: observed or intensity-normalized, with independent
  controls. Intensity normalization requires activity/work HR and resting HR.
  Original FIT interval HR/elevation and Garmin split-summary work totals use the
  same readers as the web app. Easy pace includes the rolling 25–75% band and
  trail triangles. It fits to data by default; the fixed web scale remains an option.
- **5K performance**: measured fastest continuous 5 km, calibrated interval estimates,
  and outdoor easy-speed estimates. Each series can be hidden independently.
  Easy estimates require at least two trial calibrations. Treadmill activities
  and trail activities do not contribute to outdoor easy-speed estimates.
  When an original recording is unavailable, Garmin's recorded fastest 5K split
  can be used with an explicit source label.
- **Easy effort** starts with time below the editable HR ceiling on a 0–100%
  scale, with average HR as an alternate view. Original FIT recordings are read into an aggregated
  HR histogram, then discarded. If no usable recording is available, the chart
  uses a labelled estimate from average HR.
- Targets tab: interval targets based on predicted 5K, latest measured trial, or a custom `mm:ss`
  time; short (3-minute), medium (5-minute), and long (10-minute) repetitions.
  Temperature, humidity, elevation gain/loss, equivalent race times, and an
  optional custom race distance use the web app's FVDOT and adjustment math.
- Weekly recovery: sleep, resting HR, and HRV appear in three lanes with a
  shared date axis, or one expanded metric. Latest measured weekly averages and
  day counts appear above the chart. Lines break across missing weeks; tapping a
  point opens a sheet with its value and measured-day count. Single-metric scales
  use that metric's units and precision, including resting HR and HRV.
- Sessions: search, category filters, pagination, run details, and category and
  work-lap corrections. Cross-training and strength sessions appear here too.
  Trends also includes the web's recent-sessions preview with category filtering,
  pace, distance, active HR, HR compliance, elevation, and temperature.

The date selector includes All (since June 2025), 7/30/45/90/180 days, one year,
18/24 calendar months, and custom dates. Pace defaults to min/mile; min/km is
available in Profile. The first launch of 0.11 changes an All-range selection to
90 days; an existing specific/custom selection is preserved. Full-history
calibration and saved data stay enabled. Expanded charts support pinch zoom and
horizontal date panning; vertical swipes scroll the page even after zooming.
Dashboard previews allow taps and scrolling without intercepting pinch gestures.

Every chart has one **Explore chart** action. Its full-screen view includes
**View data**, with multiline rows that keep values and source descriptions
readable. Tapping a point highlights it and opens a details sheet, with
**Open session** as a separate action.
Inspectors distinguish recorded and displayed pace, measured 5Ks and estimates,
and recorded HR versus average-HR estimates. Weekly inspectors show calendar-week
totals and can open all of that week's sessions from the cache, including dates
outside a custom display window. Reset/date-application actions appear only while
zoomed; **Use visible dates across app** changes the dashboard's shared range.
Chart labels follow the system font scale, and text/marker shapes accompany colour.
The data lists provide a screen-reader-friendly alternative to canvas gestures.

Trends has one **Adjustments** chip with its active count. Interval targets
show three prominent pace cards; the 5K basis is inline and conditions open in a sheet.
Equivalent race times and calculation explanations expand on request. Session
source/recording details are collapsed by default.

Elevation and temperature adjustments can be enabled independently. Recorded
paces are normalized toward flat/cool conditions; target paces are adjusted in
the opposite direction for the conditions entered. Missing measurements remain
unadjusted.

## Sync and terrain downloads

Open **Sync** in Profile for **Sync now**, the last sync-check time, and a short
completion status. Expand **Details** for download counts and
**Download / resume terrain**.
This enables terrain and works through missing outdoor routes, newest first,
without waiting for recovery or weather downloads. Coordinates are sent only to
OpenTopoData; original FITs and GPS profiles are discarded after aggregation.
Sync runs in an Android `dataSync` foreground service, so downloads continue
when you switch apps, close the dashboard screen, or turn the display off. Allow
notifications to see progress and **Pause** outside the app. Tapping the
notification returns to the current sync without starting a second download.
A bounded partial wake lock keeps the worker running without keeping the display
on. Android and device battery controls can still stop a service; this is not a
guarantee of unlimited execution.

The header's **Pause** button stops after the current request. Completed activity
windows and individual metrics are committed immediately; another download
resumes missing work. An interrupted sync is remembered and resumes automatically
when the app next opens with a saved Garmin session. If Garmin or the connection
stopped a request, automatic resume waits at least five minutes before trying
again; **Sync now** can retry sooner. A deliberate **Pause** stays paused until
you choose **Sync now** or **Download / resume terrain**. Service timeouts also
preserve unfinished work; the service stops before its six-hour Android limit.
Reopening during a sync attaches to the existing job. Python and SQLite work
from the screen and service share one worker, avoiding concurrent cache access.
Coverage counts show ready, skipped (no usable route/elevation), and pending
terrain separately.
Refresh fills other missing downloads and rechecks the most recent three days.
Recovery summaries are downloaded in batches of up to 28 days, newest first,
using Garmin’s sleep, resting-HR, and HRV range readers. Missing rows or
unsupported range responses fall back to the daily readers. Saved days are
reused, and Refresh rechecks only the most recent three days. Each completed
metric is committed immediately, including during a batch. Long activity
listings commit in windows of at most 90 days, after every page for that window
succeeds.

Connection failures get at most two retries. Authentication/rate limits pause
Garmin work and preserve saved charts. Each original recording is downloaded at
most once per sync for its requested FIT/terrain metrics; failure of one parser
does not discard the others. Renaming a workout or updating its training load
keeps its saved terrain; changes to recording inputs invalidate derived data.

Terrain requests are paced across chunks, routes, and app restarts, with a local
900-request daily budget, service `Retry-After` handling, and cooldowns after
repeated failures. Unfinished routes stay pending for a later resume. These
settings leave headroom under the [public API limits](https://www.opentopodata.org/#public-api).
A route interrupted mid-query is fetched again when resumed; sampled GPS and
partial elevation profiles are never persisted.

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
snapshot's latest available date. Web classification mode now follows the web
builder's record and weekly precision before calculating charts, including
interval HR/elevation fallbacks. Cached original measurements stay unrounded.
The native fastest-5K reader preserves its stricter
handling of resets, pauses, and interpolated segment boundaries.

Automated comparisons execute the web JavaScript against synthetic data for
FVDOT, equivalent races, conditions, interval/easy predictions, intensity modes,
and easy-pace bands. Source/cache tests cover station precedence and expiry,
terrain aggregation, full-history calibration, classification, and overrides.
The older 20-run shared-input replay caught and now covers the leading-week
All-range regression. Its available pace/lap checks agree within rounding. It
contains no HR, recovery, weather, terrain, or recorded 5K inputs, so it does not
replace a current on-device comparison. A consented local full-history snapshot
also exercises HR/recovery, weather, recorded trials, and all eight adjustment
combinations. That comparison caught and now covers missing-daily-RHR fallbacks,
which previously could omit intensity points, and precision differences that
changed model slopes. Terrain needs a separate export with that source enabled;
private snapshots and comparison reports remain outside version control.

## Build on this phone

From `running-dashboard/android`:

```sh
python -m venv .venv
.venv/bin/pip install --cache-dir .tools/pip-cache -r requirements.txt
python scripts/bootstrap.py
python scripts/build_apk.py
```

The ignored `.venv` and `.tools` directories live inside `android/`; the build
does not depend on another project folder. Fresh checkouts create those
directories with the commands above. Back up `.tools/debug.jks` separately for
future updates signed with the same key; do not commit it. A replacement key
cannot update an installed copy signed with the old key.

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
python scripts/check_sync.py
python scripts/check_material.py
python scripts/check_runtime.py
```

Build before running the Java and packaged-runtime checks. Node is needed for
the comparisons against the web app; those tests are skipped when it is unavailable. The runtime
probe checks the APK's packaged Python dependencies and Garmin's public sign-in
page without signing into an account. App launch, Garmin account sign-in, and
real-device interaction need an on-device check after installation. Check all
four tabs in both themes and with larger system text, plus all four Trends
groups and the home-screen icon (including themed icons), including custom target
validation, scrolling conditions, session corrections, and expanded chart data.
For sync,
start a download, switch apps or lock the phone, and reopen via its notification;
progress should continue with one job. Pause from the notification and reopen to
confirm it stays paused. An interrupted process should resume missing work on
reopen, subject to the retry cooldown. A force-stop prevents work until the app
is opened again; no boot receiver restarts downloads.

## Sync and storage

Profile controls full history, health, Garmin/station weather, original FIT
metrics, and terrain lookups. The first
sync can take time: it fetches historical activities, missing laps/recordings,
and each selected day of recovery data. Subsequent syncs reuse saved history;
Refresh checks the latest three calendar days for activity changes and health
updates. Older edits/backdated activities are not found by that recent refresh.
Failed optional downloads retain available charts and show a retry warning.
Garmin authentication/rate limits pause further optional requests in that sync
while still returning charts from saved measurements. Opening the app or changing
a chart setting first renders cached data without network calls. If dates are
missing from an existing cache, Refresh fills them; a fresh empty account starts
its first download automatically.

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

## Compare current saved data with the web app

Run from `android/`:

```sh
.venv/bin/python scripts/receive_comparison.py
```

Open the printed page on this phone. Install its current APK update and use
**Open terrain sync** to download terrain. Then return and tap
**Share saved dashboard for comparison**. Android asks before sharing
saved activity titles, metrics, HR, recovery, weather/elevation summaries,
settings, and calculated chart values. Credentials, session tokens, and GPS
routes are excluded by a shared allowlist. Exporting does not download anything.

The receiver binds only to localhost and accepts the capability URL printed for
that session. It expires after 30 minutes. Data and reports are written only to
the ignored `.state/` directory with owner-only file permissions. The report
also appears on the same page after receipt.

The comparison uses the actual web Python builder and JavaScript against the
same saved inputs and explicit date bounds. It checks the active configuration
plus eight combinations of observed/intensity pace and elevation/temperature
adjustments. It lists numeric deltas and separates small rounding effects from
larger differences. Manual category/lap overrides and native per-rep plots may
intentionally differ from the web app. Missing metric families are not validated
by an empty chart, and the report includes data-coverage counts.

To rerun a received snapshot:

```sh
.venv/bin/python scripts/compare_dashboard.py .state/comparison-snapshot.json --matrix
```

To check calculations from edited source against the same saved inputs, add
`--replay-current` and use `--out .state/comparison-candidate.md`. The default
compares the installed app's exported results for the active configuration;
replay mode recalculates that configuration without overwriting the snapshot.

This validates downloaded inputs and calculated results; it does not independently
repeat live weather/terrain requests or reparse original FIT archives which the
app has already discarded. The web builder's optional `fit_metrics` input lets
the comparison supply those saved aggregates without changing normal web builds.
