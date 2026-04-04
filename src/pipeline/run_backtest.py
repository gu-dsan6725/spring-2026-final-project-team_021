"""
Backtest execution layer for DebateTrader.

Reads weekly risk-management portfolios and simulates paper trading:
  - Entry : open price of the first trading day AFTER each portfolio Sunday
  - Exit  : open price of the first trading day AFTER the NEXT portfolio Sunday
             (last portfolio exits at the close of the last available price date)
  - No transaction costs or slippage (paper trading assumption)

Outputs
-------
outputs/backtest/results.json   Full period-by-period breakdown + summary metrics
outputs/backtest/summary.txt    Human-readable performance summary

Metrics
-------
  Total return, annualised return, Sharpe ratio (annualised, weekly),
  maximum drawdown, win rate (% of weeks with positive return)

Benchmark
---------
  Equal-weight buy-and-hold of all 6 tickers over the same date range,
  rebalanced each Monday alongside the strategy (so benchmark always holds
  1/6 of each stock regardless of Judge signal).

Usage
-----
  python -m src.pipeline.run_backtest
  python -m src.pipeline.run_backtest --initial-capital 500000
  python -m src.pipeline.run_backtest --risk-dir outputs/risk_management \
      --price-file data/sample/price/price_ohlcv.parquet
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_RISK_DIR   = "outputs/risk_management"
DEFAULT_PRICE_FILE = "data/sample/price/price_ohlcv.parquet"
DEFAULT_OUTPUT_DIR = "outputs/backtest"
DEFAULT_CAPITAL    = 1_000_000.0
ANNUAL_WEEKS       = 52


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else PROJECT_ROOT / p


def load_risk_portfolios(risk_dir: str) -> list[dict]:
    """Return list of risk reports sorted by week_end_date."""
    base = _resolve(risk_dir)
    reports = []
    for f in sorted(base.glob("*.json")):
        with open(f, encoding="utf-8") as fh:
            reports.append(json.load(fh))
    return sorted(reports, key=lambda r: r["week_end_date"])


def load_prices(price_file: str) -> pd.DataFrame:
    """Return a DataFrame indexed by (date, ticker) with open/close columns."""
    df = pd.read_parquet(_resolve(price_file))
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df = df.set_index(["date", "ticker"]).sort_index()
    return df


# ---------------------------------------------------------------------------
# Trading day helpers
# ---------------------------------------------------------------------------

def next_trading_day(after_date: str, price_df: pd.DataFrame) -> pd.Timestamp:
    """Return the first date in price_df that is strictly after after_date."""
    cutoff = pd.Timestamp(after_date)
    all_dates = price_df.index.get_level_values("date").unique().sort_values()
    future = all_dates[all_dates > cutoff]
    if future.empty:
        raise ValueError(f"No trading day found after {after_date}")
    return future[0]


def next_trading_day_after_n_days(
    after_date: str, n_days: int, price_df: pd.DataFrame
) -> pd.Timestamp:
    """Return the first trading day after (after_date + n_days)."""
    shifted = pd.Timestamp(after_date) + pd.Timedelta(days=n_days)
    all_dates = price_df.index.get_level_values("date").unique().sort_values()
    future = all_dates[all_dates > shifted]
    if future.empty:
        raise ValueError(f"No trading day found after {shifted.date()}")
    return future[0]


def get_price(
    price_df: pd.DataFrame, date: pd.Timestamp, ticker: str, col: str
) -> float:
    try:
        return float(price_df.loc[(date, ticker), col])
    except KeyError:
        raise KeyError(f"No price data for {ticker} on {date.date()} (col={col})")


# ---------------------------------------------------------------------------
# Per-period simulation
# ---------------------------------------------------------------------------

def simulate_period(
    portfolio: dict[str, float],   # ticker -> weight (0-100 scale)
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
    price_df: pd.DataFrame,
    capital_start: float,
) -> dict:
    """
    Simulate one holding period.

    Returns a dict with per-ticker detail and aggregate portfolio return.
    """
    holdings_detail = {}
    portfolio_return = 0.0

    for ticker, weight_pct in portfolio.items():
        if weight_pct <= 0:
            continue
        weight = weight_pct / 100.0

        # Use open on entry, open on exit (last period uses close of last day)
        entry_price = get_price(price_df, entry_date, ticker, "open")
        try:
            exit_price = get_price(price_df, exit_date, ticker, "open")
            exit_col = "open"
        except KeyError:
            # exit_date is last day → use close
            exit_price = get_price(price_df, exit_date, ticker, "close")
            exit_col = "close"

        ticker_return = (exit_price - entry_price) / entry_price
        portfolio_return += weight * ticker_return

        holdings_detail[ticker] = {
            "weight_pct": round(weight_pct, 4),
            "entry_price": round(entry_price, 4),
            "exit_price": round(exit_price, 4),
            "exit_price_col": exit_col,
            "return_pct": round(ticker_return * 100, 4),
            "contribution_pct": round(weight * ticker_return * 100, 4),
        }

    capital_end = capital_start * (1 + portfolio_return)

    return {
        "entry_date": entry_date.strftime("%Y-%m-%d"),
        "exit_date": exit_date.strftime("%Y-%m-%d"),
        "holdings": holdings_detail,
        "portfolio_return_pct": round(portfolio_return * 100, 4),
        "capital_start": round(capital_start, 2),
        "capital_end": round(capital_end, 2),
    }


# ---------------------------------------------------------------------------
# Benchmark: equal-weight all 6 tickers, rebalanced each period
# ---------------------------------------------------------------------------

def simulate_benchmark(
    tickers: list[str],
    periods: list[dict],   # same entry/exit dates as strategy
    price_df: pd.DataFrame,
    capital_start: float,
) -> dict:
    equal_weight = 100.0 / len(tickers)
    portfolio = {t: equal_weight for t in tickers}

    bm_periods = []
    capital = capital_start
    for p in periods:
        entry = pd.Timestamp(p["entry_date"])
        exit_ = pd.Timestamp(p["exit_date"])
        result = simulate_period(portfolio, entry, exit_, price_df, capital)
        bm_periods.append({
            "entry_date": p["entry_date"],
            "exit_date": p["exit_date"],
            "portfolio_return_pct": result["portfolio_return_pct"],
            "capital_end": result["capital_end"],
        })
        capital = result["capital_end"]

    return bm_periods


# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------

def compute_metrics(
    weekly_returns: list[float],  # decimal, e.g. 0.012 = 1.2%
    capital_curve: list[float],   # portfolio value at end of each period
    initial_capital: float,
) -> dict:
    n = len(weekly_returns)
    if n == 0:
        return {}

    total_return = (capital_curve[-1] - initial_capital) / initial_capital
    # Annualise assuming each period is one week
    annualised_return = (1 + total_return) ** (ANNUAL_WEEKS / n) - 1

    mean_r = sum(weekly_returns) / n
    if n > 1:
        variance = sum((r - mean_r) ** 2 for r in weekly_returns) / (n - 1)
        std_r = math.sqrt(variance)
    else:
        std_r = 0.0

    sharpe = (mean_r / std_r * math.sqrt(ANNUAL_WEEKS)) if std_r > 0 else 0.0

    # Max drawdown over capital curve (include initial capital as starting point)
    curve = [initial_capital] + capital_curve
    peak = curve[0]
    max_dd = 0.0
    for v in curve:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd

    win_rate = sum(1 for r in weekly_returns if r > 0) / n

    return {
        "num_periods": n,
        "total_return_pct": round(total_return * 100, 4),
        "annualised_return_pct": round(annualised_return * 100, 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown_pct": round(max_dd * 100, 4),
        "win_rate_pct": round(win_rate * 100, 2),
        "avg_weekly_return_pct": round(mean_r * 100, 4),
        "weekly_return_std_pct": round(std_r * 100, 4),
    }


# ---------------------------------------------------------------------------
# Main backtest runner
# ---------------------------------------------------------------------------

def run_backtest(
    risk_dir: str,
    price_file: str,
    output_dir: str,
    initial_capital: float,
) -> None:
    reports = load_risk_portfolios(risk_dir)
    if not reports:
        raise FileNotFoundError(f"No risk management JSON files found in {risk_dir}")

    price_df = load_prices(price_file)
    all_tickers = sorted(price_df.index.get_level_values("ticker").unique().tolist())

    # Build (entry_date, exit_date) pairs
    # entry = next trading day after week_end_date (Sunday)
    # exit  = entry of the NEXT period; for the last period, exit = next
    #         trading day after (week_end_date + 7 days), i.e. always hold ~1 week
    entry_dates = [
        next_trading_day(r["week_end_date"], price_df) for r in reports
    ]
    last_exit = next_trading_day_after_n_days(
        reports[-1]["week_end_date"], n_days=7, price_df=price_df
    )
    exit_dates = entry_dates[1:] + [last_exit]

    # Strategy simulation
    strategy_periods = []
    capital = initial_capital
    weekly_returns = []
    capital_curve = []

    for report, entry, exit_ in zip(reports, entry_dates, exit_dates):
        allocations = report["adjusted_allocations"]
        period_result = simulate_period(
            portfolio=allocations,
            entry_date=entry,
            exit_date=exit_,
            price_df=price_df,
            capital_start=capital,
        )
        period_result["week_end_date"] = report["week_end_date"]
        period_result["defensive_mode"] = report.get("defensive_mode", False)
        period_result["rules_triggered"] = report.get("rules_triggered", [])

        strategy_periods.append(period_result)
        r = period_result["portfolio_return_pct"] / 100
        weekly_returns.append(r)
        capital = period_result["capital_end"]
        capital_curve.append(capital)

        print(
            f"  {report['week_end_date']}  "
            f"entry={entry.date()}  exit={exit_.date()}  "
            f"return={period_result['portfolio_return_pct']:+.2f}%  "
            f"capital=${capital:,.0f}"
        )

    strategy_metrics = compute_metrics(weekly_returns, capital_curve, initial_capital)

    # Benchmark simulation (equal-weight all tickers, same periods)
    bm_periods = simulate_benchmark(
        tickers=all_tickers,
        periods=strategy_periods,
        price_df=price_df,
        capital_start=initial_capital,
    )
    bm_returns = [p["portfolio_return_pct"] / 100 for p in bm_periods]
    bm_curve = [p["capital_end"] for p in bm_periods]
    bm_metrics = compute_metrics(bm_returns, bm_curve, initial_capital)

    # Assemble output
    results = {
        "initial_capital": initial_capital,
        "price_file": price_file,
        "tickers": all_tickers,
        "strategy": {
            "periods": strategy_periods,
            "metrics": strategy_metrics,
        },
        "benchmark_equal_weight": {
            "description": f"Equal-weight buy-and-hold of all {len(all_tickers)} tickers, rebalanced each period",
            "periods": bm_periods,
            "metrics": bm_metrics,
        },
    }

    out_dir = _resolve(output_dir)
    os.makedirs(out_dir, exist_ok=True)
    results_path = out_dir / "results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    # Human-readable summary
    summary_lines = [
        "=" * 60,
        "DebateTrader Backtest Summary",
        "=" * 60,
        f"Initial capital : ${initial_capital:,.0f}",
        f"Periods         : {strategy_metrics['num_periods']} weeks",
        f"Date range      : {strategy_periods[0]['entry_date']} -> {strategy_periods[-1]['exit_date']}",
        "",
        f"{'Metric':<30} {'Strategy':>12} {'Benchmark':>12}",
        "-" * 56,
        f"{'Total return':<30} {strategy_metrics['total_return_pct']:>+11.2f}% {bm_metrics['total_return_pct']:>+11.2f}%",
        f"{'Annualised return':<30} {strategy_metrics['annualised_return_pct']:>+11.2f}% {bm_metrics['annualised_return_pct']:>+11.2f}%",
        f"{'Sharpe ratio (ann.)':<30} {strategy_metrics['sharpe_ratio']:>12.4f} {bm_metrics['sharpe_ratio']:>12.4f}",
        f"{'Max drawdown':<30} {strategy_metrics['max_drawdown_pct']:>+11.2f}% {bm_metrics['max_drawdown_pct']:>+11.2f}%",
        f"{'Win rate':<30} {strategy_metrics['win_rate_pct']:>11.1f}% {bm_metrics['win_rate_pct']:>11.1f}%",
        f"{'Avg weekly return':<30} {strategy_metrics['avg_weekly_return_pct']:>+11.4f}% {bm_metrics['avg_weekly_return_pct']:>+11.4f}%",
        "",
        "Period detail",
        "-" * 56,
    ]
    for p in strategy_periods:
        def_flag = " [DEFENSIVE]" if p.get("defensive_mode") else ""
        summary_lines.append(
            f"  {p['week_end_date']}  "
            f"{p['entry_date']} -> {p['exit_date']}  "
            f"{p['portfolio_return_pct']:>+7.2f}%  "
            f"${p['capital_end']:>12,.0f}{def_flag}"
        )
    summary_lines += ["", f"Full results: {results_path}"]

    summary_text = "\n".join(summary_lines)
    summary_path = out_dir / "summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_text)

    print()
    print(summary_text)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DebateTrader backtest.")
    parser.add_argument("--risk-dir",  type=str, default=DEFAULT_RISK_DIR)
    parser.add_argument("--price-file", type=str, default=DEFAULT_PRICE_FILE)
    parser.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--initial-capital", type=float, default=DEFAULT_CAPITAL)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(f"\n=== DebateTrader Backtest ===")
    run_backtest(
        risk_dir=args.risk_dir,
        price_file=args.price_file,
        output_dir=args.output_dir,
        initial_capital=args.initial_capital,
    )


if __name__ == "__main__":
    main()
