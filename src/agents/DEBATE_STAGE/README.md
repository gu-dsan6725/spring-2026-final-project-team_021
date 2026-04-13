# DEBATE_STAGE

`src/agents/DEBATE_STAGE` contains the core implementation of the project's debate stage. This stage does not generate raw analyst research on its own. Instead, it takes multiple upstream analyst reports, turns them into a structured bull-vs-bear debate, and then asks a judge agent to produce the final trading view.

This directory contains three agents:

- `BullAgent`: builds the bullish case.
- `BearAgent`: builds the bearish case.
- `JudgeAgent`: compares both sides and outputs the final `signal`, `confidence`, and position suggestion.

The package export is defined in [__init__.py](/E:/GU/6725/spring-2026-final-project-team_021/src/agents/DEBATE_STAGE/__init__.py:1).

## 1. Where This Stage Fits In The Project

Based on the code, `DEBATE_STAGE` is not a standalone script. It is called by the weekly batch pipeline in [run_debate_stage.py](/E:/GU/6725/spring-2026-final-project-team_021/src/pipeline/run_debate_stage.py:1).

Its inputs come from historical analyst reports in four categories:

- `fundamental`
- `technical`
- `macro`
- `news_trends`

The key orchestration logic appears in [run_debate_stage.py](/E:/GU/6725/spring-2026-final-project-team_021/src/pipeline/run_debate_stage.py:434):

1. Create `BullAgent`, `BearAgent`, and `JudgeAgent`.
2. Run `BullAgent.build_case(analyst_reports)` to generate the first bullish argument.
3. Run `BearAgent.rebut(analyst_reports, bull_round_1)` to build the bearish response.
4. If `rounds >= 2`, run another round of rebuttals on both sides.
5. Run `JudgeAgent.judge(...)` on the final bull and bear cases.
6. Save the per-ticker transcript and aggregate weekly bull/bear/judge outputs.

So this directory is responsible for:

- converting multiple analyst reports into structured debate cases
- creating simple bull/bear argument exchange
- producing a normalized final decision for downstream portfolio and risk logic

## 2. Input And Output Contracts

The output schemas for these agents are defined in [debate_output.py](/E:/GU/6725/spring-2026-final-project-team_021/src/schemas/debate_output.py:1).

### `DebateCase`

Both `BullAgent` and `BearAgent` return a `DebateCase` with these fields:

- `agent_name`: the current agent name
- `ticker`: stock ticker
- `analysis_date`: analysis date
- `stance`: `bullish` or `bearish`
- `thesis`: one-sentence core argument
- `confidence`: confidence score between 0 and 1
- `supporting_evidence`: evidence supporting the current side
- `counter_evidence`: evidence that weakens the current side but still needs to be acknowledged
- `rebuttal_points`: direct responses to the opposing case
- `risk_flags`: risk notes
- `score_breakdown`: explainable scoring components

### `JudgeDecision`

`JudgeAgent` returns a `JudgeDecision` with these fields:

- `agent_name`
- `ticker`
- `analysis_date`
- `signal`: `bullish`, `bearish`, or `neutral`
- `confidence`
- `position_size`
- `summary`
- `rationale`
- `dissenting_points`
- `risk_flags`
- `score_breakdown`

These schemas are implemented as dataclasses, but they intentionally expose `model_dump()` and `model_dump_json()` compatibility methods so the rest of the project can use them like lightweight Pydantic-style models without requiring Pydantic at runtime.

## 3. What `BullAgent` Does

Implementation: [bull_agent.py](/E:/GU/6725/spring-2026-final-project-team_021/src/agents/DEBATE_STAGE/bull_agent.py:1)

### Core Responsibility

`BullAgent` builds the strongest bullish thesis it can from the upstream analyst reports, while optionally responding to a bearish case.

Its two main public methods are:

- `build_case(analyst_reports, opponent_case=None)`
- `rebut(analyst_reports, bear_case)`

`rebut(...)` is just a thin wrapper around `build_case(...)` that passes the bear case as `opponent_case`.

### Execution Flow

Inside `build_case()` the flow is:

1. Convert all reports into dictionaries.
2. Raise `ValueError` if the report list is empty.
3. Try `_build_case_with_llm(...)` first.
4. If anything fails, fall back to `_build_case_with_rules(...)`.

This is a clear "LLM first, deterministic fallback second" design.

### LLM Path

