# PIPELINE

`src/pipeline` contains all execution scripts that orchestrate the end-to-end DebateTrader workflow.

This layer connects data, features, agents, and evaluation into a runnable system.

---

## 1. What This Layer Does

The pipeline is responsible for:

- running analyst agents
- generating weekly debate outputs
- building portfolio allocations
- applying risk management
- running backtests

Each script represents one stage in the full system.

---

## 2. Full Pipeline Flow

```

Data → Features → Analysts → Debate → Portfolio → Risk → Backtest

````

- features: build structured inputs  
- analysts: generate signals  
- debate: aggregate via bull vs bear  
- portfolio: convert signals to allocations  
- risk: enforce constraints  
- backtest: evaluate performance  

---

## 3. Main Pipeline Scripts

### (1) Run Analysts

File: `run_analysts.py` :contentReference[oaicite:0]{index=0}

Runs technical and fundamental analysts for selected tickers.

```bash
uv run python -m src.pipeline.run_analysts --ticker AAPL
````

Output:

* `outputs/analyst_reports/technical/`
* `outputs/analyst_reports/fundamental/`

---

### (2) Generate Historical Reports

File: `run_historical_analyst_reports.py` 

Generates time-series analyst reports for backtesting.

Frequencies:

* technical → weekly
* news/trends → weekly
* fundamental → per filing
* macro → monthly

---

### (3) Run Debate Stage

File: `run_debate_stage.py` 

Runs Bull, Bear, and Judge agents for each week.

Key behavior:

* aligns all inputs to the same Sunday
* uses latest available fundamental & macro data
* supports multi-round debate

Output:

* `outputs/debate_stage/bull/`
* `outputs/debate_stage/bear/`
* `outputs/debate_stage/judge/`
* `outputs/debate_stage/transcript/`

---

### (4) Portfolio Judge

File: `run_portfolio_judge.py` 

Converts per-ticker debate results into a portfolio allocation.

Key idea:

* uses full debate transcripts across all tickers
* allocates capital based on relative conviction

Output:

* `outputs/portfolio_judge/`

---

### (5) Risk Management

File: `run_risk_management.py` 

Applies portfolio constraints and generates risk reports.

Includes:

* max position size
* sector exposure limits
* defensive mode (low conviction)

Output:

* `outputs/risk_management/`

---

### (6) Backtest

File: `run_backtest.py` 

Simulates trading performance based on weekly portfolios.

Includes benchmarks:

* equal-weight portfolio
* SPY buy-and-hold
* 60/40 portfolio

Output:

* `results.json`
* `summary.txt`
* `chart.html`

---

### (7) Dev / Experimental Runner

File: `run_analysts2.py` 

Temporary script for testing additional agents (news, macro).

Used during development before full integration.

---

## 4. How to Run the Full System

Typical workflow:

```bash
# 1. Generate historical analyst reports
python -m src.pipeline.run_historical_analyst_reports

# 2. Run debate stage
python -m src.pipeline.run_debate_stage --all-weeks

# 3. Portfolio allocation
python -m src.pipeline.run_portfolio_judge

# 4. Apply risk management
python -m src.pipeline.run_risk_management

# 5. Run backtest
python -m src.pipeline.run_backtest
```

---

## 5. Design Principles

### Modular Execution

Each stage can be run independently or combined.

---

### Time Alignment

* weekly data aligned to Sundays
* fundamentals filtered by `filed_date`
* macro uses latest available values

This ensures:

* no look-ahead bias
* consistent backtesting

---

### File-Based Communication

All stages communicate via JSON outputs:

* easier debugging
* reproducible pipeline
* no tight coupling between modules
