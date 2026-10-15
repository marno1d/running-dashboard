"""Use the same web source modules on the host and in the packaged APK."""
from pathlib import Path
import sys

# APK assets include these exact repository files. Host-side tests use them in place.
web = Path(__file__).resolve().parents[5] / 'web_app'
if web.is_dir():
    sys.path.insert(0, str(web))
import build_dashboard as dashboard
import download_station_weather as stations
import download_activity_elevation as terrain