The prompt is defined in [debate_stage_prompt.py](/E:/GU/6725/spring-2026-final-project-team_021/src/prompts/debate_stage_prompt.py:1) as `BULL_SYSTEM_PROMPT`.

The prompt enforces several important rules:

- use only the supplied reports and optional opponent case
- do not invent facts, metrics, catalysts, or risks
- acknowledge meaningful opposing evidence
- return JSON only
- keep `confidence` within `[0, 1]`
- keep `score_breakdown` flat and numeric

In `_build_case_with_llm()`, the agent sends the following payload to the LLM:

- `ticker`
- `analysis_date`
- `stance = bullish`
- `analyst_reports`
- `opponent_case` if provided

After parsing the JSON response, the agent normalizes and truncates fields:

- `supporting_evidence`: at most 8 items
- `counter_evidence`: at most 6 items
- `rebuttal_points`: at most 4 items
- `risk_flags`: deduplicated and sorted
- `score_breakdown`: numeric entries only

### Rule-Based Fallback Path

If the LLM path fails, `_build_case_with_rules()` produces a deterministic bullish case using the fields already present in each upstream analyst report.

For each report it reads:

- `agent_name`
- `confidence`
- `signal`
- `bullish_factors`
- `bearish_factors`
- `risk_flags`

Then it computes:

- `signal_bonus = 1.0` when `signal == bullish`
- `signal_bonus = 0.25` when `signal == neutral`
- `signal_bonus = -1.0` when `signal == bearish`

Support score:

```text
support_score = (len(bullish_factors) * 0.8 + max(signal_bonus, 0.0)) * confidence
```

Counter-pressure score:

```text
counter_score = (
    len(bearish_factors) * 0.7
    + max(-signal_bonus, 0.0)
    + len(report_risks) * 0.25
) * confidence
```

Each report's net contribution is stored in `score_breakdown[report_name]`. The final case also includes:

- `aligned_support`
- `opposing_pressure`
- `argument_score`

where:

```text
argument_score = aligned_support - opposing_pressure + len(rebuttal_points) * 0.2
```

In practice, that means the bullish case becomes stronger when:

- more upstream reports contain bullish factors
- report-level signals align with a bullish view
- bearish evidence and risk flags are limited
- the agent can produce explicit rebuttals to the opposing case

### How Rebuttals Are Built

If `opponent_case` is present, `BullAgent` takes up to the first three entries from the opponent's `supporting_evidence` and turns them into rebuttal statements.

Each rebuttal tries to say:

- why the bearish claim is not decisive
- which bullish supporting point weakens it
- what limitation still remains in the opposing argument

If the current case has too little evidence, the agent uses safe fallback sentences instead of failing.

### Thesis And Confidence

In rule-based mode, `_compose_thesis()` builds a one-sentence bullish summary:

- it uses the first supporting evidence item as the lead reason
- if counter-evidence exists, it explicitly says the concerns are manageable rather than thesis-breaking

Confidence comes from `_case_confidence()`:

```text
edge = (aligned_support - opposing_pressure) / max(aligned_support + opposing_pressure, 1.0)
confidence = 0.5 + max(edge, 0.0) * 0.3 + min(rebuttal_count, 3) * 0.03
```

The result is clipped to the range `[0.35, 0.9]`.

## 4. What `BearAgent` Does

Implementation: [bear_agent.py](/E:/GU/6725/spring-2026-final-project-team_021/src/agents/DEBATE_STAGE/bear_agent.py:1)

`BearAgent` is structurally very similar to `BullAgent`, but it flips the perspective and scoring preferences.

### Public Methods

- `build_case(analyst_reports, opponent_case=None)`
- `rebut(analyst_reports, bull_case)`

### LLM Path

It follows the same control flow as `BullAgent`: try the LLM first, then fall back to deterministic rules if necessary. The only difference is that it uses `BEAR_SYSTEM_PROMPT`, which asks the model to produce the strongest bearish thesis from the given evidence.

### Rule-Based Scoring Logic

From the bear perspective, `bearish_factors` are supporting evidence, while `bullish_factors` act as counter-pressure.

Its `signal_bonus` becomes:

- `1.0` when `signal == bearish`
- `0.25` when `signal == neutral`
- `-1.0` when `signal == bullish`

Support score:

```text
support_score = (len(bearish_factors) * 0.8 + max(signal_bonus, 0.0)) * confidence
```

Counter-pressure score:

```text
counter_score = (
    len(bullish_factors) * 0.7
    + max(-signal_bonus, 0.0)
    + len(report_risks) * 0.15
) * confidence
```

