"""
Price data collector for DebateTrader.

Collects:
  - Daily OHLCV price data  →  data/sample/price/price_ohlcv.parquet

Source: Yahoo Finance (yfinance)

NOTE: Fundamental data collection is handled separately by
      src/data_collection/fundamental_collector.py.

Downstream consumers:
  - Technical Analyst agent  (OHLCV)
  - Price Validator          (cross-validation against Alpha Vantage)
"""
from __future__ import annotations

import sys
import os
import logging

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from src.data_collection.config import (
    TICKERS, YFINANCE_TICKER_MAP,
    SAMPLE_START, SAMPLE_END,
    PRICE_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OHLCV
# ---------------------------------------------------------------------------

def collect_ohlcv(
    tickers: list[str] = TICKERS,
    start: str = SAMPLE_START,
    end: str = SAMPLE_END,
    output_dir: str = PRICE_DIR,
) -> pd.DataFrame:
    """Download daily OHLCV from Yahoo Finance for all tickers."""
    logger.info(f"[PriceCollector] Collecting OHLCV  {start} → {end}  tickers={tickers}")
    os.makedirs(output_dir, exist_ok=True)

    records = []
    for canonical in tickers:
        yf_sym = YFINANCE_TICKER_MAP.get(canonical, canonical)
        logger.info(f"  {canonical} (yf={yf_sym}) ...")
        try:
            df = yf.Ticker(yf_sym).history(start=start, end=end, auto_adjust=False)

            if df.empty:
                logger.warning(f"  No data returned for {canonical}")
                continue

            df = df.reset_index()
            col_map = {
                "Date":         "date",
                "Open":         "open",
                "High":         "high",
                "Low":          "low",
                "Close":        "close",
                "Adj Close":    "adj_close",
                "Volume":       "volume",
                "Dividends":    "dividends",
                "Stock Splits": "stock_splits",
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

            # Ensure datetime64 (parquet requires it, not Python date objects)
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)

            if "adj_close" not in df.columns:
                df["adj_close"] = df["close"]

            df["ticker"] = canonical
            keep = ["date", "ticker", "open", "high", "low", "close", "adj_close",
                    "volume", "dividends", "stock_splits"]
            records.append(df[[c for c in keep if c in df.columns]])
            logger.info(f"    {len(df)} rows")

        except Exception as exc:
            logger.error(f"  Error fetching OHLCV for {canonical}: {exc}")

    if not records:
        logger.error("No OHLCV data collected.")
        return pd.DataFrame()

    combined = pd.concat(records, ignore_index=True)
    out_path = os.path.join(output_dir, "price_ohlcv.parquet")
    combined.to_parquet(out_path, index=False, engine="pyarrow")
    logger.info(f"[PriceCollector] OHLCV saved → {out_path}  ({len(combined)} rows)")
    return combined


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(tickers=TICKERS, start=SAMPLE_START, end=SAMPLE_END):
    collect_ohlcv(tickers, start, end)
    logger.info("[PriceCollector] OHLCV collection complete.")


if __name__ == "__main__":
    load_dotenv()
    run()
