# Backtest Output

This directory contains paper-trading backtest results for the DebateTrader strategy. Results are re-generated each time the pipeline runs with updated data.

## How it fits in the pipeline

```
outputs/risk_management/{date}.json   (adjusted weekly portfolios)
data/sample/price/price_ohlcv.parquet (stock OHLCV)
yfinance (SPY, AGG live fetch)
        ↓
Backtest  ←  src/pipeline/run_backtest.py
        ↓
outputs/backtest/   ← this directory
```

## Run

```bash
python -m src.pipeline.run_backtest

# Custom initial capital
python -m src.pipeline.run_backtest --initial-capital 500000

# Custom paths
python -m src.pipeline.run_backtest \
    --risk-dir   outputs/risk_management \
    --price-file data/sample/price/price_ohlcv.parquet \
    --output-dir outputs/backtest
```

## Simulation rules

- **Entry**: opening price of the first trading day *after* each portfolio's `week_end_date` (Sunday)
- **Exit**: opening price of the first trading day *after* the next portfolio's Sunday (i.e. 7 days later), which coincides with the next period's entry date
- No transaction costs, slippage, or taxes (paper trading)
- Weights come directly from `adjusted_allocations` in the risk management reports

## Benchmarks

Each benchmark isolates a different dimension of the strategy's performance.

| Name | Purpose |
|------|---------|
| **Equal-weight** | Holds all 6 universe tickers at 1/6 each, rebalanced every period. Serves as the baseline for stock selection and position sizing. Outperforming equal-weight indicates that the Judge's directional calls and the risk manager's weight adjustments add value beyond simple diversification within the same universe. |
| **SPY B&H** | Buy-and-hold the S&P 500 ETF, representing passive exposure to the broad equity market. Outperforming SPY on a risk-adjusted basis indicates that the concentrated 6-stock portfolio generates genuine alpha rather than merely riding market beta. |
| **60/40** | 60% SPY + 40% AGG, rebalanced every period. A standard institutional multi-asset allocation that trades some equity upside for bond-side stabilization. Outperforming 60/40 on a risk-adjusted basis indicates that the concentrated equity approach justifies its higher single-asset-class risk. |

## Output files

### `results.json`

Full per-period breakdown and aggregate metrics for all four series (strategy + 3 benchmarks).

Top-level structure:
```json
{
  "strategy":               { "periods": [...], "metrics": {...} },
  "benchmark_equal_weight": { "periods": [...], "metrics": {...} },
  "benchmark_spy":          { "periods": [...], "metrics": {...} },
  "benchmark_60_40":        { "periods": [...], "metrics": {...} }
}
```

Each `periods` entry:
```json
{
  "entry_date": "2025-08-04",
  "exit_date":  "2025-08-11",
  "holdings": {
    "AAPL": {
      "weight_pct": 16.67,
      "entry_price": 123.45,
      "exit_price":  126.00,
      "return_pct":  2.07,
      "contribution_pct": 0.34
    }
  },
  "portfolio_return_pct": 2.42,
  "capital_start": 1000000.0,
  "capital_end":   1024239.0
}
```

Each `metrics` object:

| Key | What it measures |
|-----|-----------------|
| `total_return_pct` | Cumulative compounded return over the entire simulation window. Represents the absolute growth of the portfolio from start to finish and is the primary headline number for comparing strategies. |
| `annualised_return_pct` | Total return scaled to a one-year equivalent, assuming 52 trading weeks per year. Normalises performance across simulations of different lengths and enables direct comparison with annually quoted benchmark returns. |
| `sharpe_ratio` | Annualised return divided by annualised volatility of weekly returns, with a risk-free rate of zero. Captures return per unit of risk taken. A higher Sharpe indicates the strategy generates returns efficiently rather than through elevated volatility. |
| `max_drawdown_pct` | The largest peak-to-trough decline in portfolio value observed across all periods. Represents the worst-case loss an investor would have experienced at any point during the simulation and reflects the downside risk of the strategy. |
| `win_rate_pct` | The percentage of weekly periods that ended with a positive return. Measures directional consistency. A high win rate indicates the strategy is correct more weeks than not, though it should be read alongside average return to detect whether gains are broad-based or concentrated in a few outlier periods. |
| `avg_weekly_return_pct` | The arithmetic mean of all weekly returns. When read alongside win rate, a high average paired with a high win rate indicates steady and repeatable performance rather than a skewed distribution driven by a small number of large-gain weeks. |

### `summary.txt`

Human-readable performance table comparing the strategy against all three benchmarks, plus a per-period detail table.

Example:
```
Metric                    Strategy   EqWeight    SPY B&H      60/40
Total return               +26.68%    +27.61%     +9.73%     +6.10%
Annualised return          +74.89%    +77.96%    +24.54%    +15.03%
Sharpe ratio (ann.)         5.3335     5.5306     2.6214     2.6277
Max drawdown                +2.70%     +1.90%     +3.35%     +1.99%
Win rate                     81.8%      77.3%      63.6%      59.1%
```

### `chart.html`

Interactive Plotly line chart showing the growth of $1,000,000 across all four series. Open in any browser — no server needed.
