from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timezone
from email.message import Message
from pathlib import Path
from unittest import mock

import download_station_weather as station_weather


CSV_HEADER = "station,valid,tmpf,dwpf,relh,feel,metar\n"


def station_csv(*rows: str) -> str:
    return CSV_HEADER + "\n".join(rows) + ("\n" if rows else "")


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.text.encode("utf-8")


class StationWeatherCacheTests(unittest.TestCase):
    def test_legacy_migration_uses_widest_file_and_builds_reusable_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir)
            raw = out / "raw"
            raw.mkdir()
            (raw / "KPVU_2020-01-01_2020-01-02.csv").write_text(
                station_csv("PVU,2020-01-01 12:00,40,30,50,38,KPVU OLD"),
                encoding="utf-8",
            )
            (raw / "KPVU_2020-01-01_2020-01-03.csv").write_text(
                station_csv(
                    "PVU,2020-01-01 12:00,41,31,51,39,KPVU NEW",
                    "PVU,2020-01-03 12:00,43,33,53,41,KPVU THIRD",
                ),
                encoding="utf-8",
            )

            covered, observations, provisional, migrated = (
                station_weather.load_or_migrate_station_cache(out, "KPVU")
            )

            self.assertTrue(migrated)
            self.assertEqual(
                covered,
                {date(2020, 1, 1), date(2020, 1, 2), date(2020, 1, 3)},
            )
            self.assertFalse(provisional)
            self.assertEqual(len(observations), 2)
            self.assertEqual(observations[0]["temperature"], 41)
            self.assertTrue(station_weather.station_cache_path(out, "KPVU").exists())

    def test_successful_empty_response_is_negative_cached(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_index = root / "activities-index.json"
            out = root / "station-weather"
            source_index.write_text(
                json.dumps(
                    [
                        {
                            "activityId": 123,
                            "activityName": "No observation run",
                            "activityType": {"typeKey": "running"},
                            "startLatitude": 40.2192,
                            "startLongitude": -111.7234,
                            "startTimeLocal": "2020-01-02 08:00:00",
                            "startTimeGMT": "2020-01-02 15:00:00",
                            "elapsedDuration": 3600,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            argv = [
                "download_station_weather.py",
                "--start",
                "2020-01-02",
                "--end",
                "2020-01-02",
                "--out",
                str(out),
                "--delay",
                "0",
            ]

            with (
                mock.patch.object(station_weather, "SOURCE_INDEX", source_index),
                mock.patch.object(station_weather.sys, "argv", argv),
                mock.patch.object(
                    station_weather,
                    "fetch_station_csv",
                    return_value=station_csv(),
                ) as fetch,
            ):
                self.assertEqual(station_weather.main(), 0)
                self.assertEqual(fetch.call_count, 1)

            with (
                mock.patch.object(station_weather, "SOURCE_INDEX", source_index),
                mock.patch.object(station_weather.sys, "argv", argv),
                mock.patch.object(station_weather, "fetch_station_csv") as fetch,
            ):
                self.assertEqual(station_weather.main(), 0)
                fetch.assert_not_called()

            payload = json.loads((out / station_weather.SUMMARY_NAME).read_text())
            self.assertEqual(payload["counts"]["missing"], 1)
            self.assertEqual(payload["downloadedStationFiles"], 0)

    def test_rate_limit_honors_retry_after_and_then_succeeds(self) -> None:
        headers = Message()
        headers["Retry-After"] = "0"
        rate_limit = urllib.error.HTTPError(
            "https://example.test",
            429,
            "Too Many Requests",
            headers,
            None,
        )
        expected = station_csv("PVU,2020-01-01 12:00,40,30,50,38,KPVU")

        with (
            mock.patch.object(
                station_weather.urllib.request,
                "urlopen",
                side_effect=[rate_limit, FakeResponse(expected)],
            ) as urlopen,
            mock.patch.object(station_weather.time, "sleep") as sleep,
        ):
            actual = station_weather.fetch_station_csv(
                "KPVU",
                date(2020, 1, 1),
                date(2020, 1, 1),
                retries=1,
                retry_base_delay=2,
            )

        self.assertEqual(actual, expected)
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(2)

    def test_transport_failure_is_not_negative_cached(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_index = root / "activities-index.json"
            out = root / "station-weather"
            source_index.write_text(
                json.dumps(
                    [
                        {
                            "activityId": 456,
                            "activityName": "Retryable run",
                            "activityType": {"typeKey": "running"},
                            "startLatitude": 40.2192,
                            "startLongitude": -111.7234,
                            "startTimeLocal": "2020-01-02 08:00:00",
                            "startTimeGMT": "2020-01-02 15:00:00",
                            "elapsedDuration": 3600,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            argv = [
                "download_station_weather.py",
                "--start",
                "2020-01-02",
                "--end",
                "2020-01-02",
                "--out",
                str(out),
                "--delay",
                "0",
            ]

            for _ in range(2):
                with (
                    mock.patch.object(station_weather, "SOURCE_INDEX", source_index),
                    mock.patch.object(station_weather.sys, "argv", argv),
                    mock.patch.object(
                        station_weather,
                        "fetch_station_csv",
                        side_effect=urllib.error.URLError("temporary failure"),
                    ) as fetch,
                ):
                    self.assertEqual(station_weather.main(), 1)
                    self.assertEqual(fetch.call_count, 1)

            self.assertFalse(station_weather.station_cache_path(out, "KPVU").exists())

    def test_recent_empty_attempt_is_temporary_but_past_empty_date_is_final(self) -> None:
        now = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)
        covered: set[date] = set()
        provisional: dict[date, datetime] = {}
        station_weather.record_successful_dates(
            {date(2026, 9, 23), date(2026, 9, 24)},
            covered,
            provisional,
            now,
        )

        self.assertIn(date(2026, 9, 23), covered)
        self.assertNotIn(date(2026, 9, 24), covered)
        self.assertIn(
            date(2026, 9, 24),
            station_weather.reusable_dates(covered, provisional, now),
        )
        later = datetime(2026, 9, 25, 1, tzinfo=timezone.utc)
        self.assertNotIn(
            date(2026, 9, 24),
            station_weather.reusable_dates(covered, provisional, later),
        )


if __name__ == "__main__":
    unittest.main()
