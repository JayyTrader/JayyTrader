#!/usr/bin/env python3
"""Collect public SDCA raw data without inventing scores or history."""

import json
import math
import os
import tempfile
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT = DATA_DIR / "sdca-latest.json"
BINANCE_URL = (
    "https://data-api.binance.vision/api/v3/klines"
    "?symbol=BTCUSDT&interval=1d&limit=500"
)
FNG_URL = "https://api.alternative.me/fng/?limit=1&format=json"
BINANCE_DOCS = "https://developers.binance.com/en/docs/products/spot/rest-api"
FNG_SOURCE = "https://alternative.me/crypto/fear-and-greed-index/"

SOURCE_LINKS = {
    "MVRV-Z Score": "https://www.lookintobitcoin.com/charts/mvrv-zscore/",
    "Realized Cap HODL Waves": "https://www.lookintobitcoin.com/charts/realized-cap-hodl-waves/",
    "CBBI": "https://colintalkscrypto.com/cbbi/",
    "VDD Multiple": "https://charts.bitbo.io/vdd-multiple/",
    "NUPL": "https://charts.bitbo.io/net-unrealized-profit-loss/",
    "BTC 50 MARP": "https://kotecharts.com/c/fifty-marp",
    "LTH/STH SOPR Ratio": "https://kotecharts.com/c/sopr-ratio",
    "BTC Damped Harmonic Oscillator": "https://durdenbtc.com/charts/btc-damped-harmonic-oscillator",
    "Bitcoin RSI": "https://coinsentry.app/indicators/bitcoin-rsi?hide=daily%2Cmonthly",
    "Bitcoin Pi Cycle Top": "https://durdenbtc.com/charts/btc-pi-cycle-top",
    "Market Extreme Zone Index": "https://www.tradingview.com/script/Z9EoqtA7-Market-Extreme-Zones-Index/",
    "Relative Valuation Oscillator": "https://www.tradingview.com/script/zq7SYdHZ-Relative-Valuation-Oscillator-QuantAlgo/",
    "Volume-Weighted Price Z-Score": "https://www.tradingview.com/script/633Bjz5u-Volume-Weighted-Price-Z-Score-QuantAlgo/",
    "Crypto Fear and Greed Index": "https://coinstats.app/fear-and-greed/",
    "Composite Sentiment Score": "https://alphabitlab.com/crypto/sentiment-lab",
}

CATEGORIES = {
    **dict.fromkeys([
        "MVRV-Z Score", "Realized Cap HODL Waves", "CBBI", "VDD Multiple",
        "NUPL", "BTC 50 MARP", "LTH/STH SOPR Ratio"
    ], "Fundamental"),
    **dict.fromkeys([
        "BTC Damped Harmonic Oscillator", "Bitcoin RSI", "Bitcoin Pi Cycle Top",
        "Market Extreme Zone Index", "Relative Valuation Oscillator",
        "Volume-Weighted Price Z-Score"
    ], "Technical"),
    **dict.fromkeys(["Crypto Fear and Greed Index", "Composite Sentiment Score"], "Sentiment"),
}


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_utc(value):
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "JayyTrader-SDCA/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def _finite_positive(value, field):
    if isinstance(value, bool):
        raise ValueError(f"Invalid {field}")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid {field}") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"Invalid {field}: expected finite positive value")
    return result


