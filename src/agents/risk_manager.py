"""
Rule-based Risk Manager for DebateTrader.

Applies portfolio-level constraints to the Judge Agent's weekly allocation,
then calls an LLM to generate a plain-English risk commentary based on the
full debate transcript.

Rules (tuned for the 6-stock demo universe):
---------------------------------------------------------------------------
CONFIDENCE_FLOOR      = 0.55   Exclude bullish positions where Judge
                                confidence < 0.55 (signal too weak).
MAX_SINGLE_PCT        = 30.0   No single ticker may exceed 30% of the
                                portfolio.
MAX_SECTOR_PCT        = 40.0   No GICS sector may exceed 40% of the
                                portfolio.
MIN_HOLDINGS          = 3      At least 3 tickers must pass the confidence
                                floor to deploy directionally.  If fewer
                                than 3 pass, defensive mode activates.
                                Rationale: with only 1-2 bullish names the
                                single-position cap (40%) cannot be enforced
                                (no spare positions to absorb excess weight),
                                so the whole-portfolio signal is treated as
                                too weak to act on directionally.
DEFENSIVE_MODE                 Triggered when < MIN_HOLDINGS tickers pass
                                the confidence floor.  The portfolio
                                switches to equal-weight across all tickers
                                (since cash is not used in this framework).
---------------------------------------------------------------------------

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
CONFIDENCE_FLOOR: float = 0.55
MAX_SINGLE_PCT:   float = 40.0   # 6-stock universe: 2 bullish → 50% each → cap fires;
                                  # 3+ bullish → ≤33% each → cap never fires
MAX_SECTOR_PCT:   float = 40.0
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
        confidence_floor: float = CONFIDENCE_FLOOR,
        max_single_pct: float = MAX_SINGLE_PCT,
        max_sector_pct: float = MAX_SECTOR_PCT,
        min_holdings: int = MIN_HOLDINGS,
        sector_map: dict[str, str] | None = None,
    ) -> None:
        self.confidence_floor = confidence_floor
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
        Apply risk rules to a judge report and return a RiskReport.

        Parameters
        ----------
        judge_report : dict
            Parsed content of outputs/debate_stage/judge/{date}.json.
        transcript : dict
            Parsed content of outputs/debate_stage/transcript/{date}.json.
        """
        week_end_date = str(judge_report.get("week_end_date", ""))
        holdings = judge_report.get("holdings", [])

        # Step 1: extract original bullish allocations
        original_alloc = self._extract_original_allocations(holdings)

        # Step 2: build candidate pool (pass confidence floor)
        candidates, excluded_by_confidence = self._filter_by_confidence(holdings)

        rules_triggered: list[str] = []
        adjustments: list[PositionAdjustment] = []

        # Step 3: check for defensive mode
        defensive_mode = len(candidates) < self.min_holdings
        if defensive_mode:
            rules_triggered.append(
                f"DEFENSIVE_MODE: only {len(candidates)} ticker(s) passed confidence "
                f"floor {self.confidence_floor:.2f}; switching to equal-weight across "
                f"all {len(holdings)} tickers."
            )
            adjusted_alloc = self._equal_weight_all(holdings)
            for ticker, orig in original_alloc.items():
                adj = adjusted_alloc.get(ticker, 0.0)
                if abs(orig - adj) > 0.01:
                    adjustments.append(PositionAdjustment(
                        ticker=ticker,
                        rule_triggered="DEFENSIVE_MODE",
                        original_pct=orig,
                        adjusted_pct=adj,
                        reason=(
                            f"Fewer than {self.min_holdings} tickers passed the confidence "
                            f"floor; portfolio set to equal weight."
                        ),
                    ))
        else:
            if excluded_by_confidence:
                rules_triggered.append(
                    f"CONFIDENCE_FLOOR ({self.confidence_floor:.2f}): excluded "
                    f"{', '.join(excluded_by_confidence)}."
                )
                for ticker in excluded_by_confidence:
                    orig = original_alloc.get(ticker, 0.0)
                    if orig > 0:
                        adjustments.append(PositionAdjustment(
                            ticker=ticker,
                            rule_triggered="CONFIDENCE_FLOOR",
                            original_pct=orig,
                            adjusted_pct=0.0,
                            reason=(
                                f"Judge confidence below threshold "
                                f"{self.confidence_floor:.2f}."
                            ),
                        ))

            # Step 4: start from Judge's original allocations (excluding filtered tickers)
            adjusted_alloc = self._judge_allocations_with_exclusions(candidates, holdings)

            # Step 5: apply single-position cap
            adjusted_alloc, single_adj = self._apply_single_cap(adjusted_alloc)
            if single_adj:
                rules_triggered.append(
                    f"MAX_SINGLE_PCT ({self.max_single_pct:.0f}%): clipped "
                    f"{', '.join(a.ticker for a in single_adj)}."
                )
                adjustments.extend(single_adj)

            # Step 6: apply sector cap
            adjusted_alloc, sector_adj = self._apply_sector_cap(adjusted_alloc)
            if sector_adj:
                rules_triggered.append(
                    f"MAX_SECTOR_PCT ({self.max_sector_pct:.0f}%): clipped sectors "
                    f"{', '.join(set(self.sector_map.get(a.ticker, '?') for a in sector_adj))}."
                )
                adjustments.extend(sector_adj)

            # Step 7: final renormalization to 100%
            adjusted_alloc = self._renormalize(adjusted_alloc)

        sector_exposures = self._compute_sector_exposures(adjusted_alloc)

        # Step 8: LLM risk commentary
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
                "confidence_floor": self.confidence_floor,
                "max_single_pct": self.max_single_pct,
                "max_sector_pct": self.max_sector_pct,
                "min_holdings": self.min_holdings,
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_original_allocations(self, holdings: list[dict]) -> dict[str, float]:
        return {
            str(h["ticker"]): float(h.get("suggested_position_pct", 0.0))
            for h in holdings
        }

    def _filter_by_confidence(
        self, holdings: list[dict]
    ) -> tuple[list[dict], list[str]]:
        """Return (passing_holdings, excluded_tickers)."""
        passing, excluded = [], []
        for h in holdings:
            signal = str(h.get("signal", "neutral"))
            confidence = float(h.get("confidence", 0.0))
            if signal == "bullish" and confidence >= self.confidence_floor:
                passing.append(h)
            elif signal == "bullish" and confidence < self.confidence_floor:
                excluded.append(str(h["ticker"]))
        return passing, excluded

    def _equal_weight_all(self, holdings: list[dict]) -> dict[str, float]:
        n = len(holdings)
        if n == 0:
            return {}
        per = round(100.0 / n, 4)
        alloc = {str(h["ticker"]): per for h in holdings}
        alloc = self._fix_rounding(alloc)
        return alloc

    def _judge_allocations_with_exclusions(
        self, candidates: list[dict], all_holdings: list[dict]
    ) -> dict[str, float]:
        """
        Start from the Judge's original suggested_position_pct.
        Tickers excluded by the confidence floor are zeroed out; their
        weight is redistributed proportionally among the remaining
        candidates.
        """
        candidate_tickers = {str(h["ticker"]) for h in candidates}
        alloc: dict[str, float] = {}
        for h in all_holdings:
            ticker = str(h["ticker"])
            alloc[ticker] = (
                float(h.get("suggested_position_pct", 0.0))
                if ticker in candidate_tickers
                else 0.0
            )
        # Renormalize so excluded weight is spread across remaining positions
        alloc = self._renormalize(alloc)
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

            # Only redistribute to currently held (positive-weight) uncapped positions.
            # If all positions are capped (e.g. only 3 holdings with a 30% cap),
            # skip redistribution and let _renormalize restore proportional weights.
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
                # Reduce each ticker in this sector proportionally
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
            # Spread equally if no weight to anchor on
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
                "confidence_floor": self.confidence_floor,
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
        result = []
        for h in judge_report.get("holdings", []):
            ticker = str(h["ticker"])
            result.append({
                "ticker": ticker,
                "signal": h.get("signal"),
                "confidence": h.get("confidence"),
                "judge_position_pct": h.get("suggested_position_pct"),
                "adjusted_position_pct": adjusted_alloc.get(ticker, 0.0),
                "summary": h.get("summary"),
                "risk_flags": h.get("risk_flags", []),
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
