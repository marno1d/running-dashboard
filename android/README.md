# Run Dashboard for Android

A standalone native Android app with Java screens and embedded CPython through
Chaquopy 17. Garmin sign-in and downloads run inside the APK on a background
thread. Termux is used to build and install updates.

The Android source originally developed in `run_dashboard` now lives here in the
`running-dashboard` repository. Version **0.22.1** brings the web dashboard's
data sources, calibration history, and presentation into the native Targets, Trends, Sessions, and Profile screens, in that navigation order. Targets is the launch and Back destination.

## Material 3 interface

The Java UI uses shared Material 3 color roles, consistent shapes and typography,
framework views, and outline icons. The four destinations have labelled icons
and a selected indicator. A compact app bar opens sync controls; active progress
and Pause appear above navigation. Routine status messages disappear after a
short delay, while errors stay visible. Logs remain available in sync controls
and Profile.

Pull down and release at the top of Trends, Sessions, or Targets to sync.
A circular indicator follows the pull and gives a small haptic cue when ready;
releasing early cancels. It uses the same foreground sync and saved-data cache
as **Sync now**, and stays disabled while another operation is running or before
sign-in. Upward scrolling, horizontal chart gestures, and multi-touch do not
trigger it. Profile keeps its explicit sync controls to protect settings edits.

Profile offers **System**, **Light**, and **Dark** appearance. Chart axes,
inspectors, sheets, controls, and selection rings use the same theme. Text color
pairs and translucent chart markers are checked for contrast. Controls keep
48 dp touch targets. Buttons use their measured label widths to wrap or stack
on narrow screens and at larger font sizes. Date/adjustment chips wrap, and
segmented controls stack when equal-width segments would clip their labels.
The adaptive launcher icon includes a monochrome layer for themed Android icons;
its route mark stays within the safe area for circular and shaped masks.

Trends leads with the latest measured 5K, volume and easy-effort summaries.
The **5K / Pace / Load / Recovery** chips select a focused chart group.
Activity browsing lives in the Sessions tab. Chart settings live in the card's overflow button;
legends use the same colors and shapes as the plotted measurements. Tap a legend
item to hide or restore its series. Hidden labels stay visible, muted and struck
through, with dimmed symbols and checkable accessibility states. The 5K, interval
pace, road/trail easy pace, and easy-effort HR buckets all support this in cards
and expanded charts. Choices are saved per chart and synchronized between both
views, including the existing 5K series switches. Toggling uses saved plot data,
keeps the axes and zoom stable, and requires no recalculation or download. Hidden
series also leave hit testing, the data list, and related easy-pace shading;
restoring a legend item brings them back. All series can be hidden without
removing their legend controls. Drag horizontally across a chart to scrub the
first enabled series in legend order. The guide follows fractional dates smoothly;
the highlight and date/series/value bubble snap to actual measurements
and remain after release. The bubble follows the cursor horizontally but stays
at a fixed vertical position in a reserved header above the axes. Header space
scales with system text size and is added to the chart height, keeping the plotted
area the same size and preventing a layout jump when scrubbing begins. This
applies to cards, expanded charts, load, and Recovery. Hiding the active series reselects the next enabled
legend entry at the cursor date. An enabled series with no measurements in view
shows an empty readout rather than borrowing another series' values. Measurements
outside the zoomed window or fixed pace scale are excluded.
Weekly load scrubs its bars; Recovery scrubs the metric lane where the drag starts,
preserving missing-week gaps and reporting the actual measured week and day count.
Readable
pace/numeric ticks, lighter grid lines, and wider plotting areas reduce clutter.
Interval pace always shows one session average per workout, calculated from
total work time divided by total work distance. The individual-repetition view
and its Trends/Profile controls are removed; older rep preferences also use
session averages. Expanded charts, scrubbing, data lists, adjustments, predictions
and session cards all use the session's work metrics. Work-lap corrections still
choose which laps contribute to that average. Calibrated estimates retain their
dashed lines. Dense estimates use fewer visible symbols while keeping every
measurement available to selection and the data list. Condition adjustments
share one setting across Trends and Sessions, with date and adjustment controls
available above both screens. Targets uses
an inline Estimate / Latest trial / Custom selector, an inline custom-time field,
three compact pace tiles, and inline condition fields with automatic saving. The extra
 “Your next interval session” heading is removed. Equivalent race times
stay expanded, with distance, pace and time sharing each row. The custom row's
distance cell is directly editable, with pace and time beside it in the same row.
It uses the selected miles/km units, saves valid edits automatically, and refreshes
predictions after a short typing pause. Clearing it blanks that row's prediction.
The field and keyboard stay in place while results update, and there is no
separate entry row or duplicate custom-distance result.
The About these
targets card is removed. Target conditions are independent of
trend adjustments.