def get_daily_closes(rows=None, now=None):
    """Return contiguous, completed Binance BTCUSDT daily closes and UTC dates."""
    if rows is None:
        rows = get_json(BINANCE_URL)
    if not isinstance(rows, list):
        raise ValueError("Binance candles must be a list")
    now = now or utc_now()
    now_ms = int(now.timestamp() * 1000)
    completed = []
    for index, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) != 12:
            raise ValueError(f"Malformed Binance candle at index {index}")
        try:
            if isinstance(row[0], bool) or isinstance(row[6], bool):
                raise ValueError("boolean timestamp")
            open_ms = int(row[0])
            close_ms = int(row[6])
            if float(row[0]) != open_ms or float(row[6]) != close_ms:
                raise ValueError("fractional timestamp")
            day = datetime.fromtimestamp(open_ms / 1000, timezone.utc).date()
        except (TypeError, ValueError, OverflowError, OSError) as exc:
            raise ValueError(f"Invalid Binance candle timestamp at index {index}") from exc
        if open_ms < 0 or close_ms < open_ms:
            raise ValueError(f"Invalid Binance candle time range at index {index}")
        if open_ms % 86_400_000 != 0 or close_ms != open_ms + 86_400_000 - 1:
            raise ValueError(f"Binance candle at index {index} is not a complete UTC daily interval")
        open_price, high, low, close = [
            _finite_positive(row[column], f"OHLC price at index {index}")
            for column in range(1, 5)
        ]
        if high < low or not low <= open_price <= high or not low <= close <= high:
            raise ValueError(f"Inconsistent OHLC prices at index {index}")
        if close_ms <= now_ms:
            completed.append((day, open_ms, close_ms, close))

    if len(completed) < 351:
        raise ValueError("Insufficient completed Binance daily candles (need at least 351)")
    dates = [candle[0] for candle in completed]
    if len(set(dates)) != len(dates):
        raise ValueError("Duplicate Binance candle dates")
    if any(later <= earlier for earlier, later in zip(dates, dates[1:])):
        raise ValueError("Binance candle dates are not strictly chronological")
    if any(later - earlier != timedelta(days=1) for earlier, later in zip(dates, dates[1:])):
        raise ValueError("Gap in Binance daily candles; data was not interpolated")
    return [day.isoformat() for day in dates], [candle[3] for candle in completed]


def validate_score(value, name="score"):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    if not math.isfinite(value) or value < -3 or value > 3:
        raise ValueError(f"{name} is outside the supported -3 to +3 display range")
    return float(value)


def validate_history(history):
    """Validate history without modifying it; return the number of observations."""
    if not isinstance(history, list):
        raise ValueError("History must be a list")
    seen = set()
    previous = None
    for index, point in enumerate(history):
        if not isinstance(point, dict):
            raise ValueError(f"History entry {index} must be an object")
        raw_date = point.get("date")
        if not isinstance(raw_date, str):
            raise ValueError(f"History entry {index} has no ISO date")
        try:
            parsed = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ValueError(f"History entry {index} has an invalid date") from exc
        if parsed.isoformat() != raw_date:
            raise ValueError(f"History entry {index} date must use YYYY-MM-DD")
        if raw_date in seen:
            raise ValueError(f"Duplicate history date: {raw_date}")
        if previous is not None and parsed <= previous:
            raise ValueError("History dates must be in strictly chronological order")
        validate_score(point.get("score"), f"history score for {raw_date}")
        seen.add(raw_date)
        previous = parsed
    return len(history)


def sma(values, length):
    if len(values) < length:
        return None
    return sum(values[-length:]) / length


def rsi_wilder(closes, length=14):
    if len(closes) <= length:
        return None
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = sum(gains[:length]) / length
    avg_loss = sum(losses[:length]) / length
    for gain, loss in zip(gains[length:], losses[length:]):
        avg_gain = (avg_gain * (length - 1) + gain) / length
        avg_loss = (avg_loss * (length - 1) + loss) / length
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def new_indicator(name):
    return {
        "name": name,
        "category": CATEGORIES[name],
        "score": None,
        "rawValue": None,
        "status": "unverified",
        "source": SOURCE_LINKS[name],
        "lastUpdated": None,
        "note": "Awaiting a verified free data feed and approved score mapping."
    }


