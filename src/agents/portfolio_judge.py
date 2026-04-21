"""
Portfolio Judge Agent for DebateTrader.

Unlike the per-stock JudgeAgent (which evaluates each ticker in isolation),
the PortfolioJudge receives the full debate transcripts for all tickers
simultaneously and constructs a portfolio allocation through cross-ticker
comparison, forcing relative ranking and conviction-weighted sizing.
"""

from __future__ import annotations

import json
import time
from typing import Any

from src.prompts.portfolio_judge_prompt import PORTFOLIO_JUDGE_SYSTEM_PROMPT
from src.tools.llm_client import call_llm, extract_json_object

_RATE_LIMIT_RETRY_WAIT = 65   # seconds to wait after a 429 before retrying
_MAX_RETRIES = 3


class PortfolioJudge:
    """
    Constructs a weekly portfolio by comparing all tickers' full debate
    transcripts in a single LLM call.
    """

    agent_name = "PortfolioJudge"

    def allocate(self, per_ticker_transcripts: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Parameters
        ----------
        per_ticker_transcripts : list[dict]
            The `per_ticker_transcript` list directly from the transcript JSON.
            Each entry contains: ticker, analyst_reports, bull_round_1,
            bear_round_1, bull_final, bear_final, judge_decision,
            source_report_dates.

        Returns
        -------
        dict with keys:
            ranking             : list[str]  — tickers highest to lowest conviction
            portfolio_rationale : str
            holdings            : dict[str, dict]  — {ticker: {weight_pct, reason}}
        """
        if not per_ticker_transcripts:
            raise ValueError("PortfolioJudge requires at least one ticker transcript.")

        tickers = [str(e["ticker"]) for e in per_ticker_transcripts]

        try:
            print(f"[{self.agent_name}] calling LLM ({len(tickers)} tickers)")
            result = self._allocate_with_llm(per_ticker_transcripts, tickers)
        except Exception as exc:
            print(f"[{self.agent_name}] LLM failed ({exc}), using rule fallback")
            result = self._allocate_fallback(per_ticker_transcripts, tickers)

        return result

    # ------------------------------------------------------------------
    # LLM path
    # ------------------------------------------------------------------

    def _allocate_with_llm(
        self,
        per_ticker_transcripts: list[dict[str, Any]],
        tickers: list[str],
    ) -> dict[str, Any]:
        payload = {
            "tickers": tickers,
            "per_ticker_transcripts": per_ticker_transcripts,
        }
        messages = [
            {
                "role": "user",
                "content": json.dumps(payload, indent=2, ensure_ascii=False),
            }
        ]

        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                raw = call_llm(
                    messages=messages,
                    system_prompt=PORTFOLIO_JUDGE_SYSTEM_PROMPT,
                    provider="anthropic",
                    model="claude-sonnet-4-6",
                    temperature=0.2,
                    max_tokens=1400,
                )
                parsed = extract_json_object(raw)
                return self._validate(parsed, tickers)
            except Exception as exc:
                last_exc = exc
                if "429" in str(exc) or "rate_limit" in str(exc).lower():
                    print(
                        f"[{self.agent_name}] rate limit hit "
                        f"(attempt {attempt}/{_MAX_RETRIES}), "
                        f"waiting {_RATE_LIMIT_RETRY_WAIT}s ..."
                    )
                    time.sleep(_RATE_LIMIT_RETRY_WAIT)
                else:
                    raise

        raise RuntimeError(
            f"[{self.agent_name}] LLM failed after {_MAX_RETRIES} retries"
        ) from last_exc

    def _validate(self, parsed: dict[str, Any], tickers: list[str]) -> dict[str, Any]:
        holdings: dict[str, Any] = parsed.get("holdings", {})

        # Ensure every ticker is present
        for t in tickers:
            if t not in holdings:
                holdings[t] = {"weight_pct": 0.0, "reason": "Not allocated by Portfolio Judge."}

        # Coerce weight_pct to non-negative float
        for t in tickers:
            entry = holdings[t]
            try:
                entry["weight_pct"] = max(0.0, float(entry.get("weight_pct", 0.0)))
            except (TypeError, ValueError):
                entry["weight_pct"] = 0.0
            entry["reason"] = str(entry.get("reason", ""))

        # Cap total at 100% — scale down if LLM overallocated
        total = sum(holdings[t]["weight_pct"] for t in tickers)
        if total > 100.0:
            factor = 100.0 / total
            for t in tickers:
                holdings[t]["weight_pct"] = round(holdings[t]["weight_pct"] * factor, 2)
            self._fix_rounding(holdings, tickers)

        # Validate ranking — fill gaps if LLM omitted some tickers
        raw_ranking: list[str] = [
            str(t) for t in parsed.get("ranking", []) if str(t) in tickers
        ]
        missing = [t for t in tickers if t not in raw_ranking]
        ranking = raw_ranking + missing

        return {
            "ranking": ranking,
            "portfolio_rationale": str(parsed.get("portfolio_rationale", "")),
            "holdings": holdings,
        }

    # ------------------------------------------------------------------
    # Rule-based fallback
    # ------------------------------------------------------------------

    def _allocate_fallback(
        self,
        per_ticker_transcripts: list[dict[str, Any]],
        tickers: list[str],
    ) -> dict[str, Any]:
        """
        Confidence-weighted allocation among bullish tickers only.
        Used when the LLM call fails entirely.
        """
        bullish_conf: dict[str, float] = {}
        for entry in per_ticker_transcripts:
            ticker = str(entry.get("ticker", ""))
            judge = entry.get("judge_decision") or {}
            if str(judge.get("signal", "neutral")) == "bullish":
                conf = max(0.0, float(judge.get("confidence", 0.5)))
                bullish_conf[ticker] = conf

        total_conf = sum(bullish_conf.values())
        holdings: dict[str, dict] = {}
        for t in tickers:
            if t in bullish_conf and total_conf > 0:
                w = round(bullish_conf[t] / total_conf * 100.0, 2)
            else:
                w = 0.0
            holdings[t] = {
                "weight_pct": w,
                "reason": "Fallback: confidence-weighted bullish allocation.",
            }

        ranking = (
            sorted(bullish_conf, key=bullish_conf.get, reverse=True)  # type: ignore[arg-type]
            + [t for t in tickers if t not in bullish_conf]
        )

        return {
            "ranking": ranking,
            "portfolio_rationale": (
                "LLM unavailable. Fallback: weights proportional to per-stock "
                "judge confidence among bullish tickers."
            ),
            "holdings": holdings,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fix_rounding(holdings: dict[str, dict], tickers: list[str]) -> None:
        """Adjust the largest non-zero position so weights sum to exactly 100."""
        total = sum(holdings[t]["weight_pct"] for t in tickers)
        diff = round(100.0 - total, 4)
        if abs(diff) < 1e-4:
            return
        positive = [t for t in tickers if holdings[t]["weight_pct"] > 0]
        if not positive:
            return
        top = max(positive, key=lambda t: holdings[t]["weight_pct"])
        holdings[top]["weight_pct"] = round(holdings[top]["weight_pct"] + diff, 2)