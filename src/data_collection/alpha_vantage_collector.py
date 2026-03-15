"""
Alpha Vantage data collector for DebateTrader.

Purpose : Collect daily adjusted OHLCV to cross-validate Yahoo Finance prices.
Endpoint: TIME_SERIES_DAILY_ADJUSTED

Output  : data/sample/price/alpha_vantage_ohlcv.parquet

Key rotation:
  Reads ALPHA_VANTAGE_API_KEY_1 / _2 / _3 from .env.
  Free tier allows 25 requests/day per key, so 3 keys = 75 req/day total —
  enough to cover the 33-ticker weekly pool.
  If a key is exhausted (rate-limit note in response), the next key is tried
  automatically.
"""
from __future__ import annotations

import sys
import os
import time
import logging

import pandas as pd
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from src.data_collection.config import (
    TICKERS, SAMPLE_START, SAMPLE_END,
    AV_BASE_URL, AV_RATE_LIMIT_SLEEP, AV_REQUEST_TIMEOUT,
    PRICE_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

def _get_api_keys() -> list[str]:
    """Read up to 3 AV keys from environment. Raises if none found."""
    keys = []
    for i in range(1, 4):
        key = os.environ.get(f"ALPHA_VANTAGE_API_KEY_{i}", "").strip()
        if key:
            keys.append(key)
    if not keys:
        raise EnvironmentError(
            "No Alpha Vantage API keys found.\n"
            "  Set ALPHA_VANTAGE_API_KEY_1 (and optionally _2, _3) in .env.\n"
            "  Free keys: https://www.alphavantage.co/support/#api-key"
        )
    logger.info(f"[AlphaVantage] {len(keys)} API key(s) loaded.")
    return keys


def _is_rate_limited(data: dict) -> bool:
    """Return True if the response body signals a rate-limit or daily quota hit."""
    for field in ("Note", "Information"):
        msg = data.get(field, "")
        if msg:
            logger.warning(f"  Alpha Vantage message ({field}): {msg[:160]}")
            return True
    return False


# ---------------------------------------------------------------------------
# Single-ticker fetch
# ---------------------------------------------------------------------------

def _fetch_daily(ticker: str, api_key: str) -> pd.DataFrame | None:
    """
    Call TIME_SERIES_DAILY (free-tier endpoint) for one ticker.
    Returns full-history DataFrame, or None on failure.

    Note: TIME_SERIES_DAILY_ADJUSTED is premium-only.
    For cross-validation purposes the unadjusted close is sufficient.
    """
    params = {
        "function":   "TIME_SERIES_DAILY",
        "symbol":     ticker,
        "outputsize": "compact",   # free tier only; returns last 100 trading days
        "datatype":   "json",
        "apikey":     api_key,
    }
    try:
        resp = requests.get(AV_BASE_URL, params=params, timeout=AV_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.error(f"  Network error for {ticker}: {exc}")
        return None

    if _is_rate_limited(data):
        return None
    if "Error Message" in data:
        logger.error(f"  API error for {ticker}: {data['Error Message']}")
        return None
    if "Time Series (Daily)" not in data:
        logger.warning(f"  Unexpected response for {ticker}: {list(data.keys())}")
        return None

    rows = [
        {
            "date":    date_str,
            "ticker":  ticker,
            "open":    float(v["1. open"]),
            "high":    float(v["2. high"]),
            "low":     float(v["3. low"]),
            "close":   float(v["4. close"]),
            "volume":  int(v["5. volume"]),
        }
        for date_str, v in data["Time Series (Daily)"].items()
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])   # datetime64 for parquet
    return df.sort_values("date").reset_index(drop=True)


def _fetch_with_key_rotation(
    ticker: str, keys: list[str]
) -> pd.DataFrame | None:
    """Try each API key in order; return first successful result."""
    for idx, key in enumerate(keys):
        logger.info(f"  Trying API key {idx + 1}/{len(keys)} ...")
        result = _fetch_daily(ticker, key)
        if result is not None:
            return result
        logger.warning(f"  Key {idx + 1} failed for {ticker}. Trying next key.")
        time.sleep(2)   # brief pause before switching keys

    logger.error(f"  All {len(keys)} API keys exhausted for {ticker}.")
    return None


# ---------------------------------------------------------------------------
# Main collection function
# ---------------------------------------------------------------------------

def collect_alpha_vantage_prices(
    tickers: list[str] = TICKERS,
    start: str = SAMPLE_START,
    end: str = SAMPLE_END,
    output_dir: str = PRICE_DIR,
) -> pd.DataFrame:
    """
    Download daily adjusted prices from Alpha Vantage and filter to [start, end].
    Rotates across up to 3 API keys if rate limits are hit.
    """
    keys = _get_api_keys()
    start_dt = pd.to_datetime(start)
    end_dt   = pd.to_datetime(end)

    logger.info(
        f"[AlphaVantage] Collecting OHLCV  {start} → {end}  tickers={tickers}"
    )
    os.makedirs(output_dir, exist_ok=True)

    frames = []
    for i, ticker in enumerate(tickers):
        logger.info(f"  [{i + 1}/{len(tickers)}] {ticker} ...")
        df = _fetch_with_key_rotation(ticker, keys)

        if df is None:
            logger.warning(f"  Skipping {ticker} — all keys failed.")
        else:
            df = df[(df["date"] >= start_dt) & (df["date"] <= end_dt)].copy()
            logger.info(f"    {len(df)} rows in date range")
            frames.append(df)

        # Rate-limit pause (skip after last ticker)
        if i < len(tickers) - 1:
            logger.info(f"    Waiting {AV_RATE_LIMIT_SLEEP}s (rate limit) ...")
            time.sleep(AV_RATE_LIMIT_SLEEP)

    if not frames:
        logger.error("[AlphaVantage] No data collected.")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    out_path = os.path.join(output_dir, "alpha_vantage_ohlcv.parquet")
    combined.to_parquet(out_path, index=False, engine="pyarrow")
    logger.info(f"[AlphaVantage] OHLCV saved → {out_path}  ({len(combined)} rows)")
    return combined


def run(tickers=TICKERS, start=SAMPLE_START, end=SAMPLE_END):
    collect_alpha_vantage_prices(tickers, start, end)
    logger.info("[AlphaVantage] Collection complete.")


if __name__ == "__main__":
    load_dotenv()
    run()
