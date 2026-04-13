# DebateTrader

DebateTrader is a multi-agent LLM-based framework for stock trading, where multiple analyst agents generate signals and a structured bull-bear debate produces the final decision.

The system is designed to separate data processing, analysis, and decision-making into modular components, making the pipeline more interpretable and extensible.

---

## Overview

The system follows a two-stage architecture:

1. **Analyst Stage**  
   Multiple analyst agents independently analyze the market from different perspectives (technical, fundamental, etc.) and generate structured signals.

2. **Debate Stage**  
   A Bull agent and a Bear agent construct opposing arguments based on analyst outputs.  
   A Judge agent evaluates both sides and produces the final trading decision.

---

## System Architecture

```

Data Collection → Analyst Agents → Debate (Bull vs Bear) → Judge → Final Signal

````

- Data collection provides structured inputs
- Analyst agents generate independent signals
- Debate stage aggregates and challenges these signals
- Judge outputs final action and confidence

---

## Data Collection

All data is collected through a unified pipeline:

```bash
python src/data_collection/run_pipeline.py
````

### Data Sources

* **Price** → Yahoo Finance (OHLCV)
* **Fundamentals** → SEC EDGAR (primary) + Yahoo Finance (supplementary)
* **Sentiment** → Google Trends (retail attention proxy)
* **News** → Finnhub company headlines
* **Macro** → FRED economic indicators

### Output Structure

```
data/sample/
├── price/
├── fundamentals/
├── sentiment/
├── news/
└── macro/
```

Data is stored in Parquet / CSV format and serves as input to downstream agents.

---

## Analyst Agents

### Technical Analyst

The Technical Analyst focuses on price-based signals using historical market data.

It takes OHLCV data and derives indicators such as moving averages, momentum, and trend signals. Based on these features, it evaluates short-term market behavior.

Responsibilities:

* Identify trends (e.g., price vs moving averages)
* Detect momentum and reversals
* Highlight bullish and bearish technical patterns

Output:

* `signal` (bullish / bearish / neutral)
* `confidence`
* `bullish_factors`
* `bearish_factors`

---

### Fundamental Analyst

The Fundamental Analyst evaluates company performance using quarterly financial data.

It uses structured fundamentals along with derived ratios (margins, ROE, leverage, liquidity) and growth metrics.

Important:

* Uses `filed_date` instead of `period_end` to avoid look-ahead bias

Responsibilities:

* Evaluate profitability and growth
* Assess financial stability
* Identify risks such as high leverage or weak liquidity

Output:

* `signal`
* `confidence`
* `summary`
* `bullish_factors`
* `bearish_factors`
* `risk_flags`

---

## Debate Stage

After analysts generate signals, the system enters a structured debate process.

### Flow

* Bull agent constructs a bullish argument
* Bear agent constructs a bearish argument
* Multiple rounds of rebuttal can be applied
* Judge agent evaluates both sides

### Output

* Final trading signal
* Position direction
* Confidence score

This stage helps reduce bias from any single agent and improves robustness.

---

## Project Structure

```
src/
├── data_collection/     # Data pipeline (price, fundamentals, sentiment, etc.)
├── pipeline/            # End-to-end execution (analyst + debate stages)
├── agents/              # Analyst, Bull, Bear, Judge agents
├── schemas/             # Data formats shared across agents
```

---

## How to Run

Run analyst stage:

```bash
uv run python -m src.pipeline.run_analysts --ticker AAPL
```

Run debate stage:

```bash
uv run python -m src.pipeline.run_debate_stage
```

Run full data pipeline:

```bash
python src/data_collection/run_pipeline.py
```

---

## Key Design Choices

* **Multi-agent architecture**
  Separates different reasoning tasks into specialized agents

* **Structured outputs (schemas)**
  Ensures consistency across pipeline stages

* **No look-ahead bias**
  Fundamental data uses `filed_date` instead of `period_end`

* **Modular pipeline**
  Each component can be run independently or combined

---

## Future Work

* Integrate LLM-based reasoning directly into analyst agents
* Improve evaluation framework and backtesting
* Add more data sources (options, alternative data, etc.)
* Enhance risk management and portfolio allocation

