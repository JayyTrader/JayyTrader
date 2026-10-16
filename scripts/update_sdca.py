
#!/usr/bin/env python3
"""JayyTrader SDCA — free, no API keys, no fabricated scores."""

import json
import math
import os
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT = DATA_DIR / "sdca-latest.json"

SOURCE_LINKS = {
    "MVRV-Z Score": "https://www.lookintobitcoin.com/charts/mvrv-zscore/",
    "Realized Cap HODL Waves": "https://www.lookintobitcoin.com/charts/realized-cap-hodl-waves/",
    "CBBI": "https://colintalkscrypto.com/cbbi/",
    "VDD Multiple": "https://charts.bitbo.io/vdd-multiple/",
    "NUPL": "https://charts.bitbo.io/net-unrealized-profit-loss/",
    "BTC 50 MARP": "https://kotecharts.com/c/fifty-marp",
    "LTH/STH SOPR Ratio": "https://kotecharts.com/c/sopr-ratio",
    "BTC Damped Harmonic Oscillator":
        "https://durdenbtc.com/charts/btc-damped-harmonic-oscillator",
    "Bitcoin RSI":
        "https://coinsentry.app/indicators/bitcoin-rsi?hide=daily%2Cmonthly",
    "Bitcoin Pi Cycle Top": "https://durdenbtc.com/charts/btc-pi-cycle-top",
    "Market Extreme Zone Index":
        "https://www.tradingview.com/script/Z9EoqtA7-Market-Extreme-Zones-Index/",
    "Relative Valuation Oscillator":
        "https://www.tradingview.com/script/zq7SYdHZ-Relative-Valuation-Oscillator-QuantAlgo/",
    "Volume-Weighted Price Z-Score":
        "https://www.tradingview.com/script/633Bjz5u-Volume-Weighted-Price-Z-Score-QuantAlgo/",
    "Crypto Fear and Greed Index": "https://coinstats.app/fear-and-greed/",
    "Composite Sentiment Score": "https://alphabitlab.com/crypto/sentiment-lab",
}

CATEGORIES = {
    **dict.fromkeys([
        "MVRV-Z Score", "Realized Cap HODL Waves", "CBBI",
        "VDD Multiple", "NUPL", "BTC 50 MARP", "LTH/STH SOPR Ratio"
    ], "Fundamental"),
    **dict.fromkeys([
        "BTC Damped Harmonic Oscillator", "Bitcoin RSI",
        "Bitcoin Pi Cycle Top", "Market Extreme Zone Index",
        "Relative Valuation Oscillator", "Volume-Weighted Price Z-Score"
    ], "Technical"),
    **dict.fromkeys([
        "Crypto Fear and Greed Index", "Composite Sentiment Score"
    ], "Sentiment"),
}

def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def get_json(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "JayyTrader-SDCA/1.0"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))

