"""
Temporary analyst runner for development and testing.

Summary
-------
This script mirrors the structure of the main analyst runner without
modifying team-owned integration code. It is intended as a temporary
runner for the remaining analyst agents under development.

Design notes
------------
- Keep the orchestration shape as close as possible to the shared runner.
- This should make later integration into the main runner a small wiring task.
"""

from __future__ import annotations

import argparse
import json
import os

from src.agents.macro_analyst import MacroAnalyst
from src.agents.news_trends_analyst import NewsTrendsAnalyst
from src.features.fundamental_features import build_fundamental_snapshot
from src.features.news_macro_features import build_news_macro_snapshot


DEFAULT_TICKERS = ["AAPL"]
DEFAULT_PRICE_PATH = "data/sample/price/yfinance_ohlcv.parquet"
DEFAULT_FUNDAMENTALS_PATH = "data/sample/fundamentals/yfinance_fundamentals_snapshot.parquet"
DEFAULT_NEWS_PATH = "data/sample/news/all_news.csv"
DEFAULT_MACRO_PATH = "data/sample/macro/macro_data.csv"
DEFAULT_OUTPUT_DIR = "outputs/analyst_reports2"


def save_json(data: dict, output_path: str) -> None:
    """Save dictionary data to a JSON file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def _save_report(output_dir: str, agent_dir: str, report) -> str:
    output_path = os.path.join(
        output_dir,
        agent_dir,
        f"{report.ticker}_{report.analysis_date}.json",
    )
    save_json(report.model_dump(mode="json"), output_path)
    return output_path


def run_for_ticker(
    ticker: str,
    price_path: str,
    fundamentals_path: str,
    news_path: str,
    macro_path: str,
    output_dir: str,
    analysis_date: str | None = None,
) -> None:
    """Run available development-stage analyst agents for one ticker and save outputs."""
    print(f"\n=== {ticker} ===")

    # Keep the same overall orchestration pattern as the shared runner.
    # `price_path` is accepted for interface compatibility even though the
    # current temporary runner does not need it yet.
    _ = price_path

    company_name = None

    try:
        fundamental_snapshot = build_fundamental_snapshot(
            parquet_path=fundamentals_path,
            ticker=ticker,
            as_of_date=analysis_date,
        )
        company_name = fundamental_snapshot["company_info"].get("company_name")
    except Exception as exc:
        print(f"Company metadata fallback only: {exc}")

    news_macro_snapshot = build_news_macro_snapshot(
        news_csv_path=news_path,
        macro_csv_path=macro_path,
        ticker=ticker,
        as_of_date=analysis_date,
        company_name=company_name,
    )
    news_trends_report = NewsTrendsAnalyst().analyze(news_macro_snapshot)
    macro_report = MacroAnalyst().analyze(news_macro_snapshot)
    report_date = analysis_date or news_trends_report.analysis_date

    news_trends_output = os.path.join(
        output_dir,
        "news_trends",
        f"{ticker}_{report_date}.json",
    )
    macro_output = os.path.join(
        output_dir,
        "macro",
        f"{ticker}_{report_date}.json",
    )
    save_json(news_trends_report.model_dump(mode="json"), news_trends_output)
    save_json(macro_report.model_dump(mode="json"), macro_output)
    print(f"News/trends report saved to: {news_trends_output}")
    print(f"Macro report saved to:       {macro_output}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Temporary analyst runner for development/testing."
    )
    parser.add_argument(
        "--ticker",
        nargs="+",
        default=DEFAULT_TICKERS,
        help="One or more ticker symbols. Defaults to AAPL for development.",
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
        help="Path to fundamentals snapshot parquet file",
    )
    parser.add_argument(
        "--news-path",
        type=str,
        default=DEFAULT_NEWS_PATH,
        help="Path to news CSV file",
    )
    parser.add_argument(
        "--macro-path",
        type=str,
        default=DEFAULT_MACRO_PATH,
        help="Path to macro CSV file",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where JSON reports will be saved",
    )
    return parser.parse_args()


def main() -> None:
    """Run the temporary analyst pipeline."""
    args = parse_args()

    failed_tickers = []

    for ticker in args.ticker:
        try:
            run_for_ticker(
                ticker=ticker,
                price_path=args.price_path,
                fundamentals_path=args.fundamentals_path,
                news_path=args.news_path,
                macro_path=args.macro_path,
                output_dir=args.output_dir,
                analysis_date=args.date,
            )
        except Exception as exc:
            failed_tickers.append((ticker, str(exc)))
            print(f"\n=== {ticker} FAILED ===")
            print(f"Reason: {exc}")

    if failed_tickers:
        print("\nSummary of failed tickers:")
        for ticker, reason in failed_tickers:
            print(f"- {ticker}: {reason}")


if __name__ == "__main__":
    main()
