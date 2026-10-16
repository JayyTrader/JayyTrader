#!/usr/bin/env python3
"""Collect public SDCA raw data without inventing scores or history."""

import csv
import io
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
COINSENTRY_RSI_URL = "https://coinsentry.app/api/v1/indicators.json"
DURDEN_DAILY_CSV_URL = "https://cdn.durdenbtc.com/btc-full-price-data/BTC_daily.csv"
BINANCE_DOCS = "https://developers.binance.com/en/docs/products/spot/rest-api"
FNG_SOURCE = "https://alternative.me/crypto/fear-and-greed-index/"
COINSENTRY_ATTRIBUTION_URL = "https://coinsentry.app/"
COINSENTRY_RSI_PAGE = "https://coinsentry.app/indicators/bitcoin-rsi?hide=daily%2Cmonthly"
DURDEN_DHO_PAGE = "https://durdenbtc.com/charts/btc-damped-harmonic-oscillator"
DURDEN_PI_PAGE = "https://durdenbtc.com/charts/btc-pi-cycle-top"
MAX_SOURCE_AGE_DAYS = 2
DURDEN_FIRST_CSV_DATE = date(2010, 7, 13)
DURDEN_PI_REFERENCE_DATE = "2026-10-09"
DURDEN_PI_PUBLISHED_VALUE = 0.460

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


