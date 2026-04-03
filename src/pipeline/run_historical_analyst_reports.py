"""
Generate historical analyst reports at fixed frequencies.

Rules implemented:
- technical: one JSON per ticker per week, dated to that week's Sunday
- news_trends: one JSON per ticker per week, dated to that week's Sunday
- fundamental: one JSON per fundamentals row, dated to filed_date
- macro: one JSON per month, dated to month-end
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd

from src.agents.fundamental_analyst import FundamentalAnalyst
from src.agents.macro_analyst import MacroAnalyst
from src.agents.news_trends_analyst import NewsTrendsAnalyst
from src.agents.technical_analyst import TechnicalAnalyst
from src.features.fundamental_features import (
    build_fundamental_snapshot_from_row,
)
from src.features.news_macro_features import build_news_macro_snapshot
from src.features.technical_features import build_technical_snapshot


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRICE_PATH = "data/sample/price/price_ohlcv.csv"
DEFAULT_FUNDAMENTALS_PATH = "data/sample/fundamentals/quarterly_fundamentals.csv"
DEFAULT_NEWS_PATH = "data/sample/news/all_news.csv"
DEFAULT_MACRO_PATH = "data/sample/macro/macro_all_daily_ffill.csv"
DEFAULT_GOOGLE_TRENDS_PATH = "data/sample/sentiment/google_trends_daily.csv"
DEFAULT_OUTPUT_DIR = "outputs/historical_analyst_reports"


def _resolve_path(path_str: str | Path) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _display_path(path_str: str | Path) -> str:
    path = _resolve_path(path_str)
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def save_json(data: dict, output_path: str | Path) -> None:
    """Save dictionary data to a JSON file."""
    resolved_output_path = _resolve_path(output_path)
    os.makedirs(resolved_output_path.parent, exist_ok=True)
    with open(resolved_output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def _read_table(path: str) -> pd.DataFrame:
    file_path = _resolve_path(path)
    if file_path.suffix.lower() == ".csv":
        return pd.read_csv(file_path)
    return pd.read_parquet(file_path)


def _sunday_for_date(value) -> pd.Timestamp:
    ts = pd.Timestamp(value).normalize()
    return ts + pd.Timedelta(days=(6 - ts.weekday()) % 7)


def _available_tickers(price_path: str) -> list[str]:
    df = _read_table(price_path)
    return sorted(df["ticker"].astype(str).str.upper().dropna().unique().tolist())


def _weekly_schedule_for_ticker(price_df: pd.DataFrame, ticker: str) -> list[str]:
    ticker_df = price_df[price_df["ticker"].astype(str).str.upper() == ticker].copy()
    if ticker_df.empty:
        return []
    ticker_df["date"] = pd.to_datetime(ticker_df["date"])
    sundays = sorted({_sunday_for_date(value).date().isoformat() for value in ticker_df["date"]})
    return sundays


def _macro_month_end_schedule(macro_df: pd.DataFrame) -> list[str]:
    macro_dates = pd.to_datetime(macro_df["Date"], errors="coerce").dropna()
    month_ends = sorted({(date + pd.offsets.MonthEnd(0)).date().isoformat() for date in macro_dates})
    return month_ends


def _fundamental_rows(fundamentals_path: str, tickers: list[str]) -> pd.DataFrame:
    df = _read_table(fundamentals_path)
    df["ticker"] = df["ticker"].astype(str).str.upper()
    df["filed_date"] = pd.to_datetime(df["filed_date"], errors="coerce")
    df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
    df = df.dropna(subset=["filed_date"])
    df = df[df["ticker"].isin(tickers)].copy()
    return df.sort_values(["ticker", "filed_date", "period_end"])


def generate_technical_reports(
    tickers: list[str],
    price_path: str,
    output_dir: str,
) -> int:
    """Generate weekly technical reports per ticker."""
    price_df = _read_table(price_path)
    technical_agent = TechnicalAnalyst()
    generated = 0

    for ticker in tickers:
        for sunday in _weekly_schedule_for_ticker(price_df=price_df, ticker=ticker):
            snapshot = build_technical_snapshot(
                parquet_path=str(_resolve_path(price_path)),
                ticker=ticker,
                as_of_date=sunday,
            )
            source_market_date = snapshot["analysis_date"]
            snapshot["analysis_date"] = sunday
            report = technical_agent.analyze(snapshot)
            report.analysis_date = sunday
            report.key_metrics_used["source_market_date"] = source_market_date

            output_path = Path(output_dir) / "technical" / f"{ticker}_{sunday}.json"
            save_json(report.model_dump(mode="json"), output_path)
            generated += 1

    return generated


def generate_news_reports(
    tickers: list[str],
    price_path: str,
    news_path: str,
    macro_path: str,
    google_trends_path: str,
    output_dir: str,
) -> int:
    """Generate weekly news/trends reports per ticker."""
    price_df = _read_table(price_path)
    news_agent = NewsTrendsAnalyst()
    generated = 0

    for ticker in tickers:
        for sunday in _weekly_schedule_for_ticker(price_df=price_df, ticker=ticker):
            snapshot = build_news_macro_snapshot(
                news_csv_path=str(_resolve_path(news_path)),
                macro_csv_path=str(_resolve_path(macro_path)),
                google_trends_csv_path=str(_resolve_path(google_trends_path)),
                ticker=ticker,
                as_of_date=sunday,
            )
            report = news_agent.analyze(snapshot)
            report.analysis_date = sunday

            output_path = Path(output_dir) / "news_trends" / f"{ticker}_{sunday}.json"
            save_json(report.model_dump(mode="json"), output_path)
            generated += 1

    return generated


def generate_fundamental_reports(
    tickers: list[str],
    fundamentals_path: str,
    output_dir: str,
) -> int:
    """Generate one fundamental report per source row."""
    rows = _fundamental_rows(fundamentals_path=fundamentals_path, tickers=tickers)
    fundamental_agent = FundamentalAnalyst()
    generated = 0

    for row in rows.itertuples(index=False):
        row_dict = row._asdict()
        filed_date = pd.Timestamp(row_dict["filed_date"]).date().isoformat()
        period_end = (
            pd.Timestamp(row_dict["period_end"]).date().isoformat()
            if row_dict.get("period_end") is not None and not pd.isna(row_dict.get("period_end"))
            else "unknown_period"
        )
        snapshot = build_fundamental_snapshot_from_row(row_dict)
        report = fundamental_agent.analyze(snapshot)

        output_name = f"{report.ticker}_{filed_date}_{period_end}.json"
        output_path = Path(output_dir) / "fundamental" / output_name
        save_json(report.model_dump(mode="json"), output_path)
        generated += 1

    return generated


def generate_macro_reports(
    news_path: str,
    macro_path: str,
    output_dir: str,
) -> int:
    """Generate one macro report per month."""
    macro_df = _read_table(macro_path)
    macro_agent = MacroAnalyst()
    generated = 0

    for month_end in _macro_month_end_schedule(macro_df):
        snapshot = build_news_macro_snapshot(
            news_csv_path=str(_resolve_path(news_path)),
            macro_csv_path=str(_resolve_path(macro_path)),
            ticker="MACRO",
            as_of_date=month_end,
        )
        snapshot["ticker"] = "MACRO"
        snapshot["analysis_date"] = month_end
        report = macro_agent.analyze(snapshot)
        report.analysis_date = month_end
        report.ticker = "MACRO"

        output_path = Path(output_dir) / "macro" / f"MACRO_{month_end}.json"
        save_json(report.model_dump(mode="json"), output_path)
        generated += 1

    return generated


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Generate historical analyst reports.")
    parser.add_argument(
        "--ticker",
        nargs="+",
        default=None,
        help="Optional list of tickers. Defaults to all tickers found in price data.",
    )
    parser.add_argument(
        "--price-path",
        type=str,
        default=DEFAULT_PRICE_PATH,
        help="Path to price data CSV/parquet",
    )
    parser.add_argument(
        "--fundamentals-path",
        type=str,
        default=DEFAULT_FUNDAMENTALS_PATH,
        help="Path to fundamentals data CSV/parquet",
    )
    parser.add_argument(
        "--news-path",
        type=str,
        default=DEFAULT_NEWS_PATH,
        help="Path to news CSV",
    )
    parser.add_argument(
        "--macro-path",
        type=str,
        default=DEFAULT_MACRO_PATH,
        help="Path to macro CSV/parquet",
    )
    parser.add_argument(
        "--google-trends-path",
        type=str,
        default=DEFAULT_GOOGLE_TRENDS_PATH,
        help="Path to Google Trends CSV/parquet",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where historical reports will be saved",
    )
    return parser.parse_args()


def main() -> None:
    """Generate historical analyst reports for all requested frequencies."""
    args = parse_args()
    tickers = args.ticker or _available_tickers(args.price_path)

    technical_count = generate_technical_reports(
        tickers=tickers,
        price_path=args.price_path,
        output_dir=args.output_dir,
    )
    news_count = generate_news_reports(
        tickers=tickers,
        price_path=args.price_path,
        news_path=args.news_path,
        macro_path=args.macro_path,
        google_trends_path=args.google_trends_path,
        output_dir=args.output_dir,
    )
    fundamental_count = generate_fundamental_reports(
        tickers=tickers,
        fundamentals_path=args.fundamentals_path,
        output_dir=args.output_dir,
    )
    macro_count = generate_macro_reports(
        news_path=args.news_path,
        macro_path=args.macro_path,
        output_dir=args.output_dir,
    )

    print("Historical analyst reports generated:")
    print(f"- technical:   {technical_count}")
    print(f"- news_trends: {news_count}")
    print(f"- fundamental: {fundamental_count}")
    print(f"- macro:       {macro_count}")
    print(f"- output_dir:  {_display_path(args.output_dir)}")


if __name__ == "__main__":
    main()
