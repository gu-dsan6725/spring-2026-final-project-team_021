# FEATURES

`src/features` contains feature builders that transform raw data into structured snapshots used by analyst agents.

These modules sit between data collection and agent reasoning.

---

## 1. What This Layer Does

The feature layer converts raw datasets into clean, model-ready inputs.

Instead of letting agents read raw data directly, each feature builder produces a **single standardized snapshot** per ticker and date.

This ensures:
- consistent inputs across agents
- no data leakage
- simpler agent logic

---

## 2. Feature Builders

### (1) Technical Features

File: `technical_features.py`

Builds price-based indicators from OHLCV data.

Includes:
- moving averages (SMA, EMA)
- momentum (returns)
- volatility
- RSI
- MACD
- volume ratios

Output example:

```json
{
  "price_features": {
    "close": 180.5,
    "sma_20": 175.2,
    "rsi_14": 62.1,
    "macd": 1.23
  }
}
````

Used by:

* Technical Analyst

---

### (2) Fundamental Features

File: `fundamental_features.py` 

Builds financial feature snapshots from quarterly fundamentals.

Key design:

* filters using `filed_date <= analysis_date`
* avoids look-ahead bias

Includes:

* growth metrics (revenue, earnings)
* margins
* ROE / ROA
* leverage and liquidity
* cash flow metrics

Also:

* normalizes percentage-like values into decimals

Used by:

* Fundamental Analyst

---

### (3) News & Macro Features

File: `news_macro_features.py` 

Combines multiple data sources into a single snapshot:

* company news (Finnhub)
* sentiment scoring (LM lexicon)
* Google Trends (retail attention)
* macroeconomic indicators (FRED)

Includes:

* article-level sentiment classification
* relevance estimation
* aggregated news statistics
* macro indicators + derived growth metrics

Used by:

* NewsTrends Analyst
* Macro Analyst

---

## 3. Snapshot Design

All feature builders follow the same pattern:

```python
snapshot = {
    "ticker": "...",
    "analysis_date": "...",
    "..._features": {...}
}
```

Key idea:

each snapshot represents **what was known at that time**

This is critical for:

* backtesting correctness
* avoiding future information leakage
* reproducibility

---

## 4. Why This Layer Exists

Without this layer, agents would:

* duplicate feature engineering logic
* risk inconsistent calculations
* accidentally introduce look-ahead bias

With this design:

* feature logic is centralized
* agents only focus on reasoning
* debugging becomes much easier

---

## 5. How It Fits In The Pipeline

```
Raw Data → Feature Builders → Analyst Agents → Debate → Portfolio → Risk
```

- data_collection → raw data  
- features → structured snapshots  
- agents → decision logic  
