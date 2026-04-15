"""
Shared schemas for the debate stage.

These dataclass-based models avoid a hard dependency on pydantic at runtime,
which keeps the project runnable in older or inconsistent local environments.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

try:
    from typing import Literal
except ImportError:  # pragma: no cover - Python < 3.8 compatibility
    from typing_extensions import Literal


class _SchemaBase:
    """Small compatibility layer matching the subset of pydantic APIs in use."""

    def model_dump(self, mode: str | None = None) -> dict:
        _ = mode
        return asdict(self)

    def model_dump_json(self, indent: int | None = None) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            indent=indent,
            ensure_ascii=False,
            default=str,
        )


@dataclass
class DebateCase(_SchemaBase):
    agent_name: str
    ticker: str
    analysis_date: str
    stance: Literal["bullish", "bearish"]
    thesis: str
    confidence: float
    supporting_evidence: list[str] = field(default_factory=list)
    counter_evidence: list[str] = field(default_factory=list)
    rebuttal_points: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    score_breakdown: dict[str, float] = field(default_factory=dict)
    memory_used: dict = field(default_factory=dict)


@dataclass
class JudgeDecision(_SchemaBase):
    agent_name: str
    ticker: str
    analysis_date: str
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: float
    position_size: float
    summary: str
    rationale: list[str] = field(default_factory=list)
    dissenting_points: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    score_breakdown: dict[str, float] = field(default_factory=dict)
    memory_used: dict = field(default_factory=dict)


@dataclass
class WeeklyDebateView(_SchemaBase):
    ticker: str
    input_data_date: str
    supports_stance: bool
    confidence: float
    thesis: str
    reasons: list[str] = field(default_factory=list)
    counterpoints: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    source_report_dates: dict[str, str] = field(default_factory=dict)
    score_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass
class WeeklyDebateReport(_SchemaBase):
    agent_name: str
    week_end_date: str
    input_data_date: str
    stance: Literal["bullish", "bearish"]
    tickers: list[str] = field(default_factory=list)
    company_views: list[WeeklyDebateView] = field(default_factory=list)


@dataclass
class WeeklyPortfolioAllocation(_SchemaBase):
    ticker: str
    input_data_date: str
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: float
    suggested_position_pct: float
    summary: str
    rationale: list[str] = field(default_factory=list)
    dissenting_points: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    source_report_dates: dict[str, str] = field(default_factory=dict)
    score_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass
class WeeklyJudgeReport(_SchemaBase):
    agent_name: str
    week_end_date: str
    input_data_date: str
    tickers: list[str] = field(default_factory=list)
    portfolio_summary: str = ""
    allocation_method: str = ""
    holdings: list[WeeklyPortfolioAllocation] = field(default_factory=list)
    bullish_tickers: list[str] = field(default_factory=list)
    bearish_tickers: list[str] = field(default_factory=list)
    neutral_tickers: list[str] = field(default_factory=list)
    total_allocated_pct: float = 0.0
    cash_pct: float = 0.0
