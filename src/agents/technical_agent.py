import json
from src.tools.technical_tools import get_technical_snapshot
from src.tools.llm_client import call_llm
from src.prompts.technical_prompt import TECHNICAL_SYSTEM_PROMPT

def run_technical_agent(ticker: str, analysis_date: str) -> dict:
    metrics = get_technical_snapshot(ticker, analysis_date)

    user_prompt = f"""
Analyze the following technical snapshot for {ticker} as of {analysis_date}.

Technical snapshot:
{json.dumps(metrics, indent=2)}

Return a JSON object with this structure:
{{
  "agent_name": "TechnicalAnalyst",
  "ticker": "{ticker}",
  "analysis_date": "{analysis_date}",
  "signal": "bullish|bearish|neutral",
  "confidence": 0.0,
  "summary": "short summary",
  "bullish_factors": ["factor 1"],
  "bearish_factors": ["factor 1"],
  "risk_flags": ["flag 1"],
  "key_metrics_used": {{}}
}}
"""

    raw_output = call_llm(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=TECHNICAL_SYSTEM_PROMPT
    )

    return json.loads(raw_output)