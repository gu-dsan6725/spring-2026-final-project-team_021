# Milestone 2: Updated Architecture and Risks

## Current Progress

- The data pipeline has been implemented and tested with sample data.
- The main data APIs used in the project have been verified to work.
- The analyst team agents have been implemented with basic functionality.
- The pipeline has successfully run end-to-end on sample tickers.

## Updated Architecture Based on Early Learnings

The overall architecture remains the same as the proposal: a multi-agent stock analysis pipeline that feeds into a debate-based trading decision layer. Based on early implementation work, we narrowed the current milestone to getting the data layer and analyst layer working reliably first, then connecting those outputs into the first debate-stage agent.

```
+---------------------------------------------------------------+
|                STOCK UNIVERSE (Weekly update)                 |
|  S&P 500 filtered by GICS classification: 11 sectors,         |
|  top 3 stocks by market cap per sector = 33 stocks total      |
+------------------------------+--------------------------------+
                               |
+------------------------------v--------------------------------+
|                     DATA LAYER (Daily)                        |
| yfinance  Alpha Vantage  SEC EDGAR  Finnhub  FRED  Google     |
| Trends                                                        |
+------------------------------+--------------------------------+
                               |
+------------------------------v--------------------------------+
|              ANALYST TEAM (Weekly, parallel)                  |
|                                                               |
|  +-------------+  +-------------+  +----------+  +----------+ |
|  | Fundamental |  |  Technical  |  |   News/  |  |  Macro   | |
|  |  Analyst    |  |  Analyst    |  |  Trends  |  | Analyst  | |
|  |             |  |             |  |  Analyst |  |          | |
|  | P/E, EPS,   |  | RSI, MACD,  |  | News     |  | Fed      | |
|  | Revenue,    |  | SMA/EMA,    |  | sentiment|  | funds,   | |
|  | Margins     |  | Returns     |  | & tone   |  | CPI, GDP | |
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

## Identified Risks and Mitigation Plans

| Risk Type | Risk Description | Mitigation |
|-----------|------------------|------------|
| Data | Data gaps across sources | Standardize by analysis date and use the latest valid snapshot when data is missing. |
| Model | LLM output inconsistency | Use schema checks, constrained prompts, and low temperature. |
| Integration | Incomplete end-to-end integration | Integrate in stages: analysts first, then debate, then risk and execution. |
| Evaluation | Limited ticker coverage in early testing | Expand testing gradually across more sectors and names. |