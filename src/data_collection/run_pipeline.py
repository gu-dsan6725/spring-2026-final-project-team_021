"""
DebateTrader Data Pipeline — Milestone 2 entry point.

Steps:
  1. Yahoo Finance  — OHLCV + fundamentals       (no API key needed)
  2. Alpha Vantage  — OHLCV for cross-validation  (ALPHA_VANTAGE_API_KEY_1/_2/_3)
  3. Price Validator — merge & flag discrepancies  (requires steps 1 + 2)
  4. Google Trends  — retail investor attention    (no API key needed)

Usage (from project root):
    python src/data_collection/run_pipeline.py

    # Skip individual steps:
    python src/data_collection/run_pipeline.py --skip-alpha-vantage --skip-validation

Environment (.env):
    ALPHA_VANTAGE_API_KEY_1 / _2 / _3   — for step 2
    GROQ_API_KEY                         — for step 4 (search term generation)
"""
from __future__ import annotations

import sys
import os
import logging
import argparse

from dotenv import load_dotenv
load_dotenv()   # Load .env before any other import reads os.environ

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from src.data_collection.config import (
    TICKERS, SAMPLE_START, SAMPLE_END,
    DATA_DIR, PRICE_DIR, FUNDAMENTALS_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step runners
# ---------------------------------------------------------------------------

def step_yfinance(skip: bool) -> None:
    if skip:
        logger.info("[SKIP] Yahoo Finance")
        return
    logger.info("=" * 60)
    logger.info("STEP 1 / 4  —  Yahoo Finance (OHLCV + fundamentals)")
    logger.info("=" * 60)
    from src.data_collection.yahoo_finance_collector import run
    run(tickers=TICKERS, start=SAMPLE_START, end=SAMPLE_END)


def step_alpha_vantage(skip: bool) -> None:
    if skip:
        logger.info("[SKIP] Alpha Vantage")
        return
    has_key = any(
        os.environ.get(f"ALPHA_VANTAGE_API_KEY_{i}", "").strip()
        for i in range(1, 4)
    )
    if not has_key:
        logger.warning(
            "[SKIP] Alpha Vantage — no ALPHA_VANTAGE_API_KEY_N found in .env.\n"
            "       Free keys: https://www.alphavantage.co/support/#api-key"
        )
        return
    logger.info("=" * 60)
    logger.info("STEP 2 / 4  —  Alpha Vantage (price cross-validation)")
    logger.info("=" * 60)
    from src.data_collection.alpha_vantage_collector import run
    run(tickers=TICKERS, start=SAMPLE_START, end=SAMPLE_END)


def step_validation(skip: bool) -> None:
    if skip:
        logger.info("[SKIP] Price validation")
        return
    yf_path = os.path.join(PRICE_DIR, "yfinance_ohlcv.parquet")
    av_path = os.path.join(PRICE_DIR, "alpha_vantage_ohlcv.parquet")
    if not (os.path.exists(yf_path) and os.path.exists(av_path)):
        logger.warning(
            "[SKIP] Price validation — one or both source files missing.\n"
            f"       Expected: {yf_path}\n"
            f"                 {av_path}"
        )
        return
    logger.info("=" * 60)
    logger.info("STEP 3 / 4  —  Price cross-validation (YF vs AV)")
    logger.info("=" * 60)
    from src.data_collection.price_validator import run
    run()


def step_google_trends(skip: bool) -> None:
    if skip:
        logger.info("[SKIP] Google Trends")
        return
    logger.info("=" * 60)
    logger.info("STEP 4 / 4  —  Google Trends (retail attention proxy)")
    logger.info("=" * 60)

    # Pass company names so Groq can generate better search terms
    # (e.g. "BRK.B" + "Berkshire Hathaway Inc." → "Berkshire Hathaway stock")
    import pandas as pd
    company_names: dict[str, str] = {}
    snapshot_path = os.path.join(FUNDAMENTALS_DIR, "yfinance_fundamentals_snapshot.parquet")
    if os.path.exists(snapshot_path):
        snap = pd.read_parquet(snapshot_path)
        company_names = dict(
            zip(snap["ticker"], snap["company_name"].fillna(""))
        )
        logger.info(f"  Loaded {len(company_names)} company names for Groq prompts.")
    else:
        logger.warning(
            "  yfinance_fundamentals_snapshot.parquet not found. "
            "Groq will use ticker symbols only."
        )

    from src.data_collection.google_trends_collector import run
    run(tickers=TICKERS, start=SAMPLE_START, end=SAMPLE_END,
        company_names=company_names)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary() -> None:
    logger.info("=" * 60)
    logger.info("OUTPUT SUMMARY")
    logger.info("=" * 60)
    if not os.path.exists(DATA_DIR):
        logger.warning(f"Output directory not found: {DATA_DIR}")
        return

    total_rows = 0
    for root, dirs, files in os.walk(DATA_DIR):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        level  = root.replace(DATA_DIR, "").count(os.sep)
        indent = "  " * level
        logger.info(f"{indent}{os.path.basename(root)}/")
        sub    = "  " * (level + 1)
        for fname in sorted(files):
            if fname.startswith("."): continue
            fpath   = os.path.join(root, fname)
            size_kb = os.path.getsize(fpath) / 1024
            row_info = ""
            if fname.endswith(".parquet"):
                try:
                    import pandas as pd
                    n = len(pd.read_parquet(fpath))
                    row_info = f"  [{n:,} rows]"
                    total_rows += n
                except Exception:
                    pass
            logger.info(f"{sub}{fname}  ({size_kb:.1f} KB){row_info}")

    logger.info(f"\nTotal parquet rows collected: {total_rows:,}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="DebateTrader data collection pipeline (Milestone 2)"
    )
    parser.add_argument("--skip-yfinance",      action="store_true")
    parser.add_argument("--skip-alpha-vantage", action="store_true")
    parser.add_argument("--skip-validation",    action="store_true")
    parser.add_argument("--skip-google-trends",  action="store_true")
    args = parser.parse_args()

    logger.info("DebateTrader Data Pipeline — Milestone 2")
    logger.info(f"  Tickers : {TICKERS}")
    logger.info(f"  Period  : {SAMPLE_START} → {SAMPLE_END}")
    logger.info(f"  Output  : {DATA_DIR}/")

    step_yfinance(args.skip_yfinance)
    step_alpha_vantage(args.skip_alpha_vantage)
    step_validation(args.skip_validation)
    step_google_trends(args.skip_google_trends)

    print_summary()
    logger.info("Pipeline finished.")


if __name__ == "__main__":
    main()
