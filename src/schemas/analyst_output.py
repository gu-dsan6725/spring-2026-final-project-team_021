"""
Shared analyst output schema.

This dataclass-based model keeps the same interface used elsewhere in the
project (`model_dump`, `model_dump_json`) without requiring pydantic.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

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
class AnalystOutput(_SchemaBase):
    agent_name: str
    ticker: str
    analysis_date: str
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: float
    summary: str
    bullish_factors: list[str] = field(default_factory=list)
    bearish_factors: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    key_metrics_used: dict[str, Any] = field(default_factory=dict)