def get_text(url):
    request = urllib.request.Request(url, headers={"User-Agent": "JayyTrader-SDCA/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return response.read().decode("utf-8-sig")


def _iso_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must use YYYY-MM-DD")
    return parsed


def _validate_source_date(raw_date, now, feed_name):
    observed = _iso_date(raw_date, f"{feed_name} observation date")
    if observed >= now.date():
        raise ValueError(f"{feed_name} observation is not a completed daily close")
    age = (now.date() - observed).days
    if age > MAX_SOURCE_AGE_DAYS:
        raise ValueError(f"{feed_name} observation is stale ({age} days old)")
    return observed


def parse_coinsentry_weekly_rsi(payload, now=None):
    """Read only CoinSentry's published rsi_weekly field; never fall back to daily RSI."""
    now = now or utc_now()
    if not isinstance(payload, dict) or payload.get("source") != "coinsentry":
        raise ValueError("CoinSentry response has an invalid source schema")
    rows = payload.get("indicators")
    if not isinstance(rows, list):
        raise ValueError("CoinSentry response is missing its indicators array")
    matches = [row for row in rows if isinstance(row, dict) and row.get("code") == "rsi_weekly"]
    if len(matches) != 1:
        raise ValueError("CoinSentry response must contain exactly one rsi_weekly field")
    row = matches[0]
    description = row.get("description")
    if not isinstance(description, str) or "14-period weekly RSI" not in description:
        raise ValueError("CoinSentry rsi_weekly definition is missing or changed")
    raw = row.get("value")
    if isinstance(raw, bool):
        raise ValueError("CoinSentry rsi_weekly value is malformed")
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("CoinSentry rsi_weekly value is malformed") from exc
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError("CoinSentry rsi_weekly must be between 0 and 100")
    observed = _validate_source_date(row.get("date"), now, "CoinSentry weekly RSI")
    attribution = payload.get("attribution")
    if not isinstance(attribution, str) or "coinsentry.app" not in attribution.lower():
        raise ValueError("CoinSentry attribution and visible backlink requirement are missing")
    return {
        "value": value,
        "date": observed.isoformat(),
        "description": description,
        "attribution": attribution,
    }


def parse_durden_daily_csv(contents, now=None):
    """Validate DurdenBTC daily OHLCV rows and return completed, contiguous closes."""
    now = now or utc_now()
    if not isinstance(contents, str) or not contents.strip():
        raise ValueError("DurdenBTC CSV is empty or malformed")
    reader = csv.DictReader(io.StringIO(contents))
    expected = ["Date", "Open", "High", "Low", "Close", "Volume"]
    if reader.fieldnames != expected:
        raise ValueError("DurdenBTC CSV schema does not match Date/Open/High/Low/Close/Volume")
    dates, closes = [], []
    for index, row in enumerate(reader):
        if not isinstance(row, dict) or any(row.get(field) is None for field in expected):
            raise ValueError(f"Malformed DurdenBTC CSV row at index {index}")
        day = _iso_date(row["Date"], f"DurdenBTC date at row {index}")
        if day > now.date():
            raise ValueError(f"DurdenBTC CSV contains a future date at row {index}")
        if dates and day <= dates[-1]:
            if day == dates[-1]:
                raise ValueError(f"Duplicate DurdenBTC CSV date: {day.isoformat()}")
            raise ValueError("DurdenBTC CSV dates are not strictly chronological")
        open_price, high, low, close = [
            _finite_positive(row[field], f"DurdenBTC {field} at row {index}")
            for field in ("Open", "High", "Low", "Close")
        ]
        if high < low or not low <= open_price <= high or not low <= close <= high:
            raise ValueError(f"Inconsistent DurdenBTC OHLC prices at row {index}")
        volume = row["Volume"]
        if isinstance(volume, bool):
            raise ValueError(f"Invalid DurdenBTC volume at row {index}")
        try:
            volume_value = float(volume)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Invalid DurdenBTC volume at row {index}") from exc
        if not math.isfinite(volume_value) or volume_value < 0:
            raise ValueError(f"Invalid DurdenBTC volume at row {index}")
        dates.append(day)
        closes.append(close)

    if not dates:
        raise ValueError("DurdenBTC CSV contains no observations")
    if dates[0] > DURDEN_FIRST_CSV_DATE:
        raise ValueError("DurdenBTC CSV is missing the source's early price history")
    if any(later - earlier != timedelta(days=1) for earlier, later in zip(dates, dates[1:])):
        raise ValueError("Gap in DurdenBTC daily CSV; data was not interpolated")

    completed = [(day, close) for day, close in zip(dates, closes) if day < now.date()]
    if len(completed) < 350:
        raise ValueError("Insufficient completed DurdenBTC daily observations (need at least 350)")
    latest = completed[-1][0]
    age = (now.date() - latest).days
    if age > MAX_SOURCE_AGE_DAYS:
        raise ValueError(f"DurdenBTC daily CSV is stale ({age} days old)")
    return [day.isoformat() for day, _ in completed], [close for _, close in completed]


def pi_cycle_ratio(closes):
    """DurdenBTC daily Pi Cycle Top ratio: 111-day SMA / (2 * 350-day SMA)."""
    if len(closes) < 350:
        raise ValueError("Pi Cycle calculation requires at least 350 daily closes")
    latest_111 = sma(closes, 111)
    latest_350 = sma(closes, 350)
    if latest_350 is None or latest_350 <= 0:
        raise ValueError("Pi Cycle 350-day average is unavailable")
    return latest_111 / (2 * latest_350)


def damped_harmonic_oscillator(dates, closes):
    """Reproduce DurdenBTC's published log-power-law damped-harmonic JavaScript."""
    if len(dates) != len(closes) or len(closes) < 350:
        raise ValueError("Damped harmonic calculation requires matching daily history with at least 350 closes")
    genesis = date(2009, 1, 3)
    day_numbers, log_prices = [], []
    for raw_day, close in zip(dates, closes):
        day = _iso_date(raw_day, "DurdenBTC calculation date")
        price = _finite_positive(close, "DurdenBTC calculation close")
        day_number = (day - genesis).days
        if day_number > 1:
            day_numbers.append(day_number)
            log_prices.append(math.log(price) / math.log(10))
    count = len(log_prices)
    if count < 350:
        raise ValueError("Damped harmonic calculation has insufficient valid history")
    log_days = [math.log(day_number) / math.log(10) for day_number in day_numbers]
    sx = sy = sxx = sxy = 0.0
    for x, y in zip(log_days, log_prices):
        sx += x
        sy += y
        sxx += x * x
        sxy += x * y
    b = (count * sxy - sx * sy) / (count * sxx - sx * sx)
    a = (sy - b * sx) / count
    deviations = [y - (a + b * x) for x, y in zip(log_days, log_prices)]
    t0 = day_numbers[0]
    elapsed = [day_number - t0 for day_number in day_numbers]
    sdd = 0.0
    for deviation in deviations:
        sdd += deviation * deviation

    gamma = 8.5e-5
    best = None
    for index in range(400):
        frequency = 0.0033 + (0.0054 - 0.0033) * index / 399
        half_gamma = gamma / 2
        damped_frequency = math.sqrt(max(frequency * frequency - half_gamma * half_gamma, 1e-8))
        s11 = s12 = s22 = sd1 = sd2 = 0.0
        for deviation, elapsed_day in zip(deviations, elapsed):
            envelope = math.exp(-half_gamma * elapsed_day)
            phase = damped_frequency * elapsed_day
            q1 = envelope * math.cos(phase)
            q2 = envelope * math.sin(phase)
            s11 += q1 * q1
            s12 += q1 * q2
            s22 += q2 * q2
            sd1 += deviation * q1
            sd2 += deviation * q2
        determinant = s11 * s22 - s12 * s12
        if abs(determinant) < 1e-30:
            continue
        c1 = (s22 * sd1 - s12 * sd2) / determinant
        c2 = (s11 * sd2 - s12 * sd1) / determinant
        sse = sdd - (c1 * sd1 + c2 * sd2)
        if best is None or sse < best[0]:
            best = (sse, damped_frequency, c1, c2)
    if best is None:
        raise ValueError("DurdenBTC damped harmonic fit could not be solved")

    _, damped_frequency, c1, c2 = best
    amplitude = math.sqrt(c1 * c1 + c2 * c2)
    phase = math.atan2(-c2, c1)
    half_gamma = gamma / 2
    residual_sse = 0.0
    for deviation, elapsed_day in zip(deviations, elapsed):
        envelope = amplitude * math.exp(-half_gamma * elapsed_day)
        fitted = envelope * math.cos(damped_frequency * elapsed_day + phase)
        difference = deviation - fitted
        residual_sse += difference * difference
    sigma = math.sqrt(residual_sse / count)

    latest_index = count - 1
    fair = a + b * log_days[latest_index]
    envelope = amplitude * math.exp(-half_gamma * elapsed[latest_index])
    denominator = max(envelope, sigma)
    if denominator <= 0 or not math.isfinite(denominator):
        raise ValueError("DurdenBTC damped harmonic scale is invalid")
    oscillator = (log_prices[latest_index] - fair) / denominator * 100
    return max(-100.0, min(100.0, oscillator))


def compare_published_display(calculated, published, decimals, feed_name):
    """Compare a reproduction with the precision actually published by its source."""
    if not math.isfinite(calculated) or not math.isfinite(published):
        raise ValueError(f"{feed_name} source comparison contains a non-finite value")
    if round(calculated, decimals) != published:
        raise ValueError(f"{feed_name} calculation does not match the published source value")
    return {
        "calculatedValue": calculated,
        "publishedValue": published,
        "displayPrecision": decimals,
        "matchedAtPublishedPrecision": True,
    }


def verify_durden_pi_reference(dates, closes):
    try:
        index = dates.index(DURDEN_PI_REFERENCE_DATE)
    except ValueError as exc:
        raise ValueError("DurdenBTC Pi Cycle reference observation is missing from its CSV") from exc
    calculated = pi_cycle_ratio(closes[:index + 1])
    comparison = compare_published_display(
        calculated, DURDEN_PI_PUBLISHED_VALUE, 3, "DurdenBTC Pi Cycle"
    )
    comparison.update({
        "comparisonDate": DURDEN_PI_REFERENCE_DATE,
        "sourcePublishedDate": DURDEN_PI_REFERENCE_DATE,
        "source": DURDEN_PI_PAGE,
    })
    return comparison


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


def mark_feed_error(item, exc, feed_name):
    item.update({
        "rawValue": None,
        "status": "feed_error",
        "verificationStatus": "unavailable",
        "error": {"type": type(exc).__name__, "message": str(exc)},
        "note": f"{feed_name} feed failed; no reading is available.",
    })


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
    except Exception as exc:
        failures.append(failure_record("Binance BTCUSDT daily candles", exc))
        btc_price["error"] = {"type": type(exc).__name__, "message": str(exc)}

    try:
        weekly = parse_coinsentry_weekly_rsi(get_json(COINSENTRY_RSI_URL), now=now)
        by_name["Bitcoin RSI"].update({
            "rawValue": weekly["value"],
            "status": "raw_available_score_pending",
            "verificationStatus": "verified_field",
            "source": COINSENTRY_RSI_URL,
            "sourceName": "CoinSentry public indicators API",
            "sourceField": "rsi_weekly",
            "referenceSource": COINSENTRY_RSI_PAGE,
            "attributionUrl": COINSENTRY_ATTRIBUTION_URL,
            "attribution": weekly["attribution"],
            "timeframe": "weekly",
            "sourceTimestamp": weekly["date"],
            "lastUpdated": weekly["date"],
            "quoteCurrency": "USD",
            "quoteCurrencyDetails": "CoinSentry documents its Bitstamp BTC/USD close series as the underlying price source.",
            "calculation": weekly["description"],
            "verificationDetails": "The published rsi_weekly field is consumed directly; no daily RSI substitute or local transformation is used.",
            "note": "CoinSentry weekly RSI reading. A visible CoinSentry backlink is required. No SDCA score is assigned."
        })
    except Exception as exc:
        failures.append(failure_record("CoinSentry weekly RSI", exc))
        mark_feed_error(by_name["Bitcoin RSI"], exc, "CoinSentry weekly RSI")

    try:
        durden_dates, durden_closes = parse_durden_daily_csv(get_text(DURDEN_DAILY_CSV_URL), now=now)
    except Exception as exc:
        for feed_name, indicator_name in (
            ("DurdenBTC Damped Harmonic Oscillator CSV", "BTC Damped Harmonic Oscillator"),
            ("DurdenBTC Pi Cycle Top CSV", "Bitcoin Pi Cycle Top"),
        ):
            failures.append(failure_record(feed_name, exc))
            mark_feed_error(by_name[indicator_name], exc, feed_name)
    else:
        source_date = durden_dates[-1]
        by_name["BTC Damped Harmonic Oscillator"].update({
            "rawValue": None,
            "status": "unverified",
            "verificationStatus": "unavailable",
            "source": DURDEN_DAILY_CSV_URL,
            "sourceName": "DurdenBTC daily BTC close CSV",
            "referenceSource": DURDEN_DHO_PAGE,
            "timeframe": "daily",
            "quoteCurrency": "USD",
            "quoteCurrencyDetails": "DurdenBTC chart labels prices in USD; the CSV header itself does not declare a quote-currency column.",
            "sourceTimestamp": source_date,
            "lastUpdated": source_date,
            "calculation": "DurdenBTC published model: OLS fit log10(close) = a + b·log10(days since 2009-01-03); fit residuals to A·exp(−γt/2)·cos(ωd·t + φ), γ=8.5e−5, searching 400 ω values from 0.0033 to 0.0054; oscillator = clip((log10(close)−fair)/max(envelope,σ)×100, −100, +100).",
            "verificationDetails": "Reading withheld: only one ambiguous historical comparison was located, and multiple reliable date-specific reference values are unavailable. The CSV alone cannot independently verify the published oscillator output.",
            "note": "DHO is unavailable pending multiple independently supportable historical reference values. No SDCA score is assigned."
        })

        try:
            ratio = pi_cycle_ratio(durden_closes)
            source_comparison = verify_durden_pi_reference(durden_dates, durden_closes)
            by_name["Bitcoin Pi Cycle Top"].update({
                "rawValue": round(ratio, 9),
                "status": "raw_available_score_pending",
                "verificationStatus": "verified_calculation",
                "source": DURDEN_DAILY_CSV_URL,
                "sourceName": "DurdenBTC daily BTC close CSV",
                "referenceSource": DURDEN_PI_PAGE,
                "timeframe": "daily",
                "quoteCurrency": "USD",
                "quoteCurrencyDetails": "DurdenBTC chart labels prices in USD; the CSV header itself does not declare a quote-currency column.",
                "sourceTimestamp": source_date,
                "lastUpdated": source_date,
                "sourceComparison": source_comparison,
                "calculation": "111-day simple moving average of daily closes ÷ (2 × 350-day simple moving average of daily closes).",
                "verificationDetails": f"Reproduced DurdenBTC's documented 111DMA ÷ (2×350DMA) formula and matched {source_comparison['publishedValue']:.3f} on {source_comparison['comparisonDate']} at the source's displayed precision.",
                "note": "DurdenBTC Pi Cycle Top ratio. No SDCA score is assigned."
            })
        except Exception as exc:
            failures.append(failure_record("DurdenBTC Pi Cycle Top", exc))
            mark_feed_error(by_name["Bitcoin Pi Cycle Top"], exc, "DurdenBTC Pi Cycle Top")

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