One important difference from `BullAgent` is how risk flags are treated:

- `BearAgent` includes `risk_flags` in the final `risk_flags` field
- it also adds them to `supporting_evidence` as explicit downside evidence
- the risk penalty weight is `0.15`
- by contrast, `BullAgent` uses a heavier `0.25` risk weight in the opposing-pressure calculation

This makes the project stance explicit: risks strengthen the bearish case more directly than they strengthen the bullish one.

### Rebuttal Logic

`BearAgent` takes up to the first three items from the bull case's `supporting_evidence` and turns them into bearish rebuttal statements.

The generated response tries to say:

- why the bullish claim is less convincing
- which downside evidence undermines it
- what unresolved issue the upside thesis still depends on overcoming

### Thesis And Confidence

In rule-based mode, `_compose_thesis()` generates a summary like:

- `"{ticker} has a credible downside case because ..."`

If counter-evidence exists, it adds that the bullish evidence does not fully neutralize the risks.

Confidence uses the same formula as `BullAgent`, and is also clipped to `[0.35, 0.9]`.

## 5. What `JudgeAgent` Does

Implementation: [judge_agent.py](/E:/GU/6725/spring-2026-final-project-team_021/src/agents/DEBATE_STAGE/judge_agent.py:1)

`JudgeAgent` is the final arbiter of the debate stage. It does not create a bullish or bearish thesis. Instead, it compares the final bull and bear cases and converts that comparison into a trading decision.

### Constructor Parameters

`JudgeAgent` exposes two tunable parameters:

- `max_position_size`, default `0.08`
- `neutral_margin`, default `0.75`

However, in the weekly pipeline it is instantiated as:

```python
JudgeAgent(max_position_size=1.0)
```

That means the per-ticker judge output is allowed to produce a raw position up to `1.0`, and the weekly pipeline later normalizes those outputs into final portfolio allocations.

### Main Entry Point

`judge(bull_case, bear_case, analyst_reports=None)`

Its control flow mirrors the other agents:

1. Normalize all inputs into dictionaries.
2. Try `_judge_with_llm(...)`.
3. Fall back to `_judge_with_rules(...)` if anything fails.

### LLM Path

The prompt `JUDGE_SYSTEM_PROMPT` requires the model to return:

- `signal`
- `confidence`
- `position_size`
- `summary`
- `rationale`
- `dissenting_points`
- `risk_flags`
- `score_breakdown`

`signal` must be one of:

- `bullish`
- `bearish`
- `neutral`

If the model returns anything else, the code forces the result to `neutral`. The position size is also clamped by `_coerce_position_size()`. If the signal is `neutral`, the position is always set to `0.0`.

### Rule-Based Decision Logic

The rule-based judge is intentionally simple and explainable: it compares the two sides' `argument_score`.

Those scores are read from:

- `bull_case["score_breakdown"]["argument_score"]`
- `bear_case["score_breakdown"]["argument_score"]`

Then it computes:

```text
margin = bull_score - bear_score
```

Decision rule:

- if `abs(margin) < neutral_margin`, return `neutral`
- if `margin > 0`, return `bullish`
- otherwise return `bearish`

With the default `neutral_margin = 0.75`, the system prefers to stay neutral when the debate is too close.

### Risk Handling

`JudgeAgent` merges risks from all available sources:

- `risk_flags` from the bull case
- `risk_flags` from the bear case
- `risk_flags` from every upstream analyst report

The merged result becomes `common_risks`.

### Confidence Formula

Rule-based confidence is computed in `_judge_confidence()`:

```text
total = max(abs(bull_score) + abs(bear_score), 1.0)
margin_ratio = abs(bull_score - bear_score) / total
base = 0.5 + margin_ratio * 0.35
case_confidence_bonus = (max(bull_case.confidence, bear_case.confidence) - 0.5) * 0.15
risk_penalty = min(risk_count, 5) * 0.02
confidence = base + case_confidence_bonus - risk_penalty
```

The final result is clipped to `[0.5, 0.9]`.

This means:

- larger bull-vs-bear separation increases confidence
- strong confidence from either side slightly boosts the judge's confidence
- more risk flags reduce confidence

### Position Sizing

In rule-based mode, `_position_size()` computes:

```text
scaled = max_position_size * max(confidence - 0.5, 0.0) / 0.4
```

Interpretation:

- if `confidence <= 0.5`, position size is near zero
- if confidence approaches `0.9`, position size approaches the configured maximum
- `neutral` always maps to `0.0`

