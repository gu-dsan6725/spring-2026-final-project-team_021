"""
Backtest execution layer for DebateTrader.

Reads weekly risk-management portfolios and simulates paper trading:
  - Entry : open price of the first trading day AFTER each portfolio Sunday
  - Exit  : open price of the first trading day AFTER the NEXT portfolio Sunday
             (last portfolio: exit = next trading day after week_end_date + 7 days)
  - No transaction costs or slippage (paper trading assumption)

Benchmarks
----------
  1. Equal-weight  : hold all 6 tickers at 1/6 each, rebalanced each period
  2. SPY B&H       : buy-and-hold S&P 500 ETF
  3. 60/40         : 60% SPY + 40% AGG, rebalanced each period

Outputs
-------
  outputs/backtest/results.json   Full breakdown + metrics for all 4 series
  outputs/backtest/summary.txt    Human-readable performance table
  outputs/backtest/chart.html     Interactive Plotly chart (4 lines)

Usage
-----
  python -m src.pipeline.run_backtest
  python -m src.pipeline.run_backtest --initial-capital 500000
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

import pandas as pd
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_RISK_DIR   = "outputs/risk_management"
DEFAULT_PRICE_FILE = "data/sample/price/price_ohlcv.parquet"
DEFAULT_OUTPUT_DIR = "outputs/backtest"
DEFAULT_CAPITAL    = 1_000_000.0
ANNUAL_WEEKS       = 52


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else PROJECT_ROOT / p


def load_risk_portfolios(risk_dir: str) -> list[dict]:
    base = _resolve(risk_dir)
    reports = []
    for f in sorted(base.glob("*.json")):
        with open(f, encoding="utf-8") as fh:
            reports.append(json.load(fh))
    return sorted(reports, key=lambda r: r["week_end_date"])


def load_prices(price_file: str) -> pd.DataFrame:
    df = pd.read_parquet(_resolve(price_file))
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df.set_index(["date", "ticker"]).sort_index()


def fetch_etf_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Fetch daily OHLCV for ETFs via yfinance, return same structure as price_df."""
    records = []
    end_excl = (pd.Timestamp(end) + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    for sym in tickers:
        raw = yf.Ticker(sym).history(start=start, end=end_excl, auto_adjust=False)
        for dt, row in raw.iterrows():
            records.append({
                "date": pd.Timestamp(dt).tz_localize(None).normalize(),
                "ticker": sym,
                "open":  float(row["Open"]),
                "close": float(row["Close"]),
            })
    df = pd.DataFrame(records).set_index(["date", "ticker"]).sort_index()
    return df


def next_trading_day(after_date: str, price_df: pd.DataFrame) -> pd.Timestamp:
    cutoff = pd.Timestamp(after_date)
    dates = price_df.index.get_level_values("date").unique().sort_values()
    future = dates[dates > cutoff]
    if future.empty:
        raise ValueError(f"No trading day after {after_date}")
    return future[0]


def next_trading_day_after_n_days(
    after_date: str, n_days: int, price_df: pd.DataFrame
) -> pd.Timestamp:
    shifted = pd.Timestamp(after_date) + pd.Timedelta(days=n_days)
    dates = price_df.index.get_level_values("date").unique().sort_values()
    future = dates[dates > shifted]
    if future.empty:
        raise ValueError(f"No trading day after {shifted.date()}")
    return future[0]


def get_price(
    price_df: pd.DataFrame, date: pd.Timestamp, ticker: str, col: str
) -> float:
    try:
        return float(price_df.loc[(date, ticker), col])
    except KeyError:
        raise KeyError(f"No price for {ticker} on {date.date()} (col={col})")


# ---------------------------------------------------------------------------
# Period simulation
# ---------------------------------------------------------------------------

def simulate_period(
    portfolio: dict[str, float],
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
    price_df: pd.DataFrame,
    capital_start: float,
) -> dict:
    holdings_detail = {}
    portfolio_return = 0.0

    for ticker, weight_pct in portfolio.items():
        if weight_pct <= 0:
            continue
        weight = weight_pct / 100.0
        entry_price = get_price(price_df, entry_date, ticker, "open")
        try:
            exit_price = get_price(price_df, exit_date, ticker, "open")
            exit_col = "open"
        except KeyError:
            exit_price = get_price(price_df, exit_date, ticker, "close")
            exit_col = "close"

        ticker_return = (exit_price - entry_price) / entry_price
        portfolio_return += weight * ticker_return

        holdings_detail[ticker] = {
            "weight_pct":       round(weight_pct, 2),
            "entry_price":      round(entry_price, 4),
            "exit_price":       round(exit_price, 4),
            "exit_price_col":   exit_col,
            "return_pct":       round(ticker_return * 100, 4),
            "contribution_pct": round(weight * ticker_return * 100, 4),
        }

    return {
        "entry_date":           entry_date.strftime("%Y-%m-%d"),
        "exit_date":            exit_date.strftime("%Y-%m-%d"),
        "holdings":             holdings_detail,
        "portfolio_return_pct": round(portfolio_return * 100, 4),
        "capital_start":        round(capital_start, 2),
        "capital_end":          round(capital_start * (1 + portfolio_return), 2),
    }


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

def simulate_equal_weight(
    tickers: list[str], periods: list[dict],
    price_df: pd.DataFrame, capital: float,
) -> list[dict]:
    w = 100.0 / len(tickers)
    portfolio = {t: w for t in tickers}
    results = []
    for p in periods:
        res = simulate_period(
            portfolio, pd.Timestamp(p["entry_date"]),
            pd.Timestamp(p["exit_date"]), price_df, capital,
        )
        results.append(res)
        capital = res["capital_end"]
    return results


def simulate_spy(
    periods: list[dict], etf_df: pd.DataFrame, capital: float,
) -> list[dict]:
    portfolio = {"SPY": 100.0}
    results = []
    for p in periods:
        res = simulate_period(
            portfolio, pd.Timestamp(p["entry_date"]),
            pd.Timestamp(p["exit_date"]), etf_df, capital,
        )
        results.append(res)
        capital = res["capital_end"]
    return results


def simulate_60_40(
    periods: list[dict], etf_df: pd.DataFrame, capital: float,
) -> list[dict]:
    portfolio = {"SPY": 60.0, "AGG": 40.0}
    results = []
    for p in periods:
        res = simulate_period(
            portfolio, pd.Timestamp(p["entry_date"]),
            pd.Timestamp(p["exit_date"]), etf_df, capital,
        )
        results.append(res)
        capital = res["capital_end"]
    return results


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(
    weekly_returns: list[float],
    capital_curve: list[float],
    initial_capital: float,
) -> dict:
    n = len(weekly_returns)
    if n == 0:
        return {}
    total_return = (capital_curve[-1] - initial_capital) / initial_capital
    annualised   = (1 + total_return) ** (ANNUAL_WEEKS / n) - 1
    mean_r = sum(weekly_returns) / n
    std_r  = math.sqrt(
        sum((r - mean_r) ** 2 for r in weekly_returns) / (n - 1)
    ) if n > 1 else 0.0
    sharpe = mean_r / std_r * math.sqrt(ANNUAL_WEEKS) if std_r > 0 else 0.0
    curve  = [initial_capital] + capital_curve
    peak   = curve[0]
    max_dd = 0.0
    for v in curve:
        peak  = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak)
    win_rate = sum(1 for r in weekly_returns if r > 0) / n
    return {
        "num_periods":            n,
        "total_return_pct":       round(total_return * 100, 4),
        "annualised_return_pct":  round(annualised * 100, 4),
        "sharpe_ratio":           round(sharpe, 4),
        "max_drawdown_pct":       round(max_dd * 100, 4),
        "win_rate_pct":           round(win_rate * 100, 2),
        "avg_weekly_return_pct":  round(mean_r * 100, 4),
        "weekly_return_std_pct":  round(std_r * 100, 4),
    }


