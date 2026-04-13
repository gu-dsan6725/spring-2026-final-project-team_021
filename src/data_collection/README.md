## Data Collection

This folder contains the full data pipeline for DebateTrader.

It collects all data needed by downstream agents, including price, fundamentals, sentiment, news, and macro indicators.

### Pipeline Overview

The main entry point is:

```bash
python src/data_collection/run_pipeline.py
````

The pipeline runs 5 steps in order:

1. **Price (Yahoo Finance)**
   Collects daily OHLCV data for each ticker
   → used by the Technical Analyst
   (see `price_collector.py` )

2. **Fundamentals (SEC EDGAR + Yahoo Finance)**
   Builds quarterly financial data with ratios
   → used by the Fundamental Analyst
   (see `fundamental_collector.py` )

3. **Google Trends (Retail Attention)**
   Uses search interest as a proxy for sentiment
   → used by the Sentiment Analyst
   (see `google_trends_collector.py` )

4. **News (Finnhub)**
   Collects company news headlines and summaries
   → used for news sentiment / event signals
   (see `finnhub_news_fetch.py` )

5. **Macro (FRED)**
   Collects macroeconomic indicators (rates, inflation, etc.)
   → used by macro-aware agents
   (see `fred_macro_fetch.py` )

---

### Configuration

All shared settings are defined in:

* `config.py` 

Includes:

* Ticker universe
* Date ranges
* Output paths
* API-related settings

---

### Output Structure

All data is saved under:

```
data/sample/
```

* `price/` → OHLCV parquet
* `fundamentals/` → quarterly fundamentals
* `sentiment/` → Google Trends
* `news/` → company news
* `macro/` → macro indicators

---

### Notes

* The pipeline is modular, each step can be skipped via CLI flags
* Data is stored in parquet format for efficiency
* Fundamentals use `filed_date` (NOT `period_end`) to avoid look-ahead bias
* Google Trends uses per-ticker normalization (no cross-ticker scaling)

---

### Utility Script

* `parquet_to_csv.py` 
  Converts parquet files to CSV for easier inspection

---

### TL;DR

This folder is basically the data backbone of the whole system.
All agents depend on the outputs generated here.
