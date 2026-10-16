import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import update_sdca as sdca


def candle_rows(count=351, start=datetime(2025, 1, 1, tzinfo=timezone.utc)):
    rows = []
    for index in range(count):
        open_time = start + timedelta(days=index)
        open_ms = int(open_time.timestamp() * 1000)
        close_ms = open_ms + 86_400_000 - 1
        close = 50 + index / 10
        rows.append([open_ms, str(close - 0.5), str(close + 1), str(close - 1), str(close), "10", close_ms, "0", 1, "0", "0", "0"])
    return rows


def daily_close_fixture(count=351, start=datetime(2025, 1, 1, tzinfo=timezone.utc)):
    """Build valid, strictly chronological daily dates for mocked feed output."""
    dates = [(start + timedelta(days=index)).date().isoformat() for index in range(count)]
    closes = [50 + index / 10 for index in range(count)]
    return dates, closes


def coinsentry_payload(day=None):
    day = day or (sdca.utc_now().date() - timedelta(days=1)).isoformat()
    return {
        "source": "coinsentry", "asOf": day,
        "attribution": "Free to use with a visible link to https://coinsentry.app",
        "indicators": [{"code": "rsi_weekly", "description": "14-period weekly RSI (0–100)", "value": 57.2915, "date": day}],
    }