### Rationale, Summary, And Dissenting Points

The judge output is not arbitrary text.

- `rationale`: primarily uses the winning side's `supporting_evidence`
- if upstream reports are available, it may add a sentence listing which analyst agents align with the winning signal
- then it appends up to two rebuttal points from the winning case

If the final result is `neutral`, the judge explains that the two sides are too close and includes evidence from both sides.

`dissenting_points` preserves the strongest evidence from the losing side, so the final decision still records what the other side got right.

## 6. Shared Design Patterns Across All Three Agents

### 6.1 LLM First, Rules As Fallback

All three agents follow the same operating principle:

- when the LLM path works, the output is more natural and more synthesized
- when the LLM path fails, the pipeline still completes using deterministic rule-based logic

This gives the debate stage two important properties:

- stronger online behavior when model calls are available
- stable offline or degraded behavior when the LLM path breaks

### 6.2 Accepts Either Dicts Or Model-Like Objects

Each agent implements `_coerce_report()` and/or `_coerce_case()`:

- if the object has `model_dump()`, the agent uses it
- if the object is already a `dict`, it is accepted directly
- otherwise the code raises a type error

That makes the stage flexible with:

- raw dictionaries
- dataclass-backed schema objects
- Pydantic-style objects with `model_dump()`

### 6.3 Aggressive Cleaning And Bounding

To keep outputs stable and safe for downstream code, the agents consistently:

- clamp confidence values into valid bounds
- strip empty strings from text lists
- deduplicate list entries while preserving order where needed
- keep only numeric entries in `score_breakdown`
- cap evidence list sizes

This matters for JSON persistence, repeatability, and downstream display logic.

## 7. How This Stage Is Persisted In The Pipeline

This directory only defines the agents, but [run_debate_stage.py](/E:/GU/6725/spring-2026-final-project-team_021/src/pipeline/run_debate_stage.py:466) writes the actual outputs to:

- `outputs/debate_stage/bull/{week_end_date}.json`
- `outputs/debate_stage/bear/{week_end_date}.json`
- `outputs/debate_stage/judge/{week_end_date}.json`
- `outputs/debate_stage/transcript/{week_end_date}.json`

The `transcript` file is the most complete artifact. It includes:

- the original `analyst_reports` for each ticker
- `bull_round_1`
- `bear_round_1`
- `bull_final`
- `bear_final`
- `judge_decision`
- `source_report_dates`

If you need to debug debate-stage behavior, `transcript` is the best output to inspect first.

## 8. A Real Single-Ticker Flow

For one ticker, the code effectively does this:

1. Load four upstream analyst reports.
2. Let `BullAgent` construct the initial bullish case.
3. Let `BearAgent` respond to that case with a bearish rebuttal.
4. If configured, run another rebuttal round.
5. Let `JudgeAgent` compare the final bull and bear cases using evidence, risks, scores, and confidence.
6. Return a per-ticker direction and raw position suggestion.
7. Let the weekly pipeline normalize those judge outputs into portfolio-level allocations.

## 9. The Most Important Things To Notice In This Code

- `BullAgent` and `BearAgent` are not perfect mirror images, especially in how they weigh and use `risk_flags`.
- `JudgeAgent` depends heavily on each side's `argument_score`, so if the final verdict looks wrong, the first place to inspect is often the bull/bear scoring logic, not the judge itself.
- In the pipeline, `JudgeAgent(max_position_size=1.0)` is an intermediate step, not the final portfolio allocation.
- `transcript` output is much more useful for debugging than the top-level weekly bull/bear/judge summaries.
- This is not an open-ended autonomous debate framework. It is a structured, bounded, serial debate layer designed for persistence and fallback reliability.

## 10. Minimal Usage Example

```python
from src.agents.DEBATE_STAGE import BullAgent, BearAgent, JudgeAgent

reports = [
    {
        "agent_name": "TechnicalAgent",
        "ticker": "AAPL",
        "analysis_date": "2026-04-12",
        "signal": "bullish",
        "confidence": 0.72,
        "bullish_factors": ["trend remains constructive"],
        "bearish_factors": ["short-term overbought"],
        "risk_flags": ["event volatility"],
    }
]

bull = BullAgent().build_case(reports)
bear = BearAgent().rebut(reports, bull)
decision = JudgeAgent().judge(bull, bear, reports)
```

The returned objects are:

- `bull`: `DebateCase`
- `bear`: `DebateCase`
- `decision`: `JudgeDecision`

