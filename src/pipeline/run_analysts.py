"""
Run Technical and Fundamental Analysts

Summary
-------
This script runs the Technical Analyst and Fundamental Analyst for a given
ticker and saves both outputs as JSON files.

Responsibilities
----------------
- Build a technical snapshot from price parquet data
- Build a fundamental snapshot from quarterly fundamentals parquet data
- Run both analyst agents
- Save the resulting reports to JSON files

Usage
-----
Run for one ticker:
    uv run python -m src.pipeline.run_analysts --ticker AAPL

Run for one ticker and one date:
    uv run python -m src.pipeline.run_analysts --ticker AAPL --date 2026-03-15

Run for multiple tickers:
    uv run python -m src.pipeline.run_analysts --ticker AAPL MSFT NVDA
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.agents.fundamental_analyst import FundamentalAnalyst
from src.agents.technical_analyst import TechnicalAnalyst
from src.features.fundamental_features import build_fundamental_snapshot
from src.features.technical_features import build_technical_snapshot


DEFAULT_PRICE_PATH = "data/sample/price/price_ohlcv.parquet"
DEFAULT_FUNDAMENTALS_PATH = "data/sample/fundamentals/quarterly_fundamentals.parquet"
DEFAULT_OUTPUT_DIR = "outputs/analyst_reports"


def save_json(data: dict, output_path: str) -> None:
    """Save dictionary data to a JSON file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def run_for_ticker(
    ticker: str,
    price_path: str,
    fundamentals_path: str,
    output_dir: str,
    analysis_date: str | None = None,
) -> None:
    """Run both analyst agents for one ticker and save outputs."""
    technical_snapshot = build_technical_snapshot(
        parquet_path=price_path,
        ticker=ticker,
        as_of_date=analysis_date,
    )
    fundamental_snapshot = build_fundamental_snapshot(
        parquet_path=fundamentals_path,
        ticker=ticker,
        as_of_date=analysis_date,
    )

    technical_agent = TechnicalAnalyst()
    fundamental_agent = FundamentalAnalyst()

    technical_report = technical_agent.analyze(technical_snapshot)
    fundamental_report = fundamental_agent.analyze(fundamental_snapshot)

    report_date = analysis_date or technical_report.analysis_date

    technical_output_path = os.path.join(
        output_dir,
        "technical",
        f"{ticker}_{report_date}.json",
    )
    fundamental_output_path = os.path.join(
        output_dir,
        "fundamental",
        f"{ticker}_{report_date}.json",
    )

    save_json(technical_report.model_dump(mode="json"), technical_output_path)
    save_json(fundamental_report.model_dump(mode="json"), fundamental_output_path)

    print(f"\n=== {ticker} ===")
    print(f"Technical report saved to:   {technical_output_path}")
    print(f"Fundamental report saved to: {fundamental_output_path}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Run technical and fundamental analyst agents.")
    parser.add_argument(
        "--ticker",
        nargs="+",
        required=True,
        help="One or more ticker symbols, e.g. --ticker AAPL MSFT NVDA",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Optional analysis date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--price-path",
        type=str,
        default=DEFAULT_PRICE_PATH,
        help="Path to OHLCV parquet file",
    )
    parser.add_argument(
        "--fundamentals-path",
        type=str,
        default=DEFAULT_FUNDAMENTALS_PATH,
        help="Path to quarterly fundamentals parquet file",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where JSON reports will be saved",
    )
    return parser.parse_args()


def main() -> None:
    """Run analyst pipeline for all requested tickers."""
    args = parse_args()

    failed_tickers = []

    for ticker in args.ticker:
        try:
            run_for_ticker(
                ticker=ticker,
                price_path=args.price_path,
                fundamentals_path=args.fundamentals_path,
                output_dir=args.output_dir,
                analysis_date=args.date,
            )
        except Exception as e:
            failed_tickers.append((ticker, str(e)))
            print(f"\n=== {ticker} FAILED ===")
            print(f"Reason: {e}")

    if failed_tickers:
        print("\nSummary of failed tickers:")
        for ticker, reason in failed_tickers:
            print(f"- {ticker}: {reason}")


if __name__ == "__main__":
    main()