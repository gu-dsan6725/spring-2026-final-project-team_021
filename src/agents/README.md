# AGENTS

`src/agents` contains all agent implementations used in DebateTrader.

These agents are responsible for transforming structured data into trading signals, arguments, and final portfolio decisions.

The design follows a modular multi-agent architecture, where each agent focuses on a specific role and communicates through structured outputs.

---

## 1. Agent Categories

This directory includes three types of agents:

### (1) Analyst Agents

Generate independent signals from different perspectives.

- `TechnicalAnalyst` :contentReference[oaicite:0]{index=0}  
  Uses price-based indicators (trend, momentum, volatility)

- `FundamentalAnalyst` :contentReference[oaicite:1]{index=1}  
  Uses financial statements and ratios (growth, margins, leverage)

- `MacroAnalyst` :contentReference[oaicite:2]{index=2}  
  Evaluates macroeconomic conditions (rates, inflation, labor market)

- `NewsTrendsAnalyst` :contentReference[oaicite:3]{index=3}  
  Uses company news and Google Trends sentiment

All analyst agents output a standardized schema:

```json
{
  "signal": "bullish | bearish | neutral",
  "confidence": 0.0,
  "summary": "...",
  "bullish_factors": [],
  "bearish_factors": [],
  "risk_flags": []
}
````

---

### (2) Debate Agents

Located in `DEBATE_STAGE/`

* BullAgent
* BearAgent
* JudgeAgent

These agents take analyst outputs and turn them into a structured bull-vs-bear debate.

See: 

---

### (3) Portfolio & Risk Agents

Operate after the debate stage to produce final allocations.

* `PortfolioJudge` 
  Allocates capital across multiple tickers using full debate transcripts

* `RiskManager` 
  Applies portfolio constraints (position limits, sector caps, defensive mode)

---

## 2. Design Pattern

All agents follow a consistent pattern:

### Hybrid (Rules + LLM)

* Deterministic logic extracts structured evidence
* LLM synthesizes final outputs (signal, summary, confidence)

Example (Technical Analyst):

* rules → extract indicators (MA, RSI, MACD)
* LLM → generate final decision 

This provides:

* interpretability from rules
* flexibility from LLM reasoning
* robustness via fallback behavior

---

### Structured Outputs

All agents communicate using predefined schemas (`src/schemas`).

This ensures:

* consistent data flow across pipeline stages
* easier debugging and persistence
* compatibility between rule-based and LLM outputs

---

### LLM Fallback Strategy

For most agents:

* try LLM first
* fall back to deterministic logic if LLM fails

This keeps the system stable even under API failures.

---

## 3. How Everything Connects

Full pipeline:

```
Data → Analyst Agents → Debate → Portfolio Judge → Risk Manager
```

* Analyst agents generate signals
* Debate agents refine and challenge them
* Portfolio judge converts signals into allocations
* Risk manager enforces constraints

---

## 4. Key Idea

Instead of relying on a single model, DebateTrader:

* separates reasoning into specialized agents
* forces disagreement through debate
* delays final decisions until after aggregation

This improves both robustness and interpretability.