def load_previous():
    try:
        with OUTPUT.open("r", encoding="utf-8") as file:
            previous = json.load(file)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        # Do not replace an unreadable file that may contain manually researched history.
        raise RuntimeError(f"Refusing to overwrite unreadable existing data file: {exc}") from exc
    if not isinstance(previous, dict):
        raise RuntimeError("Refusing to overwrite existing data file with invalid top-level structure")
    return previous


def failure_record(feed, exc):
    return {"feed": feed, "type": type(exc).__name__, "message": str(exc)}


def write_github_summary(output):
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    failures = output["feedFailures"]
    with open(summary_path, "a", encoding="utf-8") as summary:
        summary.write("## SDCA data update\n\n")
        summary.write(f"- Raw readings available: {output['dataIntegrity']['rawReadingsAvailable']}\n")
        summary.write(f"- Verified SDCA scores: {output['dataIntegrity']['verifiedScores']}\n")
        summary.write(f"- Bitcoin daily close: {output['bitcoinPriceUSDT']['status']}\n")
        summary.write(f"- Valid historical observations: {output['historyValidation']['validCount']}\n")
        if failures:
            summary.write("\n### Feed failures\n\n")
            for failure in failures:
                safe = failure["message"].replace("\r", " ").replace("\n", " ")
                summary.write(f"- **{failure['feed']}** ({failure['type']}): {safe}\n")
        else:
            summary.write("\nNo attempted feed failures.\n")
        if not output["historyValidation"]["valid"]:
            safe_error = str(output["historyValidation"]["error"]).replace("\r", " ").replace("\n", " ")
            summary.write(f"\n### History validation\n\n{safe_error}\n")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    previous = load_previous()
    indicators = [new_indicator(name) for name in SOURCE_LINKS]
    by_name = {item["name"]: item for item in indicators}
    failures = []
    btc_price = {
        "usdt": None, "status": "unavailable",
        "source": BINANCE_DOCS, "quoteCurrency": "USDT", "lastUpdated": None
    }

    try:
        candle_dates, closes = get_daily_closes(now=now)
        latest_date = candle_dates[-1]
        btc_price.update({"usdt": closes[-1], "status": "available", "lastUpdated": latest_date})
        rsi = rsi_wilder(closes, 14)
        if rsi is not None and math.isfinite(rsi):
            by_name["Bitcoin RSI"].update({
                "rawValue": round(rsi, 4), "status": "raw_available_score_pending",
                "source": BINANCE_DOCS, "referenceSource": SOURCE_LINKS["Bitcoin RSI"],
                "lastUpdated": latest_date,
                "calculation": "Wilder RSI(14), daily BTCUSDT closes",
                "note": "Raw calculation from completed public Binance BTCUSDT candles; score mapping is not implemented."
            })
        ma111, ma350 = sma(closes, 111), sma(closes, 350)
        if ma111 is not None and ma350 is not None and ma350 > 0:
            # Raw indicator calculation retained; no SDCA transformation is applied.
            ratio = ma111 / (2 * ma350)
            by_name["Bitcoin Pi Cycle Top"].update({
                "rawValue": round(ratio, 6), "status": "raw_available_score_pending",
                "source": BINANCE_DOCS, "referenceSource": SOURCE_LINKS["Bitcoin Pi Cycle Top"],
                "lastUpdated": latest_date,
                "calculation": "111-day SMA / (2 × 350-day SMA), completed daily BTCUSDT closes",
                "note": "Raw calculation only; no SDCA score mapping is implemented."
            })
    except Exception as exc:
        failures.append(failure_record("Binance BTCUSDT daily candles", exc))
        btc_price["error"] = {"type": type(exc).__name__, "message": str(exc)}
        for name in ("Bitcoin RSI", "Bitcoin Pi Cycle Top"):
            by_name[name].update({
                "status": "feed_error", "error": {"type": type(exc).__name__, "message": str(exc)},
                "note": f"Binance candle feed failed: {exc}"
            })

    try:
        payload = get_json(FNG_URL)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list) or not payload["data"]:
            raise ValueError("Alternative.me response is missing data rows")
        row = payload["data"][0]
        if not isinstance(row, dict):
            raise ValueError("Alternative.me data row must be an object")
        if isinstance(row.get("value"), bool):
            raise ValueError("Alternative.me Fear & Greed value is malformed")
        value = float(row["value"])
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError("Alternative.me Fear & Greed value must be finite and between 0 and 100")
        timestamp_raw = row["timestamp"]
        if isinstance(timestamp_raw, bool):
            raise ValueError("Alternative.me timestamp is malformed")
        timestamp = int(timestamp_raw)
        if float(timestamp_raw) != timestamp:
            raise ValueError("Alternative.me timestamp must be integer seconds")
        observed_at = datetime.fromtimestamp(timestamp, timezone.utc)
        if observed_at > now or timestamp <= 0:
            raise ValueError("Alternative.me timestamp is invalid or in the future")
        by_name["Crypto Fear and Greed Index"].update({
            "rawValue": value, "status": "raw_available_source_substitute",
            "source": FNG_SOURCE, "referenceSource": SOURCE_LINKS["Crypto Fear and Greed Index"],
            "substituteProvider": "Alternative.me", "substituteStatus": "substitute_not_equivalent_verified",
            "candidateApi": FNG_URL, "lastUpdated": iso_utc(observed_at),
            "note": "Alternative.me reading is a substitute for the selected CoinStats source; equivalence is unverified. No SDCA score is assigned."
        })
    except Exception as exc:
        failures.append(failure_record("Alternative.me Fear & Greed", exc))
        by_name["Crypto Fear and Greed Index"].update({
            "status": "feed_error", "error": {"type": type(exc).__name__, "message": str(exc)},
            "note": f"Alternative.me feed failed: {exc}"
        })

    history = previous.get("history", [])
    try:
        valid_history_count = validate_history(history)
        history_validation = {"valid": True, "validCount": valid_history_count, "error": None}
    except ValueError as exc:
        # Keep historical material byte-for-byte at the JSON-value level; suppress display instead.
        history_validation = {"valid": False, "validCount": 0, "error": str(exc)}

    raw_available = sum(item["rawValue"] is not None for item in indicators)
    verified_scores = 0  # Deliberately unimplemented until scoring rules are approved.
    output = {
        "schemaVersion": 2,
        "updatedAt": iso_utc(now),
        "status": "partial",
        "feedFailures": failures,
        "historyValidation": history_validation,
        "dataIntegrity": {
            "indicatorCount": len(indicators), "rawReadingsAvailable": raw_available,
            "verifiedScores": verified_scores,
            "missingRawReadings": len(indicators) - raw_available,
            "unverifiedScores": len(indicators) - verified_scores,
            "compositeCalculated": False,
            "message": "Raw readings only. SDCA scoring and composite calculation are not implemented."
        },
        "bitcoinPriceUSDT": btc_price,
        "indicators": indicators,
        "compositeScore": None,
        "compositeLabel": "Unavailable",
        "history": history,
        "note": "BTC daily candles are quoted in USDT. No live USD quote is configured. Missing values are not neutral; scores and composite are withheld pending approved rules."
    }

    fd, temp_path = tempfile.mkstemp(prefix="sdca-", suffix=".json", dir=DATA_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(output, file, indent=2, ensure_ascii=False, allow_nan=False)
            file.write("\n")
        os.replace(temp_path, OUTPUT)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    write_github_summary(output)
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    print(f"Indicators listed: {len(indicators)}")
    print(f"Raw readings available: {raw_available}")
    print(f"Feed failures: {len(failures)}")
    if failures:
        for failure in failures:
            print(f"Feed failure — {failure['feed']}: {failure['type']}: {failure['message']}")
    print("SDCA scores and composite remain unimplemented pending approved rules.")


if __name__ == "__main__":
    main()
