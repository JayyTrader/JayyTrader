import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import update_mvrv_zscore as mvrv


def csv_fixture():
    rows = ["date,mvrv_z_score,btc_close_usd"]
    start = date(2011, 9, 16)
    # 5,518 daily observations through 2026-10-24, matching Explore21's catalog.
    for index in range(5518):
        day = date.fromordinal(start.toordinal() + index)
        value = ((index % 101) - 50) / 20
        close = 100 + index
        rows.append(f"{day.isoformat()},{value:.4f},{close:.2f}")
    by_day = {line.split(",")[0]: i for i, line in enumerate(rows)}
    for day, value in mvrv.REFERENCE_ANCHORS.items():
        rows[by_day[day]] = f"{day},{value:.2f},50000.00"
    return "\n".join(rows) + "\n"


class MVRVParsingTests(unittest.TestCase):
    def test_parses_and_scores_historical_series_without_lookahead(self):
        rows = mvrv.parse_csv(csv_fixture(), today=date(2026, 10, 25))
        scored = mvrv.score_history(rows)
        self.assertEqual(len(rows), 5518)
        self.assertEqual(rows[0]["date"], "2011-09-16")
        self.assertEqual(rows[-1]["date"], "2026-10-24")
        self.assertIsNone(scored[28]["score"])
        self.assertIsNotNone(scored[29]["score"])
        shorter = mvrv.score_history(rows[:200])
        longer = mvrv.score_history(rows)
        self.assertEqual(shorter[150]["score"], longer[150]["score"])
        self.assertTrue(all(-2 <= row["score"] <= 2 for row in scored if row["score"] is not None))

    def test_lower_percentile_maps_to_higher_cheapness_score(self):
        rows = [
            {"date": f"2020-01-{day:02d}", "rawValue": value, "btcCloseUsd": 100.0}
            for day, value in enumerate([1, 2, 3, 4, 5], start=1)
        ]
        scored = mvrv.score_history(rows, minimum_observations=2)
        self.assertGreater(scored[1]["score"], scored[4]["score"])
        self.assertEqual(scored[1]["score"], 0.0)
        self.assertEqual(scored[4]["score"], -1.2)

    def test_rejects_bad_headers_duplicates_out_of_order_future_and_nonfinite_data(self):
        good = csv_fixture()
        cases = [
            ("date,other\n2020-01-01,1", "headers"),
            (good.replace("2011-09-17", "2011-09-16", 1), "Duplicate date"),
            (good.replace("2011-09-17", "2011-09-15", 1), "chronological"),
            (good.replace("2011-09-16,-2.5000,100.00", "2011-09-16,nan,100.00", 1), "Invalid numeric"),
            (good.replace("2011-09-16,-2.5000,100.00", "2011-09-16,,100.00", 1), "Missing"),
            (good.replace("2026-10-24,1.0000,5600.00", "2026-10-26,1.0000,5600.00", 1), "future date"),
        ]
        for text, error in cases:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                mvrv.parse_csv(text, today=date(2026, 10, 25))

    def test_anchor_validation_requires_all_public_reference_points(self):
        rows = mvrv.parse_csv(csv_fixture(), today=date(2026, 10, 25))
        result = mvrv.validate_reference_anchors(rows)
        self.assertTrue(result["valid"])
        self.assertEqual(result["checkedCount"], 8)
        damaged = [dict(row) for row in rows]
        target = next(row for row in damaged if row["date"] == "2013-12-04")
        target["rawValue"] = 99.0
        with self.assertRaisesRegex(ValueError, "cycle-anchor"):
            mvrv.validate_reference_anchors(damaged)

    def test_payload_includes_attribution_and_methodology(self):
        payload = mvrv.build_payload(csv_fixture(), now=datetime(2026, 10, 25, tzinfo=timezone.utc))
        self.assertEqual(payload["license"], "CC BY 4.0")
        self.assertEqual(payload["validation"]["referenceAnchors"]["checkedCount"], 8)
        self.assertFalse(payload["methodology"]["lookaheadBias"])
        self.assertEqual(payload["latest"]["date"], payload["history"][-1]["date"])
        self.assertIn("25 October 2026", payload["attribution"])


if __name__ == "__main__":
    unittest.main()
