import csv
import io
import math
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import update_sdca as sdca


def durden_csv_fixture(count=351, start=date(2010, 7, 13)):
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
    for index in range(count):
        close = 100.0 + index
        writer.writerow([
            (start + timedelta(days=index)).isoformat(),
            close - 0.5, close + 1, close - 1, close, 1000,
        ])
    return output.getvalue()


def coinsentry_payload(day="2026-10-15"):
    return {
        "source": "coinsentry",
        "asOf": day,
        "attribution": "Free to use with a visible link to https://coinsentry.app",
        "indicators": [
            {"code": "rsi_daily", "description": "14-period daily RSI (0–100)", "value": 48.6614, "date": day},
            {"code": "rsi_weekly", "description": "14-period weekly RSI (0–100)", "value": 57.2915, "date": day},
        ],
    }


class CoinSentryWeeklyRsiTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)

    def test_reads_weekly_field_and_preserves_actual_observation_date(self):
        result = sdca.parse_coinsentry_weekly_rsi(coinsentry_payload(), now=self.now)
        self.assertEqual(result["value"], 57.2915)
        self.assertEqual(result["date"], "2026-10-15")
        self.assertIn("weekly", result["description"])
        self.assertIn("coinsentry.app", result["attribution"])

    def test_does_not_fall_back_to_daily_rsi(self):
        payload = coinsentry_payload()
        payload["indicators"] = [payload["indicators"][0]]
        with self.assertRaisesRegex(ValueError, "rsi_weekly"):
            sdca.parse_coinsentry_weekly_rsi(payload, now=self.now)

    def test_rejects_invalid_source_value_date_and_missing_backlink(self):
        cases = []
        bad_value = coinsentry_payload()
        bad_value["indicators"][1]["value"] = float("nan")
        cases.append((bad_value, "between 0 and 100"))
        future = coinsentry_payload("2026-10-16")
        cases.append((future, "completed daily close"))
        stale = coinsentry_payload("2026-10-13")
        cases.append((stale, "stale"))
        no_backlink = coinsentry_payload()
        no_backlink["attribution"] = "No attribution supplied"
        cases.append((no_backlink, "backlink requirement"))
        malformed = coinsentry_payload()
        malformed["indicators"][1]["date"] = "2026-2-3"
        cases.append((malformed, "must be an ISO date"))
        for payload, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                sdca.parse_coinsentry_weekly_rsi(payload, now=self.now)


