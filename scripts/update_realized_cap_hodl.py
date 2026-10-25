#!/usr/bin/env python3
"""Fetch the latest publicly displayed Glassnode Realized Cap HODL Waves 1W–1M share.

This intentionally reads the public HTML page, not a private API or paid endpoint.
The job fails closed if the expected latest-value text is missing or stale.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "realized-cap-hodl-waves.json"
SOURCE_URL = "https://studio.glassnode.com/charts/supply.RcapHodlWaves?a=BTC"
MAX_STALENESS_DAYS = 4


def fetch_page() -> str:
    request = Request(
        SOURCE_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; JXProbabilityResearch/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(f"Glassnode page returned HTTP {response.status}")
            return response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not retrieve public Glassnode chart page: {exc}") from exc


def parse_latest(html: str, today: date | None = None) -> dict:
    # Read the public rendered/embedded page text only; never infer values from pixels.
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    text = re.sub(r"\s+", " ", text).strip()
    date_match = re.search(
        r"Latest Values\s+as of\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    band_match = re.search(r"1w\s*[-–]\s*1m\s+([0-9]+(?:\.[0-9]+)?)\s*%", text, flags=re.IGNORECASE)
    if not date_match or not band_match:
        raise ValueError("Expected Glassnode 'Latest Values' date and 1w-1m percentage were not found in public page text.")

    observed_date = datetime.strptime(date_match.group(1), "%d %b %Y").date()
    percent = float(band_match.group(1))
    today = today or datetime.now(timezone.utc).date()
    age_days = (today - observed_date).days
    if not 0 <= age_days <= MAX_STALENESS_DAYS:
        raise ValueError(f"Glassnode latest value is stale or future-dated: {observed_date} (age {age_days} days).")
    if not 0 <= percent <= 100:
        raise ValueError(f"Invalid 1W-1M percentage: {percent}")

    # User-defined linear mapping: 10%=+2, 30%=0, 50%=-2, clamped.
    score = max(-2.0, min(2.0, 3.0 - percent / 10.0))
    return {
        "schemaVersion": 1,
        "status": "available",
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sourceDate": observed_date.isoformat(),
        "source": SOURCE_URL,
        "metric": "Realized Cap HODL Waves 1W–1M share of USD-denominated realized capitalization",
        "inputMethod": "Automated extraction of the publicly displayed latest value; no API key or paid API used",
        "bandPercent": percent,
        "score": round(score, 4),
        "scoring": {
            "10%": 2,
            "20%": 1,
            "30%": 0,
            "40%": -1,
            "50%": -2,
            "formula": "clamp(3 - percentage / 10, -2, +2)",
        },
        "validation": {"ageDays": age_days, "maxAllowedAgeDays": MAX_STALENESS_DAYS},
    }


def main() -> None:
    payload = parse_latest(fetch_page())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Saved 1W–1M={payload['bandPercent']}%, score={payload['score']}, source date={payload['sourceDate']}")


if __name__ == "__main__":
    main()
