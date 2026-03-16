"""
Shared Analyst Output Schema

Summary
-------
This module defines the standard output format used by analyst agents.

Purpose
-------
It ensures that all analyst agents return results in a consistent structure,
so downstream components such as Bull, Bear, or Judge agents can consume them
without additional parsing logic.

Used By
-------
- Technical Analyst
- Fundamental Analyst
- Future debate-stage agents
"""

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