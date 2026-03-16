"""
Shared Analyst Output Schema

Summary
-------
This module defines the standard JSON-friendly output format used by
the Technical Analyst and Fundamental Analyst.

Purpose
-------
It ensures both analyst agents return results in the same structure so
their outputs can be saved, compared, and later consumed by downstream
agents or evaluation scripts.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class AnalystOutput(BaseModel):
    agent_name: str = Field(..., description="Name of the analyst agent")
    ticker: str = Field(..., description="Stock ticker symbol")
    analysis_date: str = Field(..., description="Analysis date in YYYY-MM-DD format")
    signal: Literal["bullish", "bearish", "neutral"] = Field(..., description="Directional signal")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0 and 1")
    summary: str = Field(..., description="Short natural language summary of the analysis")
    bullish_factors: list[str] = Field(default_factory=list, description="Bullish evidence")
    bearish_factors: list[str] = Field(default_factory=list, description="Bearish evidence")
    risk_flags: list[str] = Field(default_factory=list, description="Risk warnings or caveats")
    key_metrics_used: dict[str, Any] = Field(default_factory=dict, description="Key metrics referenced")