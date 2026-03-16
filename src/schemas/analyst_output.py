from typing import Any
from pydantic import BaseModel


class AnalystOutput(BaseModel):
    agent_name: str
    ticker: str
    signal: str
    confidence: float
    summary: str
    bullish_factors: list[str]
    bearish_factors: list[str]
    risk_flags: list[str]
    key_metrics_used: dict[str, Any]