from __future__ import annotations

import unittest
from datetime import date

from build_dashboard import classify


def running_activity(name: str, average_hr: float = 120) -> dict[str, object]:
    return {
        "activityName": name,
        "activityType": {"typeKey": "running"},
        "averageHR": average_hr,
    }


class ActivityClassificationTests(unittest.TestCase):
    def test_unqualified_taper_intervals_are_other_run_even_with_low_average_hr(self) -> None:
        activity = running_activity("Salt Lake City - Taper Intervals", average_hr=120)

        self.assertEqual(classify(activity, date(2026, 9, 24)), "other_run")

    def test_named_interval_models_keep_their_categories(self) -> None:
        self.assertEqual(
            classify(running_activity("Provo - Short Intervals"), date(2026, 9, 24)),
            "short_interval",
        )
        self.assertEqual(
            classify(running_activity("Provo - Medium Intervals"), date(2026, 9, 24)),
            "medium_interval",
        )
        self.assertEqual(
            classify(running_activity("Provo - Long Intervals"), date(2026, 9, 24)),
            "long_interval",
        )

    def test_explicit_easy_run_remains_easy(self) -> None:
        self.assertEqual(
            classify(running_activity("Salt Lake City - Easy 50"), date(2026, 9, 24)),
            "easy",
        )


if __name__ == "__main__":
    unittest.main()
