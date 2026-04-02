## Project Title

**DebateTrader: A Multi-Agent LLM Framework with Bull-Bear Debate for U.S. Stock Trading**


## Abstract

This project presents DebateTrader, a multi-agent large language model (LLM) framework for simulated U.S. stock trading that uses structured adversarial debate as its core decision-making mechanism. While LLM-based trading agents can outperform traditional quantitative baselines in short-horizon backtests, a fundamental limitation remains: single-agent systems are prone to confirmation bias, where the model selectively emphasizes evidence that supports a directional view without rigorous stress-testing of the opposing case.

DebateTrader addresses this by introducing a two-stage architecture. In the first stage, four specialized analyst agents independently process distinct data modalities, including fundamental indicators, technical signals, news sentiment, and macroeconomic indicators, and generate structured analytical reports for each stock in a screened pool drawn from the S&P 500. In the second stage, a Bull Agent and a Bear Agent each construct investment theses by synthesizing the analyst reports from their respective directional perspectives. After two rounds of structured rebuttal, a Judge Agent evaluates argument quality and evidentiary strength to produce a final trading signal, position sizing recommendation, and a calibrated confidence score. A Risk Management Agent then enforces portfolio-level constraints before execution via Alpaca's paper trading API.

The primary objective of this project is to evaluate the overall effectiveness of DebateTrader as a trading system. A key hypothesis is that the degree of disagreement between Bull and Bear Agents, operationalized as the Judge's confidence score, is predictive of subsequent signal accuracy. High-conviction decisions, where one side substantially outargues the other, are expected to yield higher win rates than low-conviction decisions where evidence is balanced. Portfolio performance will be evaluated against S&P 500 buy-and-hold, a 60/40 portfolio benchmark, and a single-agent LLM baseline using Sharpe ratio, maximum drawdown, and win rate as primary metrics.


## Data Sources

| Source | Data Type | Analyst Agent | Update Frequency | Access Method |
|--------|-----------|---------------|-----------------|---------------|
| Yahoo Finance (`yfinance`) | Historical OHLCV price data; supplementary quarterly fundamentals (P/E, margins, cash flow) to fill SEC EDGAR gaps | Technical Analyst; Fundamental Analyst | Daily | Python library |
| SEC EDGAR (XBRL API) | 10-K and 10-Q filings: income statement, balance sheet, and cash flow metrics | Fundamental Analyst | Quarterly | REST API |
| FRED (`fredapi`) | Macroeconomic indicators: Fed funds rate, CPI, 10Y Treasury yield, unemployment rate, GDP, industrial production | Macro Analyst | Monthly | Python library |
| Finnhub News API | Company-specific news headlines and summaries | News & Trend Analyst | Daily | REST API |
| Google Trends (`pytrends`) | Daily retail investor search interest (0–100 scale) per ticker | News & Trend Analyst | Daily | Python library |
| Alpaca Markets API | Paper trading execution; real-time quotes during market hours | (execution layer, not analyst input) | Real-time | REST API |


## Agent Architecture

```
+---------------------------------------------------------------+
|                STOCK UNIVERSE (Weekly update)                 |
|  S&P 500 filtered by GICS classification: 11 sectors,         |
|  top 3 stocks by market cap per sector = 33 stocks total      |
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
|  | (Quarterly) |  | (Weekly)     |  | (Monthly)|  | G-Trends | |
|  |             |  |             |  |          |  | (Weekly)  | |
|  +------+------+  +------+------+  +----+-----+  +----+-----+ |
|         +----------------+--------------+------------+        |
|                       Structured Reports                      |
+------------------------------+--------------------------------+
                               |
+------------------------------v--------------------------------+
|                  DEBATE STAGE (Weekly)                        |
|                                                               |
|   +--------------+      Round 1      +--------------+         |
|   |  Bull Agent  | <-------------->  |  Bear Agent  |         |
|   |              |      Round 2      |              |         |
|   | Synthesizes  | <-------------->  | Synthesizes  |         |
|   | bullish case |                   | bearish case |         |
|   +--------------+                   +--------------+         |
|                            |                                  |
|                 +----------v----------+                       |
|                 |    Judge Agent      |                       |
|                 |                     |                       |
|                 | Trading direction   |                       |
|                 | Position size       |                       |
|                 | Confidence score    |                       |
|                 +----------+---------+                        |
+------------------------------+--------------------------------+
                               |
+------------------------------v--------------------------------+
|              RISK MANAGEMENT AGENT (Weekly)                   |
|  Max single position: 8% of portfolio                         |
|  Max sector concentration: 30%                                |
|  Portfolio drawdown stop: 15%                                 |
|  Veto power over Judge decisions                              |
+------------------------------+--------------------------------+
                               |
+------------------------------v--------------------------------+
|           PAPER TRADING EXECUTION (Monday open)               |
|                   Alpaca Markets API                          |
+------------------------------+--------------------------------+
                               |
+------------------------------v--------------------------------+
|              POST-MORTEM AGENT (Monthly)                      |
|  Judge confidence score vs. actual win rate correlation       |
|  Bull and Bear agent historical accuracy tracking             |
|  Findings fed back into the next cycle's System Prompt        |
+---------------------------------------------------------------+
```