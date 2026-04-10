"""
DebateTrader Data Pipeline entry point.

Steps:
  1. Price          — daily OHLCV via Yahoo Finance      (no API key needed)
  2. Fundamentals   — quarterly SEC EDGAR + Yahoo Finance (no API key needed)
  3. Google Trends  — retail investor attention          (no API key needed)
  4. News           — company headlines via Finnhub       (API key hardcoded)
  5. Macro          — 35 FRED indicators                  (API key hardcoded)

Usage (from project root):
    python src/data_collection/run_pipeline.py

    # Custom date range and tickers:
    python src/data_collection/run_pipeline.py \\
        --start-date 2025-07-01 --end-date 2025-12-31 \\
        --tickers AAPL GOOGL AMZN

    # Skip individual steps:
    python src/data_collection/run_pipeline.py --skip-price --skip-fundamentals

Environment (.env):
    GROQ_API_KEY   — for step 3 (search term generation via Groq, optional)
"""
from __future__ import annotations

import sys
import os
import logging
import argparse
import datetime

from dotenv import load_dotenv
load_dotenv()   # Load .env before any other import reads os.environ

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from src.data_collection.config import (
    TICKERS, SAMPLE_START,
    DATA_DIR, FUNDAMENTALS_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _yesterday() -> str:
    return (datetime.date.today() - datetime.timedelta(days=1)).isoformat()


# ---------------------------------------------------------------------------
# Step runners
# ---------------------------------------------------------------------------

def step_price(skip: bool, tickers: list[str], start: str, end: str) -> None:
    if skip:
        logger.info("[SKIP] Price")
        return
    logger.info("=" * 60)
    logger.info("STEP 1 / 5  —  Price (Yahoo Finance OHLCV)")
    logger.info("=" * 60)
    from src.data_collection.price_collector import run
    run(tickers=tickers, start=start, end=end)


def step_fundamentals(skip: bool, tickers: list[str], end: str) -> None:
    if skip:
        logger.info("[SKIP] Fundamentals")
        return
    logger.info("=" * 60)
    logger.info("STEP 2 / 5  —  Fundamentals (SEC EDGAR primary + Yahoo Finance supplementary)")
    logger.info("=" * 60)
    from src.data_collection.fundamental_collector import run
    run(tickers=tickers, end=end)


def step_google_trends(skip: bool, tickers: list[str], start: str, end: str) -> None:
    if skip:
        logger.info("[SKIP] Google Trends")
        return
    logger.info("=" * 60)
    logger.info("STEP 3 / 5  —  Google Trends (retail attention proxy)")
    logger.info("=" * 60)

    company_names: dict[str, str] = {}
    quarterly_path = os.path.join(FUNDAMENTALS_DIR, "quarterly_fundamentals.parquet")
    if os.path.exists(quarterly_path):
        try:
            import yfinance as yf
            from src.data_collection.config import YFINANCE_TICKER_MAP
            for ticker in tickers:
                yf_sym = YFINANCE_TICKER_MAP.get(ticker, ticker)
                name = yf.Ticker(yf_sym).info.get("longName", "")
                if name:
                    company_names[ticker] = name
            logger.info(f"  Loaded {len(company_names)} company names for Groq prompts.")
        except Exception as exc:
            logger.warning(f"  Could not fetch company names: {exc}. Using ticker symbols.")
    else:
        logger.warning(
            "  quarterly_fundamentals.parquet not found. "
            "Run step 2 first, or Groq will use ticker symbols only."
        )

    from src.data_collection.google_trends_collector import run
    run(tickers=tickers, start=start, end=end, company_names=company_names)


def step_news(skip: bool, tickers: list[str], start: str, end: str) -> None:
    if skip:
        logger.info("[SKIP] News")
        return
    logger.info("=" * 60)
    logger.info("STEP 4 / 5  —  News (Finnhub company headlines)")
    logger.info("=" * 60)
    from src.data_collection.finnhub_news_fetch import run
    run(tickers=tickers, start=start, end=end)


def step_macro(skip: bool, start: str, end: str) -> None:
    if skip:
        logger.info("[SKIP] Macro")
        return
    logger.info("=" * 60)
    logger.info("STEP 5 / 5  —  Macro (FRED indicators)")
    logger.info("=" * 60)
    from src.data_collection.fred_macro_fetch import run
    run(start=start, end=end)


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
        description="DebateTrader data collection pipeline"
    )
    parser.add_argument(
        "--start-date", type=str, default=SAMPLE_START,
        help=f"Collection start date YYYY-MM-DD (default: {SAMPLE_START})",
    )
    parser.add_argument(
        "--end-date", type=str, default=None,
        help="Collection end date YYYY-MM-DD (default: yesterday)",
    )
    parser.add_argument(
        "--tickers", nargs="+", default=TICKERS,
        help=f"Ticker symbols to collect (default: {' '.join(TICKERS)})",
    )
    parser.add_argument("--skip-price",         action="store_true", help="Skip price collection")
    parser.add_argument("--skip-fundamentals",  action="store_true", help="Skip fundamentals collection")
    parser.add_argument("--skip-google-trends", action="store_true", help="Skip Google Trends collection")
    parser.add_argument("--skip-news",          action="store_true", help="Skip Finnhub news collection")
    parser.add_argument("--skip-macro",         action="store_true", help="Skip FRED macro collection")
    args = parser.parse_args()

    tickers   = [t.upper() for t in args.tickers]
    start     = args.start_date
    end       = args.end_date or _yesterday()

    logger.info("DebateTrader Data Pipeline")
    logger.info(f"  Tickers : {tickers}")
    logger.info(f"  Period  : {start} → {end}")
    logger.info(f"  Output  : {DATA_DIR}/")

    step_price(args.skip_price, tickers=tickers, start=start, end=end)
    step_fundamentals(args.skip_fundamentals, tickers=tickers, end=end)
    step_google_trends(args.skip_google_trends, tickers=tickers, start=start, end=end)
    step_news(args.skip_news, tickers=tickers, start=start, end=end)
    step_macro(args.skip_macro, start=start, end=end)

    print_summary()
    logger.info("Pipeline finished.")


if __name__ == "__main__":
    main()
