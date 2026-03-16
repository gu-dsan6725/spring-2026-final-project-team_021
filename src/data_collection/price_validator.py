"""
Price cross-validator for DebateTrader.

Compares Yahoo Finance vs Alpha Vantage daily close prices.
Flags rows where the two sources disagree by more than PRICE_DISCREPANCY_THRESHOLD_PCT.

Outputs:
  data/sample/price/price_validation_report.parquet  — full comparison table
  data/sample/price/validated_ohlcv.parquet          — primary price dataset for agents
                                                        (yfinance + flag columns)

Design: Yahoo Finance is the authoritative source; Alpha Vantage is the sanity check.
"""
from __future__ import annotations

import sys
import os
import logging

import pandas as pd
import numpy as np
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from src.data_collection.config import (
    PRICE_DIR,
    PRICE_DISCREPANCY_THRESHOLD_PCT,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def validate_prices(
    yf_path: str  = os.path.join(PRICE_DIR, "price_ohlcv.parquet"),
    av_path: str  = os.path.join(PRICE_DIR, "alpha_vantage_ohlcv.parquet"),
    output_dir: str = PRICE_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Cross-validate YF vs AV close prices.
    Returns (validated_df, report_df).
    """
    logger.info("[Validator] Loading parquet files ...")
    yf_df = pd.read_parquet(yf_path)
    av_df = pd.read_parquet(av_path)
    logger.info(f"  yfinance rows      : {len(yf_df)}")
    logger.info(f"  alpha_vantage rows : {len(av_df)}")

    # Normalise date column to datetime64 so merge works regardless of file origin
    yf_df["date"] = pd.to_datetime(yf_df["date"])
    av_df["date"] = pd.to_datetime(av_df["date"])

    # ------------------------------------------------------------------ merge
    # AV free-tier returns unadjusted close only (no adj_close column)
    merged = pd.merge(
        yf_df[["date", "ticker", "close", "volume"]].rename(columns={
            "close":  "yf_close",
            "volume": "yf_volume",
        }),
        av_df[["date", "ticker", "close", "volume"]].rename(columns={
            "close":  "av_close",
            "volume": "av_volume",
        }),
        on=["date", "ticker"],
        how="inner",
    )
    logger.info(f"  Matched (date, ticker) pairs : {len(merged)}")

    # ------------------------------------------------------------------ discrepancies
    def _pct_diff(a: pd.Series, b: pd.Series) -> pd.Series:
        return (a - b).abs() / b.replace(0, np.nan) * 100

    merged["close_diff_pct"]      = _pct_diff(merged["yf_close"],     merged["av_close"])
    merged["volume_diff_pct"] = _pct_diff(merged["yf_volume"], merged["av_volume"])
    merged["price_flag"]      = merged["close_diff_pct"] > PRICE_DISCREPANCY_THRESHOLD_PCT

    # ------------------------------------------------------------------ summary
    n_total   = len(merged)
    n_flagged = int(merged["price_flag"].sum())
    flag_rate = n_flagged / n_total * 100 if n_total else 0.0

    logger.info(f"[Validator] Threshold : {PRICE_DISCREPANCY_THRESHOLD_PCT}%")
    logger.info(f"[Validator] Flagged   : {n_flagged} / {n_total}  ({flag_rate:.2f}%)")

    for ticker, grp in merged.groupby("ticker"):
        flagged  = int(grp["price_flag"].sum())
        avg_diff = grp["close_diff_pct"].mean()
        logger.info(
            f"  {ticker:6s}  flagged={flagged}/{len(grp)}"
            f"  avg_close_diff={avg_diff:.4f}%"
        )

    # ------------------------------------------------------------------ save report
    os.makedirs(output_dir, exist_ok=True)

    report_cols = [
        "date", "ticker",
        "yf_close", "av_close", "close_diff_pct",
        "yf_volume", "av_volume", "volume_diff_pct",
        "price_flag",
    ]
    report_df = merged[report_cols].sort_values(["ticker", "date"])
    report_path = os.path.join(output_dir, "price_validation_report.parquet")
    report_df.to_parquet(report_path, index=False, engine="pyarrow")
    logger.info(f"[Validator] Report saved → {report_path}")

    # ------------------------------------------------------------------ validated dataset
    flag_cols = merged[["date", "ticker", "close_diff_pct", "volume_diff_pct", "price_flag"]]
    validated = yf_df.copy()
    validated["date"] = pd.to_datetime(validated["date"])
    validated = validated.merge(flag_cols, on=["date", "ticker"], how="left")
    validated["price_flag"]     = validated["price_flag"].fillna(False)
    validated["close_diff_pct"] = validated["close_diff_pct"].fillna(0.0)
    validated["data_source"]    = "yfinance"

    validated_path = os.path.join(output_dir, "validated_ohlcv.parquet")
    validated.sort_values(["ticker", "date"]).to_parquet(
        validated_path, index=False, engine="pyarrow"
    )
    logger.info(f"[Validator] Validated OHLCV saved → {validated_path}")

    return validated, report_df


def run():
    yf_path = os.path.join(PRICE_DIR, "price_ohlcv.parquet")
    av_path = os.path.join(PRICE_DIR, "alpha_vantage_ohlcv.parquet")

    if not os.path.exists(yf_path):
        logger.error(f"Missing: {yf_path}  — run price_collector.py first.")
        return
    if not os.path.exists(av_path):
        logger.error(f"Missing: {av_path}  — run alpha_vantage_collector.py first.")
        return

    validate_prices(yf_path, av_path)
    logger.info("[Validator] Validation complete.")


if __name__ == "__main__":
    load_dotenv()
    run()