# ---------------------------------------------------------------------------
# Interactive chart
# ---------------------------------------------------------------------------

def build_chart(
    dates: list[str],
    strategy_curve: list[float],
    eq_curve: list[float],
    spy_curve: list[float],
    mix_curve: list[float],
    strategy_periods: list[dict],
    initial_capital: float,
    output_path: Path,
) -> None:
    import plotly.graph_objects as go

    base = initial_capital

    def normalise(curve: list[float]) -> list[float]:
        return [100.0] + [v / base * 100 for v in curve]

    strat_vals = normalise(strategy_curve)
    eq_vals    = normalise(eq_curve)
    spy_vals   = normalise(spy_curve)
    mix_vals   = normalise(mix_curve)

    # Hover text for strategy: one entry per period transition point
    # index 0 = start (no period yet), index i+1 = after period i
    hover_texts = ["<b>Start</b><br>Value: 100.00"]
    for i, p in enumerate(strategy_periods):
        lines = [
            f"<b>Week ending {p['week_end_date']}</b>",
            f"Entry: {p['entry_date']}  Exit: {p['exit_date']}",
            f"<b>Period return: {p['portfolio_return_pct']:+.2f}%</b>",
            f"Portfolio value: {strat_vals[i+1]:.2f}",
            "",
            "<b>Holdings:</b>",
        ]
        for ticker, h in sorted(p["holdings"].items()):
            lines.append(
                f"  {ticker}: {h['weight_pct']:.1f}%  "
                f"({h['entry_price']:.2f} -> {h['exit_price']:.2f}  "
                f"{h['return_pct']:+.2f}%  contrib {h['contribution_pct']:+.2f}%)"
            )
        if p.get("rules_triggered"):
            lines += ["", "<b>Risk rules triggered:</b>"]
            for r in p["rules_triggered"]:
                lines.append(f"  {r}")
        if p.get("defensive_mode"):
            lines.append("<b>[DEFENSIVE MODE]</b>")
        hover_texts.append("<br>".join(lines))

    fig = go.Figure()

    # --- Strategy (DebateTrader) ---
    fig.add_trace(go.Scatter(
        x=dates,
        y=strat_vals,
        mode="lines+markers",
        name="DebateTrader",
        line=dict(color="#2563EB", width=3),
        marker=dict(size=8, color="#2563EB"),
        hovertext=hover_texts,
        hoverinfo="text",
    ))

    # --- Equal-weight ---
    fig.add_trace(go.Scatter(
        x=dates,
        y=eq_vals,
        mode="lines",
        name="Equal-Weight (6 stocks)",
        line=dict(color="#16A34A", width=2, dash="dot"),
        hovertemplate="<b>Equal-Weight</b><br>Value: %{y:.2f}<extra></extra>",
    ))

    # --- SPY ---
    fig.add_trace(go.Scatter(
        x=dates,
        y=spy_vals,
        mode="lines",
        name="SPY (S&P 500)",
        line=dict(color="#DC2626", width=2, dash="dash"),
        hovertemplate="<b>SPY B&H</b><br>Value: %{y:.2f}<extra></extra>",
    ))

    # --- 60/40 ---
    fig.add_trace(go.Scatter(
        x=dates,
        y=mix_vals,
        mode="lines",
        name="60/40 (SPY + AGG)",
        line=dict(color="#9333EA", width=2, dash="longdash"),
        hovertemplate="<b>60/40</b><br>Value: %{y:.2f}<extra></extra>",
    ))

    fig.update_layout(
        title=dict(
            text="DebateTrader vs Benchmarks  (Normalised to 100)",
            font=dict(size=18),
        ),
        xaxis=dict(title="Date", showgrid=True, gridcolor="#E5E7EB"),
        yaxis=dict(title="Portfolio Value (start = 100)", showgrid=True, gridcolor="#E5E7EB"),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right",  x=1,
        ),
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial, sans-serif", size=13),
        height=520,
        margin=dict(l=60, r=30, t=80, b=60),
    )

    fig.write_html(str(output_path), include_plotlyjs="cdn")
    print(f"  Chart saved: {output_path.relative_to(PROJECT_ROOT)}")


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def write_summary(
    strategy_metrics: dict,
    eq_metrics: dict,
    spy_metrics: dict,
    mix_metrics: dict,
    strategy_periods: list[dict],
    initial_capital: float,
    output_path: Path,
) -> str:
    col = 12
    lines = [
        "=" * 72,
        "DebateTrader Backtest Summary",
        "=" * 72,
        f"Initial capital : ${initial_capital:,.0f}",
        f"Periods         : {strategy_metrics['num_periods']} weeks",
        f"Date range      : {strategy_periods[0]['entry_date']} -> {strategy_periods[-1]['exit_date']}",
        "",
        f"{'Metric':<30} {'Strategy':>{col}} {'EqWeight':>{col}} {'SPY B&H':>{col}} {'60/40':>{col}}",
        "-" * 72,
    ]

    def row(label, key, fmt="+.2f", suffix="%"):
        vals = [strategy_metrics, eq_metrics, spy_metrics, mix_metrics]
        cells = [(f"{m[key]:{fmt}}{suffix}" if suffix else f"{m[key]:{fmt}}") for m in vals]
        return f"{label:<30} " + "  ".join(f"{c:>{col}}" for c in cells)

    lines += [
        row("Total return",          "total_return_pct"),
        row("Annualised return",      "annualised_return_pct"),
        row("Sharpe ratio (ann.)",    "sharpe_ratio",         fmt=".4f", suffix=""),
        row("Max drawdown",           "max_drawdown_pct"),
        row("Win rate",               "win_rate_pct",         fmt=".1f"),
        row("Avg weekly return",      "avg_weekly_return_pct", fmt="+.4f"),
        "",
        "Period detail (Strategy)",
        "-" * 72,
    ]

    for p in strategy_periods:
        flag = " [DEFENSIVE]" if p.get("defensive_mode") else ""
        lines.append(
            f"  {p['week_end_date']}  "
            f"{p['entry_date']} -> {p['exit_date']}  "
            f"{p['portfolio_return_pct']:>+7.2f}%  "
            f"${p['capital_end']:>12,.0f}{flag}"
        )

    text = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    return text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_backtest(
    risk_dir: str,
    price_file: str,
    output_dir: str,
    initial_capital: float,
) -> None:
    reports   = load_risk_portfolios(risk_dir)
    price_df  = load_prices(price_file)
    all_tickers = sorted(
        price_df.index.get_level_values("ticker").unique().tolist()
    )

    # Determine period boundaries
    entry_dates = [next_trading_day(r["week_end_date"], price_df) for r in reports]
    last_exit   = next_trading_day_after_n_days(
        reports[-1]["week_end_date"], n_days=7, price_df=price_df
    )
    exit_dates  = entry_dates[1:] + [last_exit]

    date_start = entry_dates[0].strftime("%Y-%m-%d")
    date_end   = last_exit.strftime("%Y-%m-%d")

    # Fetch ETF data
    print(f"  Fetching SPY & AGG  {date_start} -> {date_end} ...")
    etf_df = fetch_etf_prices(["SPY", "AGG"], start=date_start, end=date_end)

    # Strategy
    print("  Simulating strategy ...")
    strategy_periods = []
    capital = initial_capital
    for report, entry, exit_ in zip(reports, entry_dates, exit_dates):
        res = simulate_period(
            report["adjusted_allocations"], entry, exit_, price_df, capital
        )
        res["week_end_date"]   = report["week_end_date"]
        res["defensive_mode"]  = report.get("defensive_mode", False)
        res["rules_triggered"] = report.get("rules_triggered", [])
        strategy_periods.append(res)
        capital = res["capital_end"]

    # Benchmark periods (same entry/exit dates)
    bm_periods = [
        {"entry_date": p["entry_date"], "exit_date": p["exit_date"]}
        for p in strategy_periods
    ]

    print("  Simulating benchmarks ...")
    eq_periods  = simulate_equal_weight(all_tickers, bm_periods, price_df, initial_capital)
    spy_periods = simulate_spy(bm_periods, etf_df, initial_capital)
    mix_periods = simulate_60_40(bm_periods, etf_df, initial_capital)

    def returns_and_curve(periods):
        rs = [p["portfolio_return_pct"] / 100 for p in periods]
        cv = [p["capital_end"] for p in periods]
        return rs, cv

    strat_r, strat_cv = returns_and_curve(strategy_periods)
    eq_r,    eq_cv    = returns_and_curve(eq_periods)
    spy_r,   spy_cv   = returns_and_curve(spy_periods)
    mix_r,   mix_cv   = returns_and_curve(mix_periods)

    strat_m = compute_metrics(strat_r, strat_cv, initial_capital)
    eq_m    = compute_metrics(eq_r,    eq_cv,    initial_capital)
    spy_m   = compute_metrics(spy_r,   spy_cv,   initial_capital)
    mix_m   = compute_metrics(mix_r,   mix_cv,   initial_capital)

    out_dir = _resolve(output_dir)
    os.makedirs(out_dir, exist_ok=True)

    # Chart dates: start + one per exit
    chart_dates = [entry_dates[0].strftime("%Y-%m-%d")] + [
        p["exit_date"] for p in strategy_periods
    ]

    print("  Building interactive chart ...")
    build_chart(
        dates            = chart_dates,
        strategy_curve   = strat_cv,
        eq_curve         = eq_cv,
        spy_curve        = spy_cv,
        mix_curve        = mix_cv,
        strategy_periods = strategy_periods,
        initial_capital  = initial_capital,
        output_path      = out_dir / "chart.html",
    )

    # Results JSON
    results = {
        "initial_capital": initial_capital,
        "strategy": {
            "periods": strategy_periods,
            "metrics": strat_m,
        },
        "benchmark_equal_weight": {"periods": eq_periods,  "metrics": eq_m},
        "benchmark_spy":          {"periods": spy_periods, "metrics": spy_m},
        "benchmark_60_40":        {"periods": mix_periods, "metrics": mix_m},
    }
    with open(out_dir / "results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    # Summary text
    summary = write_summary(
        strat_m, eq_m, spy_m, mix_m,
        strategy_periods, initial_capital,
        out_dir / "summary.txt",
    )
    print()
    print(summary)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DebateTrader backtest.")
    parser.add_argument("--risk-dir",        type=str,   default=DEFAULT_RISK_DIR)
    parser.add_argument("--price-file",      type=str,   default=DEFAULT_PRICE_FILE)
    parser.add_argument("--output-dir",      type=str,   default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--initial-capital", type=float, default=DEFAULT_CAPITAL)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("\n=== DebateTrader Backtest ===")
    run_backtest(
        risk_dir       = args.risk_dir,
        price_file     = args.price_file,
        output_dir     = args.output_dir,
        initial_capital= args.initial_capital,
    )


if __name__ == "__main__":
    main()