Sessions has one newest-first list with dates beside the category on each card,
search, category filters, and pagination. Dates show the month and day, adding
the year for older years; separate date headings are removed. After **All**,
filters start **Short, Medium, Long, Easy, Easy Long**, then the remaining types,
with **Needs review** last. Compact cards lead with distance, whole-session pace,
duration, and average HR. Running intervals add a smaller tinted row containing
total work distance, pace, work time, and average work HR, excluding recoveries.
All four values align with the corresponding whole-session columns; the separate
Work label is removed. Missing work metrics stay blank (—), and accessibility
descriptions identify the work values explicitly. Both rows use one
measured grid, including when larger text needs two columns. Elevation gain and
loss, saved HR-compliance summaries, and temperature share a compact footer
with the session name directly after temperature. The name uses the remaining
space and ellipsizes; conditions can wrap for larger system text. Measured 5K
times sit in the same header. Padding is compact, and the search
area has no duplicate heading. Metric columns use measured text widths to fall
back from four columns to two or one with narrow screens and larger system text.
The former Trends recent-sessions preview is merged into this list.
Opening one presents a full-screen detail
page with a north-up GPS route outline and distinct start/finish markers;
its action menu contains category and work-lap corrections. The route loads from
the Garmin original recording on first opening, then uses an app-private cached
outline for offline reopening. Loading happens off the UI thread and keeps the
rest of the session readable; failures offer Retry and indoor/no-GPS sessions
show an empty state. The preview saves a bounded relative shape, with no geographic
origin, timestamps, or original FIT file; route suggestions separately retain
coarse location cells in the private cache. Outlines and cells are excluded from comparison
and training-sample exports, cleared on sign-out, and invalidated with changed
recordings. No basemap, map API key, or third-party map requests are involved. Charts also
open full-screen, with accessible data lists for the currently visible series
and original measurements available through point/session details.

The route reference browser lists saved running sessions newest first, with the
same search and category filters as Sessions. Each row includes a small north-up
GPS outline. Cached outlines appear immediately; missing visible previews load
one at a time while scrolling, without downloading the whole list. A failed
preview pauses automatic downloads and offers Retry GPS; recordings without GPS
show No GPS. List shapes use fewer points while preserving recording gaps.
Tapping a session opens **Confirm route reference**. This compares GPS against
that prospective selection, independently of the route's existing reference,
and lists longer matching recordings by distance, longest first. Matches must
cover at least 85% of the selected path's coarse GPS cells, allowing extensions
well beyond the original route without matching an isolated path crossing. It checks up
to five unchecked longer recordings initially; **Check 5 more longer recordings**
continues from the largest unchecked ones and reuses previous checks. The screen
shows how many longer recordings remain unchecked. **Keep original selection**
and **Use this longer session** explicitly save the reference; going back leaves
the existing reference intact. GPS matching and previews use the private Garmin
cache, with no external map service.