class CandleValidationTests(unittest.TestCase):
    def test_daily_close_fixture_dates_are_valid_and_contiguous(self):
        dates, closes = daily_close_fixture()
        self.assertEqual(len(dates), 351)
        self.assertEqual(dates[0], "2025-01-01")
        self.assertEqual(dates[-1], "2025-12-17")
        self.assertEqual(sdca.validate_history([{"date": day, "score": 0} for day in dates]), len(closes))

    def test_accepts_completed_contiguous_candles_and_returns_order(self):
        rows = candle_rows()
        dates, closes = sdca.get_daily_closes(rows, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(len(dates), 351)
        self.assertEqual(dates[0], "2025-01-01")
        self.assertEqual(closes[-1], 85.0)

    def test_excludes_unclosed_candle_and_rejects_insufficient_history(self):
        rows = candle_rows(352)
        now = datetime.fromtimestamp(rows[-2][6] / 1000, timezone.utc)
        dates, _ = sdca.get_daily_closes(rows, now=now)
        self.assertEqual(len(dates), 351)
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            sdca.get_daily_closes(candle_rows(351), now=datetime.fromtimestamp(candle_rows(351)[-2][6] / 1000, timezone.utc))

    def test_rejects_malformed_rows_and_invalid_prices(self):
        for value in (0, -1, float("nan"), float("inf"), "bad"):
            rows = candle_rows()
            rows[10][4] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                sdca.get_daily_closes(rows, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        rows = candle_rows()
        rows[0] = rows[0][:5]
        with self.assertRaisesRegex(ValueError, "Malformed"):
            sdca.get_daily_closes(rows, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        rows = candle_rows()
        rows[0][0] += 1
        with self.assertRaisesRegex(ValueError, "UTC daily interval"):
            sdca.get_daily_closes(rows, now=datetime(2026, 1, 1, tzinfo=timezone.utc))

    def test_raw_sma_and_wilder_rsi_calculations(self):
        self.assertIsNone(sdca.sma([1, 2], 3))
        self.assertEqual(sdca.sma([1, 2, 3, 4], 2), 3.5)
        self.assertEqual(sdca.rsi_wilder([1, 2, 3], length=2), 100.0)
        self.assertEqual(sdca.rsi_wilder([3, 2, 1], length=2), 0.0)
        self.assertEqual(sdca.rsi_wilder([1, 2, 1], length=2), 50.0)
        self.assertEqual(sdca.rsi_wilder([2, 2, 2], length=2), 50.0)
        self.assertIsNone(sdca.rsi_wilder([1, 2], length=2))

    def test_rejects_out_of_order_duplicate_and_gapped_dates(self):
        now = datetime(2026, 1, 3, tzinfo=timezone.utc)
        cases = []
        unordered = candle_rows()
        unordered[12], unordered[13] = unordered[13], unordered[12]
        cases.append((unordered, "chronological"))
        duplicated = candle_rows()
        duplicated[20] = duplicated[19].copy()
        cases.append((duplicated, "Duplicate"))
        gapped = candle_rows()
        gapped.pop(20)
        gapped.append(candle_rows(1, datetime(2026, 1, 1, tzinfo=timezone.utc))[0])
        # Still deliberately non-contiguous after the last row is ordered.
        cases.append((gapped, "chronological|Gap"))
        for rows, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                sdca.get_daily_closes(rows, now=now)


class HistoryAndFailureTests(unittest.TestCase):
    def test_score_validation_rejects_out_of_range_composite_values(self):
        self.assertEqual(sdca.validate_score(0, "composite score"), 0.0)
        for value in (-3.01, 3.01, float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sdca.validate_score(value, "composite score")

    def test_history_accepts_only_valid_ordered_dates_and_scores(self):
        good = [{"date": "2025-01-01", "score": -3}, {"date": "2025-01-03", "score": 3}]
        self.assertEqual(sdca.validate_history(good), 2)
        invalid = [
            [{"date": "2025-01-01", "score": 3.01}],
            [{"date": "2025-02-30", "score": 0}],
            [{"date": "2025-01-02", "score": 0}, {"date": "2025-01-02", "score": 1}],
            [{"date": "2025-01-03", "score": 0}, {"date": "2025-01-02", "score": 0}],
            [{"date": "2025-01-01", "score": float("nan")}],
        ]
        for history in invalid:
            with self.subTest(history=history), self.assertRaises(ValueError):
                sdca.validate_history(history)

    def test_failure_record_is_structured_and_retains_error_type(self):
        record = sdca.failure_record("public feed", TimeoutError("timeout"))
        self.assertEqual(record, {"feed": "public feed", "type": "TimeoutError", "message": "timeout"})

    def test_unreadable_existing_output_is_never_replaced_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "invalid.json"
            target.write_text("not json", encoding="utf-8")
            with patch.object(sdca, "OUTPUT", target), self.assertRaisesRegex(RuntimeError, "Refusing to overwrite"):
                sdca.load_previous()
            self.assertEqual(target.read_text(encoding="utf-8"), "not json")

    def test_independent_feed_failure_does_not_discard_valid_readings_or_history(self):
        history = [{"date": "2025-01-01", "score": 0.25}]
        def json_for_url(url):
            if url == sdca.COINSENTRY_RSI_URL:
                return coinsentry_payload()
            raise TimeoutError("feed timeout")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            output_path = data_dir / "sdca-latest.json"
            output_path.write_text(json.dumps({"history": history}), encoding="utf-8")
            with patch.object(sdca, "ROOT", root), patch.object(sdca, "DATA_DIR", data_dir), patch.object(sdca, "OUTPUT", output_path), patch.object(sdca, "get_daily_closes", return_value=daily_close_fixture()), patch.object(sdca, "get_json", side_effect=json_for_url), patch.object(sdca, "get_text", return_value="source csv"), patch.object(sdca, "parse_durden_daily_csv", return_value=daily_close_fixture()), patch.object(sdca, "damped_harmonic_oscillator", return_value=-12.5), patch.object(sdca, "pi_cycle_ratio", return_value=0.47), patch.object(sdca, "verify_durden_dho_reference", return_value={"matchedAtPublishedPrecision": True, "publishedValue": -100, "comparisonDate": "2026-02-26"}), patch.object(sdca, "verify_durden_pi_reference", return_value={"matchedAtPublishedPrecision": True, "publishedValue": 0.460, "comparisonDate": "2026-10-09"}), patch.dict(os.environ, {}, clear=True):
                sdca.main()
            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result["history"], history)
            self.assertEqual(result["indicators"][8]["rawValue"], 57.2915)
            self.assertEqual(result["indicators"][8]["timeframe"], "weekly")
            self.assertEqual(result["indicators"][8]["sourceField"], "rsi_weekly")
            self.assertEqual(result["indicators"][8]["sourceTimestamp"], result["indicators"][8]["lastUpdated"])
            self.assertEqual(result["indicators"][8]["source"], sdca.COINSENTRY_RSI_URL)
            self.assertEqual(result["indicators"][7]["rawValue"], -12.5)
            self.assertEqual(result["indicators"][7]["source"], sdca.DURDEN_DAILY_CSV_URL)
            self.assertEqual(result["indicators"][9]["status"], "raw_available_score_pending")
            self.assertEqual(result["indicators"][13]["status"], "feed_error")
            self.assertEqual(result["feedFailures"][0]["feed"], "Alternative.me Fear & Greed")
            self.assertEqual(result["bitcoinPriceUSDT"]["quoteCurrency"], "USDT")
            self.assertEqual(result["bitcoinPriceUSDT"]["status"], "available")
            self.assertEqual(result["dataIntegrity"]["verifiedScores"], 0)
            self.assertEqual(result["dataIntegrity"]["missingRawReadings"], 12)
            self.assertEqual(result["dataIntegrity"]["unverifiedScores"], 15)

    def test_coinsentry_endpoint_failure_keeps_durden_and_sentiment_readings(self):
        def json_for_url(url):
            if url == sdca.COINSENTRY_RSI_URL:
                raise TimeoutError("CoinSentry unavailable")
            return {"data": [{"value": "50", "timestamp": "1792108800"}]}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            output_path = data_dir / "sdca-latest.json"
            output_path.write_text(json.dumps({"history": []}), encoding="utf-8")
            with patch.object(sdca, "ROOT", root), patch.object(sdca, "DATA_DIR", data_dir), patch.object(sdca, "OUTPUT", output_path), patch.object(sdca, "get_daily_closes", return_value=daily_close_fixture()), patch.object(sdca, "get_json", side_effect=json_for_url), patch.object(sdca, "get_text", return_value="source csv"), patch.object(sdca, "parse_durden_daily_csv", return_value=daily_close_fixture()), patch.object(sdca, "damped_harmonic_oscillator", return_value=-12.5), patch.object(sdca, "pi_cycle_ratio", return_value=0.47), patch.object(sdca, "verify_durden_dho_reference", return_value={"matchedAtPublishedPrecision": True, "publishedValue": -100, "comparisonDate": "2026-02-26"}), patch.object(sdca, "verify_durden_pi_reference", return_value={"matchedAtPublishedPrecision": True, "publishedValue": 0.460, "comparisonDate": "2026-10-09"}), patch.dict(os.environ, {}, clear=True):
                sdca.main()
            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result["indicators"][8]["status"], "feed_error")
            self.assertIsNone(result["indicators"][8]["rawValue"])
            self.assertEqual(result["indicators"][7]["rawValue"], -12.5)
            self.assertEqual(result["indicators"][9]["rawValue"], 0.47)
            self.assertEqual(result["indicators"][13]["rawValue"], 50.0)
            self.assertEqual([item["feed"] for item in result["feedFailures"]], ["CoinSentry weekly RSI"])

    def test_durden_csv_endpoint_failure_keeps_weekly_rsi_and_sentiment_readings(self):
        def json_for_url(url):
            if url == sdca.COINSENTRY_RSI_URL:
                return coinsentry_payload()
            return {"data": [{"value": "50", "timestamp": "1792108800"}]}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            output_path = data_dir / "sdca-latest.json"
            output_path.write_text(json.dumps({"history": []}), encoding="utf-8")
            with patch.object(sdca, "ROOT", root), patch.object(sdca, "DATA_DIR", data_dir), patch.object(sdca, "OUTPUT", output_path), patch.object(sdca, "get_daily_closes", return_value=daily_close_fixture()), patch.object(sdca, "get_json", side_effect=json_for_url), patch.object(sdca, "get_text", side_effect=TimeoutError("Durden CSV unavailable")), patch.dict(os.environ, {}, clear=True):
                sdca.main()
            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result["indicators"][8]["rawValue"], 57.2915)
            self.assertEqual(result["indicators"][7]["status"], "feed_error")
            self.assertEqual(result["indicators"][9]["status"], "feed_error")
            self.assertEqual(result["indicators"][13]["rawValue"], 50.0)
            self.assertEqual([item["feed"] for item in result["feedFailures"]], [
                "DurdenBTC Damped Harmonic Oscillator CSV", "DurdenBTC Pi Cycle Top CSV"
            ])

    def test_substitute_source_timestamp_is_normalized_and_reported(self):
        history = []
        feed_payload = {"data": [{"value": "63", "timestamp": "1792108800"}]}
        def json_for_url(url):
            if url == sdca.COINSENTRY_RSI_URL:
                return coinsentry_payload()
            return feed_payload

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            output_path = data_dir / "sdca-latest.json"
            output_path.write_text(json.dumps({"history": history}), encoding="utf-8")
            with patch.object(sdca, "ROOT", root), patch.object(sdca, "DATA_DIR", data_dir), patch.object(sdca, "OUTPUT", output_path), patch.object(sdca, "get_daily_closes", return_value=daily_close_fixture()), patch.object(sdca, "get_json", side_effect=json_for_url), patch.object(sdca, "get_text", return_value="source csv"), patch.object(sdca, "parse_durden_daily_csv", return_value=daily_close_fixture()), patch.object(sdca, "damped_harmonic_oscillator", return_value=-12.5), patch.object(sdca, "pi_cycle_ratio", return_value=0.47), patch.object(sdca, "verify_durden_dho_reference", return_value={"matchedAtPublishedPrecision": True, "publishedValue": -100, "comparisonDate": "2026-02-26"}), patch.object(sdca, "verify_durden_pi_reference", return_value={"matchedAtPublishedPrecision": True, "publishedValue": 0.460, "comparisonDate": "2026-10-09"}), patch.dict(os.environ, {}, clear=True):
                sdca.main()
            result = json.loads(output_path.read_text(encoding="utf-8"))
            fear_greed = result["indicators"][13]
            self.assertEqual(fear_greed["source"], sdca.FNG_SOURCE)
            self.assertEqual(fear_greed["referenceSource"], sdca.SOURCE_LINKS["Crypto Fear and Greed Index"])
            self.assertEqual(fear_greed["lastUpdated"], "2026-10-16T00:00:00+00:00")
            self.assertEqual(fear_greed["status"], "raw_available_source_substitute")
            self.assertEqual(fear_greed["substituteStatus"], "substitute_not_equivalent_verified")
            self.assertEqual(result["feedFailures"], [])
            self.assertEqual(result["indicators"][8]["timeframe"], "weekly")
            self.assertEqual(result["indicators"][9]["source"], sdca.DURDEN_DAILY_CSV_URL)

    def test_github_summary_includes_independent_feed_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            output = {
                "feedFailures": [{"feed": "test feed", "type": "TimeoutError", "message": "timed out"}],
                "historyValidation": {"valid": True, "validCount": 0, "error": None},
                "dataIntegrity": {"rawReadingsAvailable": 2, "verifiedScores": 0},
                "bitcoinPriceUSDT": {"status": "unavailable"}
            }
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary)}):
                sdca.write_github_summary(output)
            self.assertIn("test feed", summary.read_text(encoding="utf-8"))
            self.assertIn("TimeoutError", summary.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
