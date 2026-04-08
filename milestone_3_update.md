# Milestone 3: System Integration and Initial Evaluation

Building on the architecture described in Milestone 2, the system has now been extended from a partially connected pipeline into a working end-to-end workflow. The overall structure remains the same as the previously proposed design, including the data layer, analyst layer, debate stage, and downstream components shown in the diagram. However, in this milestone, these components are no longer isolated and have been connected into a complete pipeline that can run from data ingestion to portfolio evaluation.

In the analyst layer, the four analyst agents (fundamental, technical, news/trends, and macro) are now fully implemented and produce structured reports on a weekly basis. These reports serve as the direct inputs to the debate stage, consistent with the architecture outlined previously. One important implementation detail is that all reports are aligned by availability date rather than reporting period, which helps avoid data leakage and ensures that each weekly decision only uses information that would have been available at that time.

The debate stage described in the architecture diagram has now been implemented as a weekly batch process. For each ticker and each week, the system runs a structured interaction between the Bull and Bear agents, followed by a final decision from the Judge agent. The Judge outputs a trading signal, confidence score, and position sizing suggestion. The system also supports both single-round and multi-round debate settings, which allows us to control the trade-off between computational cost and reasoning depth. In addition, the full debate transcript is stored for each ticker, which makes the decision process transparent and easier to analyze.

Following the debate stage, the risk management layer introduced in the architecture has also been implemented. Instead of directly executing the Judge’s output, the system applies a set of rule-based constraints, including a confidence threshold, maximum position size, and diversification requirements. This layer acts as a control mechanism that adjusts the raw decisions into a more realistic portfolio, reflecting practical trading considerations.

To support evaluation, a backtesting component has been added after the risk management stage. This component simulates weekly trading based on the generated portfolios and produces performance metrics such as total return, Sharpe ratio, drawdown, and win rate. It also compares the system against simple benchmark strategies, including equal-weight allocation, SPY buy-and-hold, and a 60/40 portfolio. This provides an initial framework for evaluating the system at the portfolio level rather than only at the individual agent level.

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