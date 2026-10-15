#!/usr/bin/env python3
"""Serve the dashboard locally and run refreshes on request."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
from collections import deque
from datetime import datetime
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
DASHBOARD_DIR = ROOT / "dashboard"
UPDATE_SCRIPT = ROOT / "update_dashboard.py"
REFRESH_HEADER = "X-Garmin-Dashboard"
REFRESH_HEADER_VALUE = "refresh"
STEP_PATTERN = re.compile(r"^== (.+) ==$")
MAX_LOG_LINES = 250


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class RefreshManager:
    """Own one updater process and expose a thread-safe status snapshot."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._status = "idle"
        self._step = "Ready"
        self._started_at: str | None = None
        self._finished_at: str | None = None
        self._return_code: int | None = None
        self._log: deque[str] = deque(maxlen=MAX_LOG_LINES)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "status": self._status,
                "step": self._step,
                "startedAt": self._started_at,
                "finishedAt": self._finished_at,
                "returnCode": self._return_code,
                "log": list(self._log),
            }

    def start(self) -> tuple[bool, dict[str, Any]]:
        with self._lock:
            if self._running:
                return False, self._snapshot_unlocked()
            self._running = True
            self._status = "running"
            self._step = "Starting update"
            self._started_at = now_iso()
            self._finished_at = None
            self._return_code = None
            self._log.clear()

        worker = threading.Thread(target=self._run, name="dashboard-refresh", daemon=True)
        worker.start()
        return True, self.snapshot()

    def _snapshot_unlocked(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "status": self._status,
            "step": self._step,
            "startedAt": self._started_at,
            "finishedAt": self._finished_at,
            "returnCode": self._return_code,
            "log": list(self._log),
        }

    def _append_log(self, line: str) -> None:
        with self._lock:
            self._log.append(line)
            match = STEP_PATTERN.match(line.strip())
            if match:
                self._step = match.group(1)

    def _finish(self, return_code: int, error: str | None = None) -> None:
        with self._lock:
            if error:
                self._log.append(error)
            self._running = False
            self._return_code = return_code
            self._finished_at = now_iso()
            if return_code == 0:
                self._status = "succeeded"
                self._step = "Update complete"
            else:
                self._status = "failed"
                self._step = f"Update failed (exit code {return_code})"

    def _run(self) -> None:
        command = [sys.executable, "-u", str(UPDATE_SCRIPT)]
        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"

        try:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.rstrip("\r\n")
                self._append_log(line)
                print(line, flush=True)
            return_code = process.wait()
        except Exception as exc:  # Keep the server usable if process launch fails.
            self._finish(1, f"Could not run updater: {exc}")
            return

        self._finish(return_code)


class DashboardRequestHandler(SimpleHTTPRequestHandler):
    manager: RefreshManager

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/api/refresh":
            self.send_json(self.manager.snapshot())
            return
        super().do_GET()

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/refresh":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if self.headers.get(REFRESH_HEADER) != REFRESH_HEADER_VALUE:
            self.send_json({"error": "Missing dashboard refresh header."}, HTTPStatus.FORBIDDEN)
            return

        started, state = self.manager.start()
        self.send_json(
            state,
            HTTPStatus.ACCEPTED if started else HTTPStatus.CONFLICT,
        )

    def log_message(self, message: str, *args: Any) -> None:
        print(f"{self.address_string()} - {message % args}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve the Garmin dashboard with a local data-refresh endpoint."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Local port to use. Defaults to 8000.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not DASHBOARD_DIR.is_dir():
        print(f"Missing dashboard directory: {DASHBOARD_DIR}", file=sys.stderr)
        return 2
    if not UPDATE_SCRIPT.is_file():
        print(f"Missing updater: {UPDATE_SCRIPT}", file=sys.stderr)
        return 2

    manager = RefreshManager()
    DashboardRequestHandler.manager = manager
    handler = partial(DashboardRequestHandler, directory=str(DASHBOARD_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    host, port = server.server_address
    print(f"Dashboard available at http://{host}:{port}")
    print("Press Ctrl-C to stop the server.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