Profile's Workouts card shows a compact readout of easy durations, interval
repetitions/work time/warm-up/cooldown, and walking pace. **Edit workouts** opens
a scrollable overlay containing the editable fields and **Use latest session**
actions. Valid edits still save automatically. **Done** or dismissing the
overlay refreshes the compact readout while keeping the Profile scroll position.

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
  The 5K basis has its own saved historical adjustments and HR-normalization
  mode, independent of Trends and Sessions. Predicted estimates default to both
  elevation and weather adjustments on. On upgrade, the current 5K chart's HR
  mode is copied once; later changes stay independent. Latest Trial has separate
  elevation/weather choices, initially copied from the existing chart flags,
  and never uses HR normalization. Custom uses the entered time directly.
  The one-tap Adjustments control toggles both corrections; its overflow edits
  them individually. The compact basis card puts the 5K time in its header,
  combines basis status and date, and places an HR on/off chip beside Adjustments.
  Both controls retain 48 dp touch targets and wrap when enlarged text needs room.
  The same historical corrections apply to the estimate's trial calibration.
  Conditions for the next workout remain a separate step and apply once to the
  resulting base target paces. Changing those conditions never changes the 5K basis.
  Temperature, humidity, and elevation gain/loss **in feet per mile** are editable directly in the tab,
  without a menu or Apply button. Valid edits save immediately; target paces update
  after a short typing pause without replacing the fields or dismissing the keyboard.
  Every condition field has a Done action. Done, Back, or tapping outside the
  fields parks focus on the page and dismisses the keyboard; tapping a different
  field still moves directly between inputs. Short/Medium/Long targets share a
  compact row, with work duration, pace and units visible in each tile. The tiles
  wrap when a narrow screen or enlarged system text needs more room.
  The four compact fields wrap to fewer columns when larger text needs room.
  Partial or invalid numbers leave the previous complete conditions intact and
  dim the paces until editing finishes. Manual temperature/humidity edits record
  a one-hour hold for weather autofill; changing elevation does not extend it.
  **Reset** restores 45 °F, blank humidity, and zero gain/loss in one tap, dismisses
  editing, and holds those defaults for one hour. Local weather can override the hold.
  On upgrade, old elevation totals are retained as a visible note and the new
  per-mile fields start at zero; old totals are never reinterpreted as rates.
  Choosing a route, resetting, or manually editing a rate clears the note.
  **Routes** beside Local weather now selects only a route. Shape, surface and one
  full reference are configured separately in Profile. Route mode hides the manual
  elevation-rate inputs; **Manual** restores them without losing their saved values.
  Weather edits keep route selection. Every workout and race is laid onto the
  selected route's measured distance/elevation profile, rather than applying one
  average gain/loss rate to all distances. Tap an interval/easy target or race row
  for its totals and, for workouts, the phase-by-phase breakdown. Interval tiles
  show work-only elevation. On a selected route, Easy and Easy long predictions
  use its Road or Trail 128 bpm model. Without sufficient matching easy/HR history,
  those plans show an explicit error; recorded reference pace is not substituted.
  In manual mode, independent **Road** and **Trail** easy-pace estimates
  target an average HR of **128 bpm** in the entered conditions. They work without
  a 5K trial or interval prediction. Each uses only its own outdoor easy/easy-long
  sessions: up to 24 runs from the last 90 days, at least ten minutes long with
  valid pace and HR. At least five sessions are required; treadmills, virtual runs,
  and interval workouts are excluded. Historical weather and elevation corrections
  apply where measurements exist, independently of 5K and chart controls.
  A robust median pairwise slope fits log pace against HR using pairs within
  30 days, with at least 8 bpm of observed spread. The target must be within 5 bpm
  of the observed HR range. When HR barely varies, four nearby runs within 3 bpm
  can provide a local median instead. Unclear relationships or excessive scatter
  produce a data-needed message. The displayed typical range uses robust residual
  spread (with a 2.5% minimum); it is descriptive, not a confidence interval or HR
  guarantee. Pace rounds to five seconds. Easy workout distance uses the selected
  45/80-minute duration (configurable in Profile), shown beside each estimate. Trail surface
  and technical difficulty remain unmodeled; trail estimates retain the usual
  terrain mix of the runner's recent trail history.
  Local weather fills temperature and humidity using Open-Meteo's current model
  data and approximate Android location. The app asks for coarse foreground
  location when first needed on Targets; declining leaves manual editing available.
  With access enabled, opening the app or Targets checks for an update, with at
  most one automatic lookup per ten minutes. Failed attempts count, and the
  cooldown and manual hold survive app restarts. Local weather can be tapped to
  bypass the cooldown/hold; only a successful refresh replaces the manual values.
  Typing temperature or humidity cancels any in-flight lookup. Leaving the app
  cancels location and HTTP work; there is no background-location permission or
  repeating background weather job. Elevation fields are never filled by weather.
  Coordinates are rounded to two decimal places (roughly 1 km north/south, less
  east/west depending on latitude) before the HTTPS request and are not stored or
  logged. Only temperature, humidity and timestamps are retained. No account,
  Garmin data, device identifier or route is sent. Open-Meteo still sees the public
  IP and request metadata; its [privacy policy](https://open-meteo.com/en/terms#privacy)
  describes server logs including coordinates, retained for up to 90 days.
  Requests time out, reject missing/stale values, and preserve saved conditions
  on failure. The weather timestamp and Open-Meteo attribution appear below the fields.
  Temperature, humidity, elevation gain/loss, equivalent race times, and an
  optional custom race distance use the web app's FVDOT and adjustment math.
- **Profile → Routes** configures Lakeview Parkway (Provo), west to Jordan River
  then south (SLC), Liberty Park (SLC), and Bonneville Shoreline (SLC). Each route
  has one full reference session, an Out-and-back / Loop / One-way shape, Road /
  Trail surface, and an optional reverse direction. Starting point follows the
  reference start, or its finish when reversed. GPS suggests a turnaround or loop
  length; confirm/edit that distance once. A shorter out-and-back turns earlier
  along the same outward leg, then reverses gain/loss on the return. Its turnaround
  is solved from the complete planned duration, not half the original reference
  or half the elapsed time. Loops repeat as needed. One-way runs and outward legs
  beyond the measured extent use clearly labelled average-terrain extrapolation.
  Reference suggestions rank GPS overlap and longer coverage, regardless of run
  category. Check five more recordings to extend suggestions; existing checks
  are reused. Normal recording sync builds profiles and suggestions without extra
  download requests. Older per-category references migrate to the longest whole-run
  reference (or longest remaining reference). An older cache may require one explicit
  reread of that recording when selecting the route to obtain its elevation profile.
  A reference needs GPS, distance and recorded altitude; aggregate totals alone
  are insufficient. Missing or changed references require choosing a reference again.
- **Profile → Workouts** defines Easy (45 min) and Easy long (80 min), plus warm-up,
  repetitions, work duration and cooldown for Short / Medium / Long. Initial interval
  defaults are 10×3, 6×5, and 3×10 minutes, each with 10 min warm-up and cooldown.
  Every repetition has exactly one minute of walking afterward, including the final
  rep. Walking pace starts at 20:00/mi and is configurable in the selected distance
  units. Warm-up and cooldown always use the route surface's estimated 128 bpm easy
  pace. All phases advance along the route; only work phases determine interval
  pace and work elevation. The native spatial model evaluates terrain in at most
  100 m steps and solves out-and-back closure to approximately 0.5 m. Uphill and
  downhill need not consume equal time. Local elevation effects and weather apply
  once; walking uses its configured fixed pace. Recorded elevation is smoothed
  with nearby samples and a 3 m change threshold, stored as a bounded cumulative
  ascent/descent profile. Technical footing and other trail conditions are not modeled.
  **Use latest session** explicitly copies parameters from the latest matching run;
  selected work laps determine reps and median work duration, and the final walking
  minute is removed from the remaining cooldown duration. Moving recovery laps can
  populate walking pace; stationary/unusable recoveries leave its existing value.
  Sync never silently changes workout definitions. Inline valid edits save immediately.
  Easy durations accept 5–360 min; interval plans are bounded to six hours.
  Route configurations, distance/elevation profiles and coarse location cells remain
  app-private and outside comparison/sample exports. Only calculated aggregate route
  plans are exported. Web pace parity excludes the native spatial model while still
  comparing its 5K basis. Raw FIT files are discarded; sign-out clears references,
  profiles and GPS cells. No map or elevation service receives this reference data.
- Weekly recovery: sleep, resting HR, and HRV appear in three lanes with a
  shared date axis, or one expanded metric. Latest measured weekly averages and
  day counts appear above the chart. Lines break across missing weeks; tapping a
  point opens a sheet with its value and measured-day count. Single-metric scales
  use that metric's units and precision, including resting HR and HRV.
- Sessions: search, category filters, pagination, run details, and category and
  work-lap corrections. Cross-training and strength sessions appear here too.
  Recent-session metrics are shown in these same rows, with one search/filter
  state and no separate preview on Trends.

The date selector includes All (since June 2025), 7/30/45/90/180 days, one year,
18/24 calendar months, and custom dates. Pace defaults to min/mile; min/km is
available in Profile. The first launch of 0.11 changes an All-range selection to
90 days; an existing specific/custom selection is preserved. Full-history
calibration and saved data stay enabled. Charts use one-finger horizontal drags
for scrubbing; vertical swipes scroll the page until a scrub begins. Expanded
charts use two fingers to zoom and pan (date and value axes for pace/load/effort,
dates only for Recovery). Lifting one finger after a pinch never starts a scrub
or opens details. Double-tap resets the expanded viewport. Dashboard previews
allow scrubbing, taps and page scrolling without intercepting pinch gestures.

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

Trends and Sessions share an **Adjustments** split control. Tap its label once
to turn both elevation and weather on or off immediately. It shows **On**, **Off**, or **1**
when only one is active; tapping a partial selection enables both. The adjacent
**More** button opens the individual elevation/weather switches and Apply action.
Both settings are saved together and redraw cached charts and cards without a
download. Sessions labels its pace columns **Adj pace** and **Adj work pace**
when conditions are enabled. Overall pace uses the whole activity's distance
and elevation; interval work pace uses the work distance and work elevation
(with the established activity-elevation fallback). Missing conditions stay
unadjusted, and HR-normalized trend modes do not replace these card paces.
Distance, time, HR, elevation, and weather values stay recorded. Recorded overall
and work paces remain available in session details.
Interval targets show three compact pace tiles; the 5K basis and automatically
saved condition fields are inline.
Equivalent race times stay expanded, with an automatically saved custom-distance field. Session
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
without waiting for recovery or weather downloads. Terrain route samples are sent
to OpenTopoData; original FITs and GPS profiles are discarded after aggregation.
The separate local-weather lookup sends only rounded current-location coordinates
to Open-Meteo while the app is in use.
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
python scripts/check_refresh.py
python scripts/check_material.py
python scripts/check_conditions.py
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
In Targets, verify Estimate starts with both adjustments on, and its HR mode
matches the previous 5K chart mode on first upgrade. Toggle both adjustments,
each individual correction, and HR normalization; verify the basis labels and
paces update from cached data. Change Trends settings and confirm Targets stays
the same, and vice versa. Switch to Latest Trial and Custom: HR normalization
must not appear, and Custom must use exactly the entered 5K time. Check saved
choices after switching sources, tabs, and restarting; explicitly turning
predicted adjustments off must survive reopening. Edit next-workout conditions inline:
there must be no Apply step, the keyboard and caret must stay put while paces update,
and tab/app changes must retain saved edits. Try negative temperatures, partial
numbers, humidity outside 0–100, and negative elevation to check validation.
Tap outside the fields or use Done/Back: focus and keyboard must clear without
immediately selecting the first field again. Tapping another condition field
must switch directly without losing the edit. At normal text size, verify the
Short/Medium/Long pace tiles all share one row with work durations and pace units;
enlarged text should wrap them rather than clipping labels or values.
Change next-workout conditions:
the 5K basis should stay fixed while target paces change. Check both themes and
enlarged text for the new controls.
For local weather, grant approximate location and confirm temperature/humidity
fill while elevation stays unchanged. Reopening within ten minutes must not
request again; Local weather must refresh on demand. Denied permission, phone
location disabled, no recent fix, timeout and no internet must leave conditions
editable and preserve saved values. Type during a lookup: that edit must win.
Reopen after a manual edit and confirm the one-hour hold persists; an explicit
successful refresh should end it. Leaving the app must cancel the lookup. Check
updates while Garmin sync is running and verify target paces catch up afterward.
`python scripts/check_weather_endpoint.py` optionally checks the live API contract
using the provider's public Berlin example, never the phone's actual location.
For each chart legend, hide and restore every entry, then hide all entries and
restore one. Expand a chart, zoom, and toggle a series: the view should stay put,
hidden points should leave View data and point selection, and the card legend
should agree after closing. Check 5K visibility in its settings sheet as well,
and verify choices survive switching date ranges, tabs, and reopening the app.
Scrub each chart horizontally: the guide should move smoothly while the bubble
shows a real point's date and value from the first enabled legend item. Lift to
keep the readout; toggle the active series to retarget it without changing zoom.
Verify an enabled but empty series shows no visible measurements, fixed-scale
outliers cannot be selected, and interval pace shows one average per workout.
Check each Recovery lane and weekly load, plus two-finger zoom/pan in Explore.
After lifting one finger from a pinch, the remaining finger must not scrub or
open a point sheet. Vertical swipes must scroll the page; taps and View data must
still open details. Check bubble placement at both edges with enlarged text:
it must stay in the reserved header when the finger moves up and down, never
cover axes or data, and never resize the plot when it appears or disappears.
In Sessions, verify there is one list with newest-first dates beside each card's
category, search, every category filter, Show more, and all available
HR/elevation/weather/5K metrics. Check that the first category filters follow
Short/Medium/Long/Easy/Easy Long, with Needs review last, and that older-year
card dates include the year.
Check that overall pace uses the entire session rather than work reps or a 5K
segment. Toggle conditions in either Sessions or Trends and switch tabs: both
controls should agree, only pace columns should change, and both elevation
gain and loss should remain visible. Check a long activity duration and larger
system text to confirm the metric grid wraps while the Work pace/HR columns
stay aligned. Confirm the name follows temperature in the footer without a
separate name row. Opening a row should retain its
detail page, recorded overall/work paces, and correction actions. Trends
should contain charts and summaries without an activity preview.
For pull-to-refresh, release a short pull, then a full pull from the top of
Trends, Sessions, and Targets. Only the full pull should start one sync. Pull
from the middle of a page, use chart gestures, and pull while sync is active;
these should not start another job. Check completion, error, and pause states,
then switch tabs or reopen during the sync.
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
5K segments, daily recovery values, weather, aggregate HR histograms, route
reference configuration, cumulative distance/elevation profiles, relative route outlines, and bounded coarse GPS cells
for local overlap matching. It retains no original archives, passwords, or authentication
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
larger differences. Manual category/lap overrides may
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
