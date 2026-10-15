# Shared resources

Garmin response parsers shared by the web and Android apps:

- `garmin_health.py`: sleep, resting HR, and HRV response normalization.
- `garmin_weather.py`: activity weather response normalization.

The web downloaders import these modules relative to their source location.
The Android build packages them into the embedded Python application archive.

Keep platform-specific download, storage, and UI code in `web_app/` or
`android/`. Do not commit real activity data, health data, or authentication
tokens. Tests use synthetic fixtures.
