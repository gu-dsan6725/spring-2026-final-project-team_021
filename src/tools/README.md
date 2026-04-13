# TOOLS

`src/tools` contains utility functions and shared helpers used by agents.

This layer provides reusable building blocks for data access, feature retrieval, and LLM interaction.

---

## 1. What This Layer Does

The tools layer acts as a bridge between:

- features → structured data  
- agents → decision logic  
- LLM → generation  

Instead of embedding logic directly inside agents, common operations are abstracted into reusable tools.

---

## 2. Tool Categories

### (1) Feature Access Tools

Provide simplified access to structured features for agents.

#### Technical Tools

File: `technical_tools.py` :contentReference[oaicite:0]{index=0}  

- wraps technical feature computation  
- returns a clean snapshot with key indicators  

Includes:
- price
- moving averages (SMA)
- RSI
- MACD
- momentum
- volatility  

Used by:
- Technical Analyst

---

#### Fundamental Tools

File: `fundamental_tools.py` :contentReference[oaicite:1]{index=1}  

- wraps fundamental feature extraction  
- returns key financial metrics  

Includes:
- revenue / earnings growth  
- margins  
- ROE / ROA  
- leverage and liquidity  
- cash flow metrics  

Used by:
- Fundamental Analyst

---

### (2) LLM Utilities

File: `llm_client.py` :contentReference[oaicite:2]{index=2}  

Provides a unified interface for calling language models.

Features:
- supports multiple providers (Anthropic, Groq)
- automatic provider selection via environment variables
- retry + rate limit handling
- JSON extraction from model outputs

Key function:
- `call_llm()` → send prompt + messages to model  
- `extract_json_object()` → safely parse structured output  

Used by:
- all LLM-based agents

---

## 3. Design Principles

### Abstraction

Agents do not directly:

- load data  
- compute features  
- call APIs  

Instead, they rely on tools.

---

### Reusability

Common logic is centralized:

- avoids duplication across agents  
- keeps agent code clean and focused  

---

### Separation of Concerns

- features → compute data  
- tools → provide access / wrappers  
- agents → reasoning  

This keeps each layer simple and maintainable.

---

## 4. Why This Layer Exists

Without tools:

- agents would duplicate feature logic  
- LLM calls would be inconsistent  
- debugging would be harder  

With tools:

- code is modular  
- interfaces are standardized  
- system is easier to extend  

---

## 5. How It Fits In The System

```

Data → Features → Tools → Agents → Pipeline

```id="2k1nzo"

- features build structured data  
- tools expose that data  
- agents consume it  
