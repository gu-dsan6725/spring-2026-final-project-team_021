"""
Rule-based Risk Manager for DebateTrader (Portfolio Judge variant).

Applies portfolio-level constraints to the Portfolio Judge's weekly allocation,
then calls an LLM to generate a plain-English risk commentary based on the
full debate transcript.

Rules (tuned for the 6-stock demo universe):
---------------------------------------------------------------------------
MAX_SINGLE_PCT        = 55.0   No single ticker may exceed 55% of the
                                portfolio.
MAX_SECTOR_PCT        = 55.0   No GICS sector may exceed 55% of the
                                portfolio.
MIN_HOLDINGS          = 3      If the Portfolio Judge allocates fewer than 3
                                non-zero positions, defensive mode activates.
DEFENSIVE_MODE                 Triggered when non-zero holdings < MIN_HOLDINGS.
                                The portfolio switches to equal-weight across
                                all tickers (since cash is not used in this
                                framework).
---------------------------------------------------------------------------

Input format
------------
Reads outputs from run_portfolio_judge.py:
  {
    "week_end_date": "...",
    "tickers": [...],
    "holdings": {
      "AAPL": {"weight_pct": 35.0, "reason": "..."},
      ...
    },
    "total_allocated_pct": 95.0   ← may be < 100 if LLM under-allocated
  }

If total_allocated_pct != 100%, non-zero weights are renormalized to 100%
before any rules are applied.

Redistribution logic
--------------------
When a cap clips a position, the excess weight is redistributed
proportionally among the remaining uncapped positions.  The process
iterates until no cap is violated (handles cases where redistribution
itself triggers a cap).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from src.prompts.risk_management_prompt import RISK_COMMENTARY_SYSTEM_PROMPT
from src.tools.llm_client import call_llm


# ---------------------------------------------------------------------------
# Sector map for the 6-stock demo universe
# ---------------------------------------------------------------------------
SECTOR_MAP: dict[str, str] = {
    "AAPL":  "Technology",
    "AMZN":  "Consumer Discretionary",
    "BRK.B": "Financials",
    "GOOGL": "Communication Services",
    "LLY":   "Health Care",
    "XOM":   "Energy",
}

# ---------------------------------------------------------------------------
# Risk thresholds
# ---------------------------------------------------------------------------
MAX_SINGLE_PCT:   float = 55.0
MAX_SECTOR_PCT:   float = 55.0
MIN_HOLDINGS:     int   = 3
MAX_REDISTRIBUTION_PASSES: int = 10


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

@dataclass
class PositionAdjustment:
    ticker: str
    rule_triggered: str
    original_pct: float
    adjusted_pct: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RiskReport:
    week_end_date: str
    defensive_mode: bool
    rules_triggered: list[str]
    original_allocations: dict[str, float]
    adjusted_allocations: dict[str, float]
    adjustments: list[PositionAdjustment]
    sector_exposures: dict[str, float]
    llm_risk_commentary: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["adjustments"] = [a.to_dict() for a in self.adjustments]
        return d


# ---------------------------------------------------------------------------
# Core risk manager
# ---------------------------------------------------------------------------

class RiskManager:
    """Apply portfolio constraints and generate an LLM risk commentary."""

    def __init__(
        self,
        max_single_pct: float = MAX_SINGLE_PCT,
        max_sector_pct: float = MAX_SECTOR_PCT,
        min_holdings: int = MIN_HOLDINGS,
        sector_map: dict[str, str] | None = None,
    ) -> None:
        self.max_single_pct = max_single_pct
        self.max_sector_pct = max_sector_pct
        self.min_holdings = min_holdings
        self.sector_map = sector_map or SECTOR_MAP

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(
        self,
        judge_report: dict[str, Any],
        transcript: dict[str, Any],
    ) -> RiskReport:
        """
        Apply risk rules to a portfolio judge report and return a RiskReport.

        Parameters
        ----------
        judge_report : dict
            Parsed content of outputs/portfolio_judge/{date}.json.
        transcript : dict
            Parsed content of outputs/debate_stage/transcript/{date}.json.
        """
        week_end_date = str(judge_report.get("week_end_date", ""))
        holdings_raw: dict[str, dict] = judge_report.get("holdings", {})
        tickers: list[str] = judge_report.get("tickers", list(holdings_raw.keys()))

        # Step 1: extract and normalize original allocations
        original_alloc = self._extract_and_normalize(holdings_raw, tickers)

        rules_triggered: list[str] = []
        adjustments: list[PositionAdjustment] = []

        # Step 2: check for defensive mode (< MIN_HOLDINGS non-zero positions)
        nonzero_count = sum(1 for v in original_alloc.values() if v > 0)
        defensive_mode = nonzero_count < self.min_holdings

        if defensive_mode:
            rules_triggered.append(
                f"DEFENSIVE_MODE: Portfolio Judge allocated {nonzero_count} non-zero "
                f"position(s) (minimum {self.min_holdings}); switching to equal-weight "
                f"across all {len(tickers)} tickers."
            )
            adjusted_alloc = self._equal_weight_all(tickers)
            for ticker, orig in original_alloc.items():
                adj = adjusted_alloc.get(ticker, 0.0)
                if abs(orig - adj) > 0.01:
                    adjustments.append(PositionAdjustment(
                        ticker=ticker,
                        rule_triggered="DEFENSIVE_MODE",
                        original_pct=orig,
                        adjusted_pct=adj,
                        reason=(
                            f"Fewer than {self.min_holdings} non-zero positions; "
                            f"portfolio set to equal weight."
                        ),
                    ))
        else:
            adjusted_alloc = dict(original_alloc)

            # Step 3: apply single-position cap
            adjusted_alloc, single_adj = self._apply_single_cap(adjusted_alloc)
            if single_adj:
                rules_triggered.append(
                    f"MAX_SINGLE_PCT ({self.max_single_pct:.0f}%): clipped "
                    f"{', '.join(a.ticker for a in single_adj)}."
                )
                adjustments.extend(single_adj)

            # Step 4: apply sector cap
            adjusted_alloc, sector_adj = self._apply_sector_cap(adjusted_alloc)
            if sector_adj:
                rules_triggered.append(
                    f"MAX_SECTOR_PCT ({self.max_sector_pct:.0f}%): clipped sectors "
                    f"{', '.join(set(self.sector_map.get(a.ticker, '?') for a in sector_adj))}."
                )
                adjustments.extend(sector_adj)

            # Step 5: final renormalization to 100%
            adjusted_alloc = self._renormalize(adjusted_alloc)

        sector_exposures = self._compute_sector_exposures(adjusted_alloc)

        # Step 6: LLM risk commentary
        print("[RiskManager] requesting LLM risk commentary...")
        commentary = self._llm_commentary(
            week_end_date=week_end_date,
            judge_report=judge_report,
            adjusted_alloc=adjusted_alloc,
            rules_triggered=rules_triggered,
            transcript=transcript,
        )

        return RiskReport(
            week_end_date=week_end_date,
            defensive_mode=defensive_mode,
            rules_triggered=rules_triggered,
            original_allocations=original_alloc,
            adjusted_allocations=adjusted_alloc,
            adjustments=adjustments,
            sector_exposures=sector_exposures,
            llm_risk_commentary=commentary,
            parameters={
                "max_single_pct": self.max_single_pct,
                "max_sector_pct": self.max_sector_pct,
                "min_holdings": self.min_holdings,
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_and_normalize(
        self, holdings_raw: dict[str, dict], tickers: list[str]
    ) -> dict[str, float]:
        """
        Extract weight_pct from portfolio judge holdings dict.
        If weights don't sum to 100%, renormalize only the non-zero positions.
        """
        alloc: dict[str, float] = {
            t: max(0.0, float(holdings_raw.get(t, {}).get("weight_pct", 0.0)))
            for t in tickers
        }
        total = sum(alloc.values())
        if total > 0 and abs(total - 100.0) > 0.01:
            nonzero_total = sum(v for v in alloc.values() if v > 0)
            if nonzero_total > 0:
                factor = 100.0 / nonzero_total
                alloc = {
                    t: (round(v * factor, 4) if v > 0 else 0.0)
                    for t, v in alloc.items()
                }
                alloc = self._fix_rounding(alloc, only_nonzero=True)
        return alloc

    def _equal_weight_all(self, tickers: list[str]) -> dict[str, float]:
        n = len(tickers)
        if n == 0:
            return {}
        per = round(100.0 / n, 4)
        alloc = {t: per for t in tickers}
        alloc = self._fix_rounding(alloc)
        return alloc

    def _apply_single_cap(
        self, alloc: dict[str, float]
    ) -> tuple[dict[str, float], list[PositionAdjustment]]:
        adjustments: list[PositionAdjustment] = []
        alloc = dict(alloc)

        for _ in range(MAX_REDISTRIBUTION_PASSES):
            violators = {t: v for t, v in alloc.items() if v > self.max_single_pct}
            if not violators:
                break
            excess = sum(v - self.max_single_pct for v in violators.values())
            for ticker, orig_pct in violators.items():
                adjustments.append(PositionAdjustment(
                    ticker=ticker,
                    rule_triggered="MAX_SINGLE_PCT",
                    original_pct=round(orig_pct, 2),
                    adjusted_pct=self.max_single_pct,
                    reason=(
                        f"Position {orig_pct:.1f}% exceeds single-ticker cap "
                        f"{self.max_single_pct:.0f}%."
                    ),
                ))
                alloc[ticker] = self.max_single_pct

            uncapped = {
                t: v for t, v in alloc.items()
                if v > 0 and v < self.max_single_pct and t not in violators
            }
            if not uncapped:
                break
            alloc = self._redistribute(alloc, uncapped, excess)

        return alloc, adjustments

    def _apply_sector_cap(
        self, alloc: dict[str, float]
    ) -> tuple[dict[str, float], list[PositionAdjustment]]:
        adjustments: list[PositionAdjustment] = []
        alloc = dict(alloc)

        for _ in range(MAX_REDISTRIBUTION_PASSES):
            sector_totals = self._compute_sector_exposures(alloc)
            violating_sectors = {
                s: t for s, t in sector_totals.items() if t > self.max_sector_pct
            }
            if not violating_sectors:
                break

            for sector, sector_total in violating_sectors.items():
                tickers_in_sector = [
                    t for t, v in alloc.items()
                    if self.sector_map.get(t) == sector and v > 0
                ]
                if not tickers_in_sector:
                    continue
                excess = sector_total - self.max_sector_pct
                for ticker in tickers_in_sector:
                    share = alloc[ticker] / sector_total
                    reduction = excess * share
                    orig = alloc[ticker]
                    alloc[ticker] = max(0.0, orig - reduction)
                    if reduction > 0.01:
                        adjustments.append(PositionAdjustment(
                            ticker=ticker,
                            rule_triggered="MAX_SECTOR_PCT",
                            original_pct=round(orig, 2),
                            adjusted_pct=round(alloc[ticker], 2),
                            reason=(
                                f"Sector '{sector}' total {sector_total:.1f}% exceeds "
                                f"cap {self.max_sector_pct:.0f}%; position trimmed."
                            ),
                        ))

                uncapped_other = {
                    t: v for t, v in alloc.items()
                    if self.sector_map.get(t) != sector
                }
                alloc = self._redistribute(alloc, uncapped_other, excess)

        return alloc, adjustments

    @staticmethod
    def _redistribute(
        alloc: dict[str, float],
        targets: dict[str, float],
        excess: float,
    ) -> dict[str, float]:
        """Add `excess` to `targets`, proportional to their current weights."""
        alloc = dict(alloc)
        total_target = sum(targets.values())
        if total_target <= 0:
            n = len(targets)
            if n:
                per = excess / n
                for t in targets:
                    alloc[t] = alloc.get(t, 0.0) + per
        else:
            for t, v in targets.items():
                alloc[t] = alloc.get(t, 0.0) + excess * (v / total_target)
        return alloc

    def _compute_sector_exposures(self, alloc: dict[str, float]) -> dict[str, float]:
        exposures: dict[str, float] = {}
        for ticker, pct in alloc.items():
            sector = self.sector_map.get(ticker, "Unknown")
            exposures[sector] = round(exposures.get(sector, 0.0) + pct, 4)
        return exposures

    @staticmethod
    def _renormalize(alloc: dict[str, float]) -> dict[str, float]:
        total = sum(alloc.values())
        if total <= 0:
            return alloc
        factor = 100.0 / total
        normalized = {t: round(v * factor, 4) for t, v in alloc.items()}
        return RiskManager._fix_rounding(normalized, only_nonzero=True)

    @staticmethod
    def _fix_rounding(
        alloc: dict[str, float], only_nonzero: bool = False
    ) -> dict[str, float]:
        """Adjust the largest non-zero position so weights sum to exactly 100."""
        total = sum(alloc.values())
        diff = round(100.0 - total, 4)
        if abs(diff) < 1e-6:
            return alloc
        candidates = {t: v for t, v in alloc.items() if v > 0} if only_nonzero else alloc
        if not candidates:
            return alloc
        top = max(candidates, key=candidates.get)
        alloc = dict(alloc)
        alloc[top] = round(alloc[top] + diff, 4)
        return alloc

    # ------------------------------------------------------------------
    # LLM commentary
    # ------------------------------------------------------------------

    def _llm_commentary(
        self,
        week_end_date: str,
        judge_report: dict[str, Any],
        adjusted_alloc: dict[str, float],
        rules_triggered: list[str],
        transcript: dict[str, Any],
    ) -> str:
        condensed_judge = self._condense_judge_for_llm(judge_report, adjusted_alloc)
        condensed_transcript = self._condense_transcript_for_llm(transcript)

        payload = {
            "week_end_date": week_end_date,
            "risk_parameters": {
                "max_single_pct": self.max_single_pct,
                "max_sector_pct": self.max_sector_pct,
                "min_holdings": self.min_holdings,
            },
            "rules_triggered": rules_triggered,
            "adjusted_portfolio": adjusted_alloc,
            "sector_exposures": self._compute_sector_exposures(adjusted_alloc),
            "judge_summary": condensed_judge,
            "debate_highlights": condensed_transcript,
        }

        try:
            commentary = call_llm(
                messages=[
                    {
                        "role": "user",
                        "content": json.dumps(payload, indent=2, ensure_ascii=False),
                    }
                ],
                system_prompt=RISK_COMMENTARY_SYSTEM_PROMPT,
                temperature=0.3,
                max_tokens=600,
            )
            return commentary
        except Exception as exc:
            return (
                f"[LLM commentary unavailable: {exc}] "
                f"Rules triggered: {'; '.join(rules_triggered) if rules_triggered else 'none'}. "
                f"Adjusted portfolio: "
                + ", ".join(f"{t} {v:.1f}%" for t, v in adjusted_alloc.items() if v > 0)
                + "."
            )

    @staticmethod
    def _condense_judge_for_llm(
        judge_report: dict[str, Any], adjusted_alloc: dict[str, float]
    ) -> list[dict]:
        holdings: dict[str, dict] = judge_report.get("holdings", {})
        result = []
        for ticker, data in holdings.items():
            result.append({
                "ticker": ticker,
                "portfolio_judge_weight_pct": data.get("weight_pct"),
                "adjusted_position_pct": adjusted_alloc.get(ticker, 0.0),
                "reason": data.get("reason", ""),
            })
        return result

    @staticmethod
    def _condense_transcript_for_llm(transcript: dict[str, Any]) -> list[dict]:
        highlights = []
        for entry in transcript.get("per_ticker_transcript", []):
            ticker = str(entry.get("ticker", ""))
            bull_final = entry.get("bull_final") or {}
            bear_final = entry.get("bear_final") or {}
            judge_dec = entry.get("judge_decision") or {}
            highlights.append({
                "ticker": ticker,
                "bull_thesis": bull_final.get("thesis", ""),
                "bull_confidence": bull_final.get("confidence"),
                "bear_thesis": bear_final.get("thesis", ""),
                "bear_confidence": bear_final.get("confidence"),
                "judge_signal": judge_dec.get("signal"),
                "judge_confidence": judge_dec.get("confidence"),
                "judge_risk_flags": judge_dec.get("risk_flags", []),
                "judge_dissenting": judge_dec.get("dissenting_points", [])[:2],
            })
        return highlights
