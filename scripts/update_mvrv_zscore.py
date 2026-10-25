#!/usr/bin/env python3
"""Fetch, validate, score, and publish Explore21's Bitcoin MVRV Z-Score history.

Explore21 publishes this data under CC BY 4.0. The score is a project-defined
expanding historical-percentile transform, not an Explore21 trading signal.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "mvrv-z-score.json"
SOURCE_URL = "https://charts.explore21.com/data/bitcoin-mvrv-z-score.csv"
CHART_URL = "https://charts.explore21.com/bitcoin-mvrv-z-score"
DATA_CATALOG_URL = "https://charts.explore21.com/data"
LICENSE = "CC BY 4.0"
MIN_OBSERVATIONS = 30
MAX_STALENESS_DAYS = 4
MAX_FUTURE_DAYS = 0

# Values published in Explore21's cycle-comparison page, rounded to 2 decimals.
# They guard against schema changes, wrong series, or silently shifted dates.
REFERENCE_ANCHORS = {
    "2013-12-04": 6.22,
    "2015-01-14": -0.57,
    "2017-12-16": 8.71,
    "2018-12-15": -0.47,
    "2021-11-08": 3.42,
    "2022-11-21": -0.31,
    "2025-10-06": 2.48,
    "2026-06-30": 0.18,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def fetch_csv(url: str = SOURCE_URL) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "JXProbability-MVRV-Research/1.0 (+https://github.com/JayyTrader/JayyTrader)",
            "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.1",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            content_type = response.headers.get_content_type()
            if content_type not in ("text/csv", "text/plain", "application/octet-stream"):
                raise ValueError(f"Unexpected Explore21 CSV content type: {content_type}")
            payload = response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Unable to download Explore21 MVRV Z-Score CSV: {exc}") from exc
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Explore21 CSV is not valid UTF-8") from exc


def parse_csv(text: str, today: date | None = None) -> list[dict]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Explore21 CSV is empty")
    reader = csv.DictReader(io.StringIO(text))
    expected = {"date", "mvrv_z_score", "btc_close_usd"}
    headers = {header.strip() for header in (reader.fieldnames or []) if header}
    if not expected.issubset(headers):
        raise ValueError(f"CSV headers must include {sorted(expected)}; received {sorted(headers)}")

    today = today or utc_now().date()
    rows = []
    seen_dates = set()
    previous_date = None
    for line_number, row in enumerate(reader, start=2):
        try:
            day = date.fromisoformat(row["date"].strip())
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"Invalid date at CSV line {line_number}") from exc
        if day in seen_dates:
            raise ValueError(f"Duplicate date in Explore21 CSV: {day.isoformat()}")
        if day > today:
            raise ValueError(f"Explore21 CSV contains a future date: {day.isoformat()}")
        if previous_date is not None and day <= previous_date:
            raise ValueError("Explore21 CSV dates must be strictly chronological")
        if previous_date is not None and (day - previous_date).days != 1:
            raise ValueError(f"Gap in Explore21 daily series between {previous_date} and {day}")

        raw_z = row["mvrv_z_score"].strip()
        raw_close = row["btc_close_usd"].strip()
        if not raw_z or not raw_close:
            raise ValueError(f"Missing MVRV Z-Score or BTC close on {day.isoformat()}")
        try:
            z_score = float(raw_z)
            close = float(raw_close)
        except ValueError as exc:
            raise ValueError(f"Non-numeric value on {day.isoformat()}") from exc
        if not math.isfinite(z_score) or not math.isfinite(close) or close <= 0:
            raise ValueError(f"Invalid numeric value on {day.isoformat()}")

        rows.append({"date": day.isoformat(), "rawValue": z_score, "btcCloseUsd": close})
        seen_dates.add(day)
        previous_date = day

    if len(rows) < 1000:
        raise ValueError(f"Historical series unexpectedly short: {len(rows)} rows")
    if rows[0]["date"] > "2011-10-31":
        raise ValueError(f"Historical series starts unexpectedly late: {rows[0]['date']}")
    if rows[-1]["date"] < (today.fromordinal(today.toordinal() - MAX_STALENESS_DAYS)).isoformat():
        raise ValueError(f"Explore21 series is stale; latest row is {rows[-1]['date']}")
    return rows


def validate_reference_anchors(rows: list[dict], tolerance: float = 0.021) -> dict:
    by_date = {row["date"]: row["rawValue"] for row in rows}
    checked = []
    mismatches = []
    for day, published_value in REFERENCE_ANCHORS.items():
        actual = by_date.get(day)
        if actual is None:
            mismatches.append({"date": day, "expected": published_value, "actual": None})
        elif abs(actual - published_value) > tolerance:
            mismatches.append({"date": day, "expected": published_value, "actual": actual})
        else:
            checked.append(day)
    if mismatches:
        details = ", ".join(
            f"{item['date']} expected {item['expected']}, got {item['actual']}"
            for item in mismatches
        )
        raise ValueError(f"Explore21 CSV failed published cycle-anchor validation: {details}")
    return {"valid": True, "checkedCount": len(checked), "checkedDates": checked}


def score_history(rows: list[dict], minimum_observations: int = MIN_OBSERVATIONS) -> list[dict]:
    """Use only data through each date; lower percentile means cheaper valuation."""
    if minimum_observations < 2:
        raise ValueError("minimum_observations must be at least 2")
    observed = []
    output = []
    for row in rows:
        value = row["rawValue"]
        observed.append(value)
        if len(observed) < minimum_observations:
            percentile = None
            score = None
        else:
            # Strictly lower readings match Explore21's wording, 'higher than on X% of days'.
            percentile = 100.0 * sum(prior < value for prior in observed) / len(observed)
            score = max(-2.0, min(2.0, 2.0 - 4.0 * percentile / 100.0))
        output.append({
            **row,
            "historicalPercentile": round(percentile, 4) if percentile is not None else None,
            "score": round(score, 4) if score is not None else None,
        })
    return output


def build_payload(text: str, now: datetime | None = None) -> dict:
    now = now or utc_now()
    rows = parse_csv(text, today=now.date())
    anchor_validation = validate_reference_anchors(rows)
    scored = score_history(rows)
    latest = scored[-1]
    if latest["score"] is None or latest["historicalPercentile"] is None:
        raise ValueError("Latest MVRV Z-Score could not be scored")
    return {
        "schemaVersion": 1,
        "status": "available",
        "updatedAt": now.isoformat(timespec="seconds"),
        "sourceUpdatedAt": latest["date"],
        "source": SOURCE_URL,
        "referenceSource": CHART_URL,
        "dataCatalog": DATA_CATALOG_URL,
        "license": LICENSE,
        "attribution": f"Explore21 Charts, “Bitcoin MVRV Z-Score”, accessed {now.date().strftime('%d %B %Y')}.",
        "methodology": {
            "rawIndicator": "Explore21's expanding-window MVRV Z-Score: (market cap - realized cap) / expanding standard deviation of market cap.",
            "score": "2 - 4 × (expanding historical percentile / 100), clipped to [-2, +2].",
            "percentile": "Percentage of observations available on or before that date with a strictly lower raw MVRV Z-Score.",
            "minimumObservations": MIN_OBSERVATIONS,
            "lookaheadBias": False,
            "interpretation": {
                "+2": "Historically low valuation",
                "0": "Middle of the historical distribution",
                "-2": "Historically high valuation",
            },
            "warning": "This is a research normalization, not an Explore21 signal, forecast, or investment recommendation.",
        },
        "validation": {
            "rowCount": len(scored),
            "firstDate": scored[0]["date"],
            "lastDate": scored[-1]["date"],
            "referenceAnchors": anchor_validation,
        },
        "latest": {
            "date": latest["date"],
            "rawValue": round(latest["rawValue"], 4),
            "historicalPercentile": latest["historicalPercentile"],
            "score": latest["score"],
            "btcCloseUsd": round(latest["btcCloseUsd"], 2),
        },
        "history": scored,
    }


def write_payload(payload: dict, output: Path = OUTPUT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="mvrv-z-score-", suffix=".json", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(temp_name, output)
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)


def main() -> None:
    now = utc_now()
    payload = build_payload(fetch_csv(), now=now)
    write_payload(payload)
    latest = payload["latest"]
    print(f"Explore21 MVRV Z-Score updated: {latest['date']}")
    print(f"Raw Z-Score: {latest['rawValue']}; percentile: {latest['historicalPercentile']}%; score: {latest['score']}")
    print(f"Validated {payload['validation']['rowCount']} rows and {payload['validation']['referenceAnchors']['checkedCount']} published cycle anchors.")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write("## Explore21 MVRV Z-Score update\n\n")
            summary.write(f"- Historical observations: {payload['validation']['rowCount']}\n")
            summary.write(f"- Latest source date: {latest['date']}\n")
            summary.write(f"- Raw Z-Score: {latest['rawValue']}\n")
            summary.write(f"- Historical percentile: {latest['historicalPercentile']}%\n")
            summary.write(f"- Normalized score: {latest['score']} / +2 to -2\n")
            summary.write(f"- Published cycle anchors validated: {payload['validation']['referenceAnchors']['checkedCount']}\n")


if __name__ == "__main__":
    main()
