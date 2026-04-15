# DebateTrader: A Multi-Agent LLM Framework with Structured Bull–Bear Debate for Stock Trading

---

## Abstract

DebateTrader is a multi-agent framework for stock trading that introduces structured debate into the decision-making process. While large language model (LLM)-based systems can flexibly integrate diverse financial information, most existing approaches rely on a single agent to generate signals, which can lead to confirmation bias and limited evaluation of conflicting evidence.

To address this, DebateTrader decomposes trading decisions into multiple stages. Specialized analyst agents first generate structured signals from different data sources, including technical indicators, company fundamentals, macroeconomic conditions, and news sentiment. A Bull agent and a Bear agent then construct opposing investment arguments, followed by a Judge agent that determines the final decision. At the portfolio level, a separate agent evaluates all assets jointly and allocates capital based on relative conviction.

The system is evaluated on a curated universe of six S&P 500 stocks using a historical backtesting framework with weekly rebalancing. This controlled setting allows us to focus on system behavior and decision quality. We hypothesize that structured disagreement improves robustness and leads to more differentiated and interpretable portfolio allocations.

---

## 1. Introduction

Stock trading requires synthesizing information from multiple sources, including price movements, company fundamentals, macroeconomic conditions, and market sentiment. Traditional quantitative approaches rely on predefined features and statistical models, which often struggle to incorporate unstructured data such as news or narrative signals. With the emergence of large language models (LLMs), it has become possible to reason over heterogeneous data in a more flexible way.

Despite this progress, most LLM-based trading systems rely on a single-agent design, where one model produces the final decision. This setup introduces a key limitation: the model may exhibit confirmation bias and lacks mechanisms for internal critique or comparison.

This project explores whether structured disagreement can improve decision quality. We propose DebateTrader, a multi-agent framework that separates trading decisions into independent analysis, adversarial argumentation, and final judgment. Multiple analyst agents first generate signals from different data modalities, after which a Bull and Bear agent construct opposing perspectives that are evaluated by a Judge agent.

Beyond individual decisions, we also consider portfolio-level reasoning. Instead of assigning weights independently, the system evaluates all assets jointly and allocates capital based on relative conviction, which better reflects real-world investment decision-making.

To enable detailed analysis, we restrict the evaluation to a curated universe of six S&P 500 stocks, each representing a different sector. This allows us to focus on system behavior and decision processes rather than large-scale optimization.

---

## 2. Related Work

Existing work on AI-driven trading systems can be broadly grouped into traditional quantitative models, machine learning approaches, and more recent LLM-based methods. Classical approaches such as factor models and time-series forecasting rely on structured numerical data and predefined assumptions. While these methods are often interpretable, they are limited in incorporating unstructured information such as textual sentiment.

Recent work explores the use of LLMs for financial reasoning, including summarizing earnings reports, extracting sentiment from news, and generating trading signals. These approaches benefit from flexible reasoning but are typically built on a single-agent framework, which lacks mechanisms for evaluating conflicting evidence.

Multi-agent systems provide an alternative by decomposing complex reasoning tasks into specialized components. In particular, debate-based frameworks, where agents argue opposing viewpoints, have shown improvements in reasoning quality and robustness. However, most prior work focuses on general reasoning tasks rather than domain-specific applications.

DebateTrader extends these ideas to financial decision-making by combining multi-modal data with structured bull–bear debate and introducing portfolio-level reasoning. This design allows the system to compare assets directly and produce differentiated allocations.

---

## 3. System Architecture

DebateTrader follows a modular multi-agent architecture, as illustrated in Figure 1. The system separates data processing, analysis, reasoning, and execution into distinct stages, allowing each component to operate independently.

The pipeline begins with a data layer that collects information from multiple sources, including market prices, financial statements, macroeconomic indicators, and news data. These inputs are transformed into structured feature snapshots that represent the information available at a given point in time, ensuring consistency across agents and avoiding future data leakage.

In the analysis stage, specialized agents evaluate each stock from different perspectives. The technical analyst focuses on price-based indicators such as trends and momentum, while the fundamental analyst evaluates financial performance and balance sheet health. Additional agents incorporate macroeconomic signals and news-driven sentiment. Each agent produces a structured output containing a signal, confidence score, and supporting evidence.

These outputs are then passed to a debate stage, where a Bull agent constructs a positive case and a Bear agent constructs a negative case. After a structured rebuttal process, a Judge agent evaluates both sides and produces a final decision.

The system then performs portfolio-level reasoning by evaluating all assets jointly and assigning weights based on relative conviction. Finally, a risk management module applies constraints such as position limits and sector exposure, and the strategy is evaluated through backtesting.

### Figure 1. System Architecture

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
|  Fundamental | Technical | Macro | News & Trend               |
+------------------------------+--------------------------------+
|
+------------------------------v--------------------------------+
|               DEBATE STAGE (Bull vs Bear + Judge)             |
+------------------------------+--------------------------------+
|
+------------------------------v--------------------------------+
|          PORTFOLIO JUDGE (cross-ticker)                       |
+------------------------------+--------------------------------+
|
+------------------------------v--------------------------------+
|           RISK MANAGEMENT + BACKTEST                          |
+---------------------------------------------------------------+

```

---

## 4. Data and Evaluation

The system integrates multiple data sources covering market prices, financial statements, macroeconomic indicators, and news signals. These sources provide complementary views of each asset and enable the model to capture both quantitative trends and information-driven signals.

The evaluation is conducted on a fixed universe of six large-cap U.S. equities selected from the S&P 500, each representing a different sector. This setup ensures diversity while keeping the system manageable for detailed analysis. The goal is to study system behavior rather than optimize performance at scale.

A summary of the data sources is provided in Table 1.

### Table 1. Data Sources Used in DebateTrader

| Source                     | Data Type                                               | Analyst                | Update Frequency | Access Method  |
| -------------------------- | ------------------------------------------------------- | ---------------------- | ---------------- | -------------- |
| Yahoo Finance (`yfinance`) | Historical OHLCV price data; supplementary fundamentals | Technical; Fundamental | Daily            | Python library |
| SEC EDGAR (XBRL API)       | Financial statements (10-K, 10-Q)                       | Fundamental            | Quarterly        | REST API       |
| FRED (`fredapi`)           | Macroeconomic indicators                                | Macro                  | Monthly          | Python library |
| Finnhub News API           | Company news data                                       | News & Trend           | Daily            | REST API       |
| Google Trends (`pytrends`) | Retail attention signals                                | News & Trend           | Daily            | Python library |
| Yahoo Finance (`yfinance`) | Backtest pricing data (SPY, AGG)                        | Backtest               | Daily            | Python library |

All data is preprocessed to ensure temporal alignment. Financial data is filtered using the filing date rather than the reporting period end date, preventing the use of future information and avoiding look-ahead bias. The processed data is converted into structured feature snapshots representing the information available at each decision point.

The system is evaluated using a historical backtesting framework with weekly rebalancing. At each step, the model generates signals, constructs a portfolio, and simulates returns based on subsequent market data.

Performance is compared against baseline strategies including S&P 500 buy-and-hold, an equal-weight portfolio, and a 60/40 allocation. Evaluation metrics include Sharpe ratio, maximum drawdown, and win rate, capturing both return and risk characteristics.