def get_daily_closes():
    # Public Binance market-data endpoint; no API key.
    url = (
        "https://data-api.binance.vision/api/v3/klines"
        "?symbol=BTCUSDT&interval=1d&limit=500"
    )
    rows = get_json(url)
    closes = [float(row[4]) for row in rows]
    dates = [
        datetime.fromtimestamp(row[0] / 1000, timezone.utc)
        .date().isoformat()
        for row in rows
    ]
    if len(closes) < 351 or any(p <= 0 for p in closes):
        raise ValueError("Insufficient or invalid daily BTC candles")
    return dates, closes

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
            result = json.load(file)
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    previous = load_previous()
    indicators = [new_indicator(name) for name in SOURCE_LINKS]
    by_name = {item["name"]: item for item in indicators}

    btc_price = {
        "usd": None, "status": "unavailable",
        "source": "Binance public daily candles", "lastUpdated": None
    }
    data_dates = []
    closes = []

    try:
        data_dates, closes = get_daily_closes()
        btc_price = {
            "usd": closes[-1],
            "status": "available",
            "source": "Binance public BTCUSDT daily candle close",
            "lastUpdated": data_dates[-1]
        }

        rsi = rsi_wilder(closes, 14)
        if rsi is not None and math.isfinite(rsi):
            item = by_name["Bitcoin RSI"]
            item.update({
                "rawValue": round(rsi, 4),
                "status": "raw_available_score_pending",
                "lastUpdated": data_dates[-1],
                "calculation": "Wilder RSI(14), daily BTCUSDT closes",
                "note": (
                    "Calculated from public Binance candles. Verify timeframe "
                    "and settings against the selected RSI before scoring."
                )
            })

        ma111 = sma(closes, 111)
        ma350 = sma(closes, 350)
        if ma111 is not None and ma350 is not None and ma350 > 0:
            ratio = ma111 / (2 * ma350)
            item = by_name["Bitcoin Pi Cycle Top"]
            item.update({
                "rawValue": round(ratio, 6),
                "status": "raw_available_score_pending",
                "lastUpdated": data_dates[-1],
                "calculation": "111-day SMA / (2 × 350-day SMA)",
                "note": (
                    "Ratio 1.00 is the crossover. Confirm exchange and "
                    "daily-close conventions against the selected source."
                )
            })

    except Exception as exc:
        btc_price["note"] = f"Public candle retrieval failed: {exc}"
        print(f"BTC candles unavailable: {exc}")

    # Public no-key Fear & Greed feed.
    # This is Alternative.me, NOT the selected CoinStats source.
    try:
        payload = get_json(
            "https://api.alternative.me/fng/?limit=1&format=json"
        )
        row = payload["data"][0]
        value = float(row["value"])
        if not 0 <= value <= 100:
            raise ValueError("Fear & Greed value outside 0–100")

        item = by_name["Crypto Fear and Greed Index"]
        item.update({
            "rawValue": value,
            "status": "raw_available_source_substitute",
            "lastUpdated": row.get("timestamp"),
            "candidateSource": "Alternative.me",
            "candidateApi": "https://api.alternative.me/fng/?limit=1&format=json",
            "note": (
                "Alternative.me reading; not assumed identical to CoinStats. "
                "SDCA score awaits the workbook's approved transformation."
            )
        })
    except Exception as exc:
        by_name["Crypto Fear and Greed Index"]["note"] = (
            f"Alternative.me feed failed: {exc}"
        )
        print(f"Fear & Greed unavailable: {exc}")

    # Never manufacture scores. A composite is withheld until the approved
    # transformations and required valid inputs are implemented.
    history = previous.get("history", [])
    if not isinstance(history, list):
        history = []

    raw_available = sum(
        item["rawValue"] is not None for item in indicators
    )
    verified_scores = sum(
        isinstance(item["score"], (int, float))
        and item["status"] == "available"
        for item in indicators
    )

    output = {
        "updatedAt": now,
        "status": "partial",
        "dataIntegrity": {
            "indicatorCount": len(indicators),
            "rawReadingsAvailable": raw_available,
            "verifiedScores": verified_scores,
            "unverifiedOrMissing": len(indicators) - verified_scores,
            "compositeCalculated": False,
            "message": (
                "Raw data collection has begun. Composite withheld until "
                "the approved workbook scoring rules are implemented."
            )
        },
        "bitcoinPriceUSD": btc_price,
        "indicators": indicators,
        "compositeScore": None,
        "compositeLabel": "Unavailable",
        "history": history,
        "note": (
            "SDCA direction: positive = BTC cheap; negative = BTC expensive. "
            "Raw technical readings are not SDCA scores. No missing value "
            "is treated as neutral."
        )
    }

    fd, temp_path = tempfile.mkstemp(
        prefix="sdca-", suffix=".json", dir=DATA_DIR
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(output, file, indent=2, ensure_ascii=False)
            file.write("\n")
        os.replace(temp_path, OUTPUT)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    print(f"Indicators listed: {len(indicators)}")
    print(f"Raw readings available: {raw_available}")
    print("Composite withheld until scoring rules are verified.")

if __name__ == "__main__":
    main()
