# Running Dashboard

A running dashboard with a web app and space for a future Android app.

## Repository layout

- `web_app/`: web interface, Python server, downloaders, and dashboard builder.
- `android/`: future Android Studio project.
- `common/`: shared data contracts, sample fixtures, and resources used by both apps.

## Run the web app

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r web_app/requirements.txt
cd web_app
../.venv/bin/python dashboard_server.py
```

Open http://127.0.0.1:8000. On a fresh checkout, run
`../.venv/bin/python update_dashboard.py` from `web_app/` to log into Garmin and
generate the dashboard data.

See [the web app guide](web_app/README.md) for download, build, and refresh commands.
Local Garmin tokens, downloaded activity and health data, and generated dashboard
data are ignored by Git.

## Tests

From the repository root:

```sh
cd web_app
../.venv/bin/python -m unittest discover -v
```
