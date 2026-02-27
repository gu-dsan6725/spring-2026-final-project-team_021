## Project Title

**DebateTrader: A Multi-Agent LLM Framework with Bull-Bear Debate for U.S. Stock Trading**


## Abstract

This project presents DebateTrader, a multi-agent large language model (LLM) framework for simulated U.S. stock trading that uses structured adversarial debate as its core decision-making mechanism. While LLM-based trading agents can outperform traditional quantitative baselines in short-horizon backtests, a fundamental limitation remains: single-agent systems are prone to confirmation bias, where the model selectively emphasizes evidence that supports a directional view without rigorous stress-testing of the opposing case.

DebateTrader addresses this by introducing a two-stage architecture. In the first stage, four specialized analyst agents independently process distinct data modalities, including fundamental indicators, technical signals, news sentiment, and macroeconomic indicators, and generate structured analytical reports for each stock in a screened pool drawn from the S&P 500. In the second stage, a Bull Agent and a Bear Agent each construct investment theses by synthesizing the analyst reports from their respective directional perspectives. After two rounds of structured rebuttal, a Judge Agent evaluates argument quality and evidentiary strength to produce a final trading signal, position sizing recommendation, and a calibrated confidence score. A Risk Management Agent then enforces portfolio-level constraints before execution via Alpaca's paper trading API.

The primary objective of this project is to evaluate the overall effectiveness of DebateTrader as a trading system. A key hypothesis is that the degree of disagreement between Bull and Bear Agents, operationalized as the Judge's confidence score, is predictive of subsequent signal accuracy. High-conviction decisions, where one side substantially outargues the other, are expected to yield higher win rates than low-conviction decisions where evidence is balanced. Portfolio performance will be evaluated against S&P 500 buy-and-hold, a 60/40 portfolio benchmark, and a single-agent LLM baseline using Sharpe ratio, maximum drawdown, and win rate as primary metrics.


## Data Sources

| Source | Data Type | Update Frequency | Access Method |
|--------|-----------|-----------------|---------------|
| Yahoo Finance (`yfinance`) | Historical OHLCV data, basic fundamentals (P/E, EPS, revenue growth) | Daily | Python library |
| Alpha Vantage | Historical and real-time price data, used to cross-validate Yahoo Finance | Daily | REST API |
| SEC EDGAR | 10-K and 10-Q filings for fundamental analysis | Quarterly | REST API |
| Finnhub News API | Company-specific news headlines and summaries | Daily | REST API |
| FRED (`fredapi`) | Macroeconomic indicators: Fed funds rate, CPI, yield curve, unemployment | Monthly / as released | Python library |
| Stocktwits API | Retail investor sentiment scores per ticker | Daily | REST API |
| Alpaca Markets API | Paper trading execution, real-time quotes during market hours | Real-time | REST API |


## Agent Architecture

```
+---------------------------------------------------------------+
|                STOCK UNIVERSE (Weekly update)                 |
|  S&P 500 filtered by GICS classification: 11 sectors,         |
|  top 3 stocks by market cap per sector = 33 stocks total      |
+------------------------------+--------------------------------+
                               |
+------------------------------v--------------------------------+
|                     DATA LAYER (Daily)                        |
| yfinance  Alpha Vantage  SEC EDGAR  Finnhub  FRED  Stocktwits |
+------------------------------+--------------------------------+
                               |
+------------------------------v--------------------------------+
|              ANALYST TEAM (Weekly, parallel)                  |
|                                                               |
|  +-------------+  +-------------+  +----------+  +----------+ |
|  | Fundamental |  |  Technical  |  |  News &  |  |Sentiment | |
|  |  Analyst    |  |  Analyst    |  |  Macro   |  |Analyst   | |
|  |             |  |             |  | Analyst  |  |          | |
|  | P/E, EPS,   |  | RSI, MACD,  |  | FOMC,    |  |Stocktwits| |
|  | Revenue,    |  | Moving Avg, |  | CPI,News |  |          | |
|  | Margins     |  | Volume      |  | headlines|  |          | |
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