class DurdenCsvValidationTests(unittest.TestCase):
    def test_validates_daily_rows_and_excludes_an_unfinished_current_day(self):
        csv_text = durden_csv_fixture()
        dates, closes = sdca.parse_durden_daily_csv(
            csv_text,
            now=datetime(2011, 6, 30, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(len(dates), 351)
        self.assertEqual(dates[0], "2010-07-13")
        self.assertEqual(dates[-1], "2011-06-28")
        self.assertEqual(closes[-1], 450.0)

        current_day_csv = csv_text + "2011-06-29,450,452,449,451,1000\n"
        current_dates, _ = sdca.parse_durden_daily_csv(
            current_day_csv,
            now=datetime(2011, 6, 29, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(current_dates[-1], "2011-06-28")

    def test_rejects_wrong_schema_missing_rows_and_invalid_prices(self):
        valid = durden_csv_fixture()
        with self.assertRaisesRegex(ValueError, "schema"):
            sdca.parse_durden_daily_csv(valid.replace("Date,Open,High,Low,Close,Volume", "date,Open,High,Low,Close,Volume", 1))
        malformed_lines = valid.splitlines()
        malformed_lines[-1] = "2011-06-28,449.5,451.0"
        with self.assertRaisesRegex(ValueError, "Malformed"):
            sdca.parse_durden_daily_csv("\n".join(malformed_lines) + "\n")
        for raw in ("0", "-1", "nan", "inf", "bad"):
            bad = valid.replace(",100.0,1000", f",{raw},1000", 1)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                sdca.parse_durden_daily_csv(bad, now=datetime(2011, 6, 30, tzinfo=timezone.utc))

    def test_rejects_duplicate_unordered_gapped_future_and_stale_dates(self):
        valid = durden_csv_fixture()
        lines = valid.splitlines()
        duplicate = lines.copy()
        duplicate[20] = duplicate[19]
        unordered = lines.copy()
        unordered[20], unordered[21] = unordered[21], unordered[20]
        missing_gap = lines.copy()
        del missing_gap[20]
        future = lines.copy()
        future[-1] = "2011-07-01,450,452,449,451,1000"
        cases = [
            ("\n".join(duplicate) + "\n", "Duplicate"),
            ("\n".join(unordered) + "\n", "chronological"),
            ("\n".join(missing_gap) + "\n", "Gap"),
            ("\n".join(future) + "\n", "future date"),
        ]
        for content, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                sdca.parse_durden_daily_csv(content, now=datetime(2011, 6, 30, tzinfo=timezone.utc))
        with self.assertRaisesRegex(ValueError, "stale"):
            sdca.parse_durden_daily_csv(valid, now=datetime(2012, 1, 1, tzinfo=timezone.utc))

    def test_pi_cycle_formula_uses_111_and_350_daily_closes(self):
        closes = [float(value) for value in range(1, 351)]
        self.assertAlmostEqual(sdca.pi_cycle_ratio(closes), 295 / (2 * 175.5), places=14)
        with self.assertRaisesRegex(ValueError, "350 daily closes"):
            sdca.pi_cycle_ratio(closes[:349])

    def test_durden_pi_historical_verification_uses_source_closes_for_2026_10_09(self):
        # Pinned 350-row source slice from DurdenBTC's published daily CSV.
        fixture = Path(__file__).parent / "fixtures" / "durden-pi-2026-10-09.csv"
        with fixture.open(newline="", encoding="utf-8") as source:
            rows = list(csv.DictReader(source))
        dates = [row["Date"] for row in rows]
        closes = [float(row["Close"]) for row in rows]

        self.assertEqual(len(dates), 350)
        self.assertEqual(dates[0], "2025-10-25")
        self.assertEqual(dates[-1], "2026-10-09")
        self.assertTrue(all(
            (date.fromisoformat(later) - date.fromisoformat(earlier)).days == 1
            for earlier, later in zip(dates, dates[1:])
        ))
        comparison = sdca.verify_durden_pi_reference(dates, closes)
        self.assertTrue(comparison["matchedAtPublishedPrecision"])
        self.assertEqual(comparison["comparisonDate"], "2026-10-09")
        self.assertEqual(comparison["source"], sdca.DURDEN_PI_PAGE)
        self.assertAlmostEqual(comparison["calculatedValue"], 0.4598941916758626, places=14)
        self.assertEqual(f"{comparison['calculatedValue']:.3f}", "0.460")

    def test_source_comparison_uses_the_published_display_precision(self):
        pi = sdca.compare_published_display(0.459894191676, 0.460, 3, "Pi Cycle")
        self.assertTrue(pi["matchedAtPublishedPrecision"])
        with self.assertRaisesRegex(ValueError, "does not match"):
            sdca.compare_published_display(0.455, 0.460, 3, "Pi Cycle")

    def test_damped_harmonic_calculation_is_finite_and_clamped(self):
        start = date(2010, 7, 13)
        dates, closes = [], []
        for index in range(800):
            day = start + timedelta(days=index)
            age = (day - date(2009, 1, 3)).days
            elapsed = index
            log_close = 0.3 + 0.52 * math.log10(age) + 0.22 * math.exp(-8.5e-5 / 2 * elapsed) * math.cos(0.0041 * elapsed + 0.2)
            dates.append(day.isoformat())
            closes.append(10 ** log_close)
        result = sdca.damped_harmonic_oscillator(dates, closes)
        self.assertTrue(math.isfinite(result))
        self.assertGreaterEqual(result, -100)
        self.assertLessEqual(result, 100)


if __name__ == "__main__":
    unittest.main()
