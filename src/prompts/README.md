# PROMPTS

`src/prompts` defines all LLM system prompts used in DebateTrader.

These prompts control how each agent reasons, what it is allowed to use, and how outputs are structured.

---

## 1. What This Layer Does

This folder defines the **behavior and constraints** of all LLM-based agents.

Instead of letting agents generate free-form responses, prompts enforce:

- strict reasoning boundaries  
- structured outputs (JSON)  
- consistency across agents  
- no hallucination beyond provided data  

---

## 2. Prompt Categories

### (1) Analyst Prompts

Used by analyst agents to convert structured features into signals.

- Technical Analyst → :contentReference[oaicite:0]{index=0}  
- Fundamental Analyst → :contentReference[oaicite:1]{index=1}  

Key design:
- input = rule-extracted factors + metrics  
- output = signal + confidence + short summary  

Constraints:
- must not invent data  
- must stay grounded in provided evidence  
- must return valid JSON only  

---

### (2) Debate Prompts

Used in the multi-agent debate stage.

File: `debate_stage_prompt.py` :contentReference[oaicite:2]{index=2}  

Includes:
- Bull Agent  
- Bear Agent  
- Judge Agent  

Roles:

- **Bull** → build strongest bullish case  
- **Bear** → build strongest bearish case  
- **Judge** → compare both sides and decide  

Key idea:
- forces structured disagreement  
- preserves both sides of reasoning  
- produces interpretable decision logic  

---

### (3) Portfolio Prompt

File: `portfolio_judge_prompt.py` :contentReference[oaicite:3]{index=3}  

Used by the Portfolio Judge.

Responsibilities:
- compare all tickers simultaneously  
- rank by conviction  
- assign portfolio weights  

Key design:
- explicitly discourages equal-weight bias  
- enforces relative comparison across assets  
- ensures portfolio-level reasoning (not per-stock)

---

### (4) Risk Prompt

File: `risk_management_prompt.py` :contentReference[oaicite:4]{index=4}  

Used to generate human-readable risk commentary.

Output:
- plain English (not JSON)  
- 3–5 paragraphs  
- highlights key portfolio risks  

Focus:
- cross-position risk themes  
- unusual exposures  
- forward-looking risks  

---

## 3. Design Principles

### Grounded Reasoning

All prompts explicitly enforce:

- "use only provided information"
- "do not invent data"

This reduces hallucination risk.

---

### Structured Outputs

Most prompts require strict JSON output schemas:

- consistent downstream parsing  
- easier debugging  
- reliable pipeline integration  

---

### Role Separation

Each prompt defines a **clear role**:

- analysts → generate signals  
- debate agents → argue  
- judge → decide  
- portfolio → allocate  
- risk → interpret  

This mirrors real-world decision-making workflows.

---

### LLM as Final Layer

The system uses:

- rules → extract features  
- prompts → control reasoning  

This hybrid design balances:
- interpretability  
- flexibility  

---

## 4. Why This Matters

Without this layer:

- agents would behave inconsistently  
- outputs would break downstream pipeline  
- hallucination risk would increase  

With structured prompts:

- behavior is predictable  
- outputs are standardized  
- reasoning is traceable  

---

## 5. How It Fits In The System

```

Data → Features → Prompts → Agents → Debate → Portfolio → Risk

```id="8k2mzn"

- features provide structured inputs  
- prompts define reasoning rules  
- agents execute those rules  
