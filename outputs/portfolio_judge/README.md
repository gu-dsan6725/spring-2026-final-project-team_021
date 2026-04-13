# Portfolio Judge Output

This directory contains weekly portfolio allocation reports produced by the Portfolio Judge layer of DebateTrader.

## How it fits in the pipeline

```
Debate Stage (transcript output)
        ↓
Portfolio Judge  ←  src/agents/portfolio_judge.py
        ↓
outputs/portfolio_judge/{YYYY-MM-DD}.json   ← this directory
        ↓
Risk Management
```

Unlike the per-stock Judge Agent (which evaluates each ticker in isolation), the Portfolio Judge receives all 6 tickers' full debate transcripts in a single LLM call, forcing cross-ticker ranking before weight assignment.

Each file corresponds to one week, named after the Sunday `week_end_date` of that week.

## Run

```bash
# All available weeks
python -m src.pipeline.run_portfolio_judge

# Filter by date range
python -m src.pipeline.run_portfolio_judge --start-date 2025-08-03 --end-date 2025-12-28

# Custom directories
python -m src.pipeline.run_portfolio_judge \
    --transcript-dir outputs/debate_stage/transcript \
    --output-dir outputs/portfolio_judge \
    --delay 15
```

**Input required** (per week):
- `outputs/debate_stage/transcript/{date}.json` — Full debate transcripts for all tickers

## Output schema (`{date}.json`)

```json
{
  "week_end_date": "2025-12-28",
  "agent_name": "PortfolioJudge",
  "tickers": ["AAPL", "AMZN", "BRK.B", "GOOGL", "LLY", "XOM"],
  "portfolio_rationale": "...",
  "ranking": ["LLY", "AAPL", "GOOGL", "AMZN", "XOM", "BRK.B"],
  "holdings": {
    "LLY":   { "weight_pct": 40.0, "reason": "..." },
    "AAPL":  { "weight_pct": 30.0, "reason": "..." },
    "GOOGL": { "weight_pct": 20.0, "reason": "..." },
    "AMZN":  { "weight_pct": 10.0, "reason": "..." },
    "XOM":   { "weight_pct": 0.0,  "reason": "..." },
    "BRK.B": { "weight_pct": 0.0,  "reason": "..." }
  },
  "total_allocated_pct": 100.0
}
```

| Field | Description |
|-------|-------------|
| `ranking` | Tickers ordered from highest to lowest conviction |
| `portfolio_rationale` | 2-3 sentence explanation of the overall allocation logic |
| `holdings` | Per-ticker weight and one-sentence reason; zero-weight tickers are included |
| `total_allocated_pct` | Sum of all `weight_pct` values (target: 100%; may be < 100 if LLM under-allocates — renormalized downstream by Risk Manager) |

## Ticker universe

| Ticker | Sector |
|--------|--------|
| AAPL | Technology |
| AMZN | Consumer Discretionary |
| BRK.B | Financials |
| GOOGL | Communication Services |
| LLY | Health Care |
| XOM | Energy |
