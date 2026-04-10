## Project Title

**DebateTrader: A Multi-Agent LLM Framework with Bull-Bear Debate for U.S. Stock Trading**


## Abstract

This project presents DebateTrader, a multi-agent large language model (LLM) framework for simulated U.S. stock trading that uses structured adversarial debate as its core decision-making mechanism. While LLM-based trading agents can outperform traditional quantitative baselines in short-horizon backtests, a fundamental limitation remains: single-agent systems are prone to confirmation bias, where the model selectively emphasizes evidence that supports a directional view without rigorous stress-testing of the opposing case.

DebateTrader addresses this by introducing a two-stage architecture. In the first stage, four specialized analysts independently process distinct data modalities, including fundamental indicators, technical signals, news sentiment, and macroeconomic indicators, and generate structured analytical reports for each stock in a curated six-stock demo universe. In the second stage, a Bull Agent and a Bear Agent each construct investment theses by synthesizing the analyst reports from their respective directional perspectives. After one round of structured rebuttal (configurable to two), a Judge Agent evaluates argument quality and evidentiary strength to produce a final trading signal, position sizing recommendation, and a calibrated confidence score. A Risk Management Agent then enforces portfolio-level constraints, and performance is evaluated through a historical backtest simulation.

The primary objective of this project is to evaluate the overall effectiveness of DebateTrader as a trading system. A key hypothesis is that the degree of disagreement between Bull and Bear Agents, operationalized as the Judge's confidence score, is predictive of subsequent signal accuracy. High-conviction decisions, where one side substantially outargues the other, are expected to yield higher win rates than low-conviction decisions where evidence is balanced. Portfolio performance will be evaluated against S&P 500 buy-and-hold, a 60/40 portfolio benchmark, and a single-agent LLM baseline using Sharpe ratio, maximum drawdown, and win rate as primary metrics.


## Data Sources

| Source | Data Type | Analyst | Update Frequency | Access Method |
|--------|-----------|---------------|-----------------|---------------|
| Yahoo Finance (`yfinance`) | Historical OHLCV price data; supplementary quarterly fundamentals (P/E, margins, cash flow) to fill SEC EDGAR gaps | Technical Analyst; Fundamental Analyst | Daily | Python library |
| SEC EDGAR (XBRL API) | 10-K and 10-Q filings: income statement, balance sheet, and cash flow metrics | Fundamental Analyst | Quarterly | REST API |
| FRED (`fredapi`) | Macroeconomic indicators: Fed funds rate, CPI, 10Y Treasury yield, unemployment rate, GDP, industrial production | Macro Analyst | Monthly | Python library |
| Finnhub News API | Company-specific news headlines and summaries | News & Trend Analyst | Daily | REST API |
| Google Trends (`pytrends`) | Daily retail investor search interest (0–100 scale) per ticker | News & Trend Analyst | Daily | Python library |
| Yahoo Finance (`yfinance`) | Historical OHLCV for backtest entry/exit pricing; ETF prices for benchmarks (SPY, AGG) | (backtest layer, not analyst input) | Daily | Python library |


## Agent Architecture

```
+---------------------------------------------------------------+
|                STOCK UNIVERSE (Demo)                          |
|  6 stocks from S&P 500: 1 per GICS sector                    |
|  AAPL, AMZN, BRK.B, GOOGL, LLY, XOM                         |
+------------------------------+--------------------------------+
                               |
+------------------------------v--------------------------------+
|                      DATA LAYER                               |
|     yfinance   SEC EDGAR   FRED   Finnhub   Google Trends     |
+------------------------------+--------------------------------+
                               |
+------------------------------v--------------------------------+
|                  ANALYST TEAM (parallel)                      |
|                                                               |
|  +-------------+  +-------------+  +----------+  +----------+ |
|  | Fundamental |  |  Technical  |  |  Macro   |  | News &   | |
|  |  Analyst    |  |  Analyst    |  |  Analyst |  | Trend    | |
|  |             |  |             |  |          |  | Analyst  | |
|  | SEC EDGAR,  |  | RSI, MACD,  |  | Fed rate,|  | Finnhub  | |
|  | yfinance    |  | Moving Avg, |  | CPI, GDP,|  | news,    | |
|  | (Quarterly) |  | (Weekly)    |  | (Monthly)|  | G-Trends | |
|  |             |  |             |  |          |  | (Weekly) | |
|  +------+------+  +------+------+  +----+-----+  +----+-----+ |
|         +----------------+--------------+------------+        |
|                       Structured Outputs                      |
+------------------------------+--------------------------------+
                               |
+------------------------------v--------------------------------+
|               DEBATE STAGE (Weekly, Sundays)                  |
|                                                               |
|   +--------------+                   +--------------+         |
|   |  Bull Agent  | ─────────────>    |  Bear Agent  |         |
|   |              |                   |              |         |
|   | Synthesizes  | <─────────────    | Synthesizes  |         |
|   | bullish case |  (1 round, opt 2) | bearish case |         |
|   +--------------+                   +--------------+         |
|                            |                                  |
|                 +----------v----------+                       |
|                 |    Judge Agent      |                       |
|                 |                     |                       |
|                 | Trading direction   |                       |
|                 | Position size       |                       |
|                 +----------+---------+                        |
+------------------------------+--------------------------------+
                               |
+------------------------------v--------------------------------+
|           RISK MANAGEMENT LAYER (Weekly, Rule-Based)          |
|  Confidence floor: 0.55 (exclude weak bullish signals)        |
|  Max single position: 40% of portfolio                        |
|  Max sector concentration: 40%                                |
|  Min holdings: 3 (fewer → defensive equal-weight mode)        |
+------------------------------+--------------------------------+
                               |
+------------------------------v--------------------------------+
|              BACKTEST SIMULATION (Historical)                  |
|  Entry: open of first trading day after each Sunday           |
|  Exit:  open of first trading day after next Sunday           |
|  Benchmarks: Equal-weight, SPY B&H, 60/40 (SPY+AGG)          |
+------------------------------+--------------------------------+
```