"""
Bear Agent for the debate stage.

The Bear Agent consumes upstream analyst reports and builds a bearish
investment case. It can also produce rebuttal points when a Bull case is
available.
"""

from __future__ import annotations

import json
from typing import Any

from src.prompts.debate_stage_prompt import BEAR_SYSTEM_PROMPT
from src.schemas.debate_output import DebateCase
from src.tools.llm_client import call_llm, extract_json_object


class BearAgent:
    """Construct a bearish case from analyst reports."""

    agent_name = "BearAgent"
    stance = "bearish"

    def build_case(
        self,
        analyst_reports: list[dict[str, Any] | Any],
        opponent_case: dict[str, Any] | Any | None = None,
    ) -> DebateCase:
        reports = [self._coerce_report(report) for report in analyst_reports]
        if not reports:
            raise ValueError("BearAgent requires at least one analyst report.")

        try:
            print(f"[{self.agent_name}] using LLM")
            return self._build_case_with_llm(
                analyst_reports=reports,
                opponent_case=opponent_case,
            )
        except Exception as exc:
            print(f"[{self.agent_name}] using rule fallback ({exc})")
            return self._build_case_with_rules(
                analyst_reports=reports,
                opponent_case=opponent_case,
            )

    def _build_case_with_llm(
        self,
        analyst_reports: list[dict[str, Any]],
        opponent_case: dict[str, Any] | Any | None,
    ) -> DebateCase:
        ticker, analysis_date = self._resolve_metadata(analyst_reports)

        payload = {
            "ticker": ticker,
            "analysis_date": analysis_date,
            "stance": self.stance,
            "analyst_reports": analyst_reports,
            "opponent_case": self._coerce_case(opponent_case) if opponent_case is not None else None,
        }
        raw_output = call_llm(
            messages=[{"role": "user", "content": json.dumps(payload, indent=2, ensure_ascii=False)}],
            system_prompt=BEAR_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=1200,
        )
        parsed = extract_json_object(raw_output)
        return DebateCase(
            agent_name=self.agent_name,
            ticker=ticker,
            analysis_date=analysis_date,
            stance=self.stance,
            thesis=str(parsed["thesis"]),
            confidence=self._bounded_confidence(parsed.get("confidence", 0.5)),
            supporting_evidence=self._clean_text_list(parsed.get("supporting_evidence"))[:8],
            counter_evidence=self._clean_text_list(parsed.get("counter_evidence"))[:6],
            rebuttal_points=self._clean_text_list(parsed.get("rebuttal_points"))[:4],
            risk_flags=sorted(set(self._clean_text_list(parsed.get("risk_flags")))),
            score_breakdown=self._coerce_score_breakdown(parsed.get("score_breakdown")),
        )

    def _build_case_with_rules(
        self,
        analyst_reports: list[dict[str, Any]],
        opponent_case: dict[str, Any] | Any | None,
    ) -> DebateCase:
        reports = analyst_reports
        ticker, analysis_date = self._resolve_metadata(reports)

        supporting_evidence: list[str] = []
        counter_evidence: list[str] = []
        risk_flags: list[str] = []
        score_breakdown: dict[str, float] = {}

        aligned_support = 0.0
        opposing_pressure = 0.0

        for report in reports:
            report_name = str(report.get("agent_name", "UnknownAnalyst"))
            confidence = self._bounded_confidence(report.get("confidence", 0.5))
            signal = str(report.get("signal", "neutral"))

            bullish_factors = self._as_list(report.get("bullish_factors"))
            bearish_factors = self._as_list(report.get("bearish_factors"))
            report_risks = self._as_list(report.get("risk_flags"))

            signal_bonus = 1.0 if signal == "bearish" else 0.25 if signal == "neutral" else -1.0
            support_score = (
                len(bearish_factors) * 0.8 + max(signal_bonus, 0.0)
            ) * confidence
            counter_score = (
                len(bullish_factors) * 0.7
                + max(-signal_bonus, 0.0)
                + len(report_risks) * 0.15
            ) * confidence
            net_score = round(support_score - counter_score, 3)

            score_breakdown[report_name] = net_score
            aligned_support += support_score
            opposing_pressure += counter_score

            supporting_evidence.extend(
                f"[{report_name}] {factor}" for factor in bearish_factors
            )
            if report_risks:
                supporting_evidence.extend(
                    f"[{report_name}] Risk flag: {risk}" for risk in report_risks
                )
            counter_evidence.extend(
                f"[{report_name}] {factor}" for factor in bullish_factors
            )
            if signal == "bearish":
                supporting_evidence.append(
                    f"[{report_name}] Directional signal is bearish with confidence {confidence:.2f}."
                )
            elif signal == "bullish":
                counter_evidence.append(
                    f"[{report_name}] Directional signal is bullish with confidence {confidence:.2f}."
                )

            risk_flags.extend(report_risks)

        rebuttal_points = self._build_rebuttal_points(
            opponent_case=opponent_case,
            supporting_evidence=supporting_evidence,
            counter_evidence=counter_evidence,
        )

        argument_score = round(
            aligned_support - opposing_pressure + len(rebuttal_points) * 0.2,
            3,
        )
        score_breakdown["argument_score"] = argument_score
        score_breakdown["aligned_support"] = round(aligned_support, 3)
        score_breakdown["opposing_pressure"] = round(opposing_pressure, 3)

        confidence = self._case_confidence(
            aligned_support=aligned_support,
            opposing_pressure=opposing_pressure,
            rebuttal_count=len(rebuttal_points),
        )

        unique_support = self._unique_preserve_order(supporting_evidence)[:8]
        unique_counter = self._unique_preserve_order(counter_evidence)[:6]
        unique_risks = sorted(set(risk_flags))

        thesis = self._compose_thesis(
            ticker=ticker,
            supporting_evidence=unique_support,
            counter_evidence=unique_counter,
        )

        return DebateCase(
            agent_name=self.agent_name,
            ticker=ticker,
            analysis_date=analysis_date,
            stance=self.stance,
            thesis=thesis,
            confidence=confidence,
            supporting_evidence=unique_support,
            counter_evidence=unique_counter,
            rebuttal_points=rebuttal_points,
            risk_flags=unique_risks,
            score_breakdown=score_breakdown,
        )

    def rebut(
        self,
        analyst_reports: list[dict[str, Any] | Any],
        bull_case: dict[str, Any] | Any,
    ) -> DebateCase:
        """Build a bearish case that explicitly rebuts the bull case."""

        return self.build_case(analyst_reports=analyst_reports, opponent_case=bull_case)

    def _build_rebuttal_points(
        self,
        opponent_case: dict[str, Any] | Any | None,
        supporting_evidence: list[str],
        counter_evidence: list[str],
    ) -> list[str]:
        if opponent_case is None:
            return []

        opponent = self._coerce_case(opponent_case)
        opponent_claims = self._as_list(opponent.get("supporting_evidence"))[:3]
        rebuttals: list[str] = []

        if not opponent_claims:
            return rebuttals

        fallback_support = supporting_evidence or [
            "multiple analyst reports still contain unresolved downside evidence"
        ]
        fallback_counter = counter_evidence or [
            "upside evidence exists, but it is not dominant across the analyst set"
        ]

        for idx, claim in enumerate(opponent_claims):
            support_anchor = fallback_support[idx % len(fallback_support)]
            caveat_anchor = fallback_counter[idx % len(fallback_counter)]
            rebuttals.append(
                f"The bullish claim '{claim}' is less convincing because {support_anchor} "
                f"and the upside thesis still relies on overcoming {caveat_anchor}."
            )

        return rebuttals

    def _compose_thesis(
        self,
        ticker: str,
        supporting_evidence: list[str],
        counter_evidence: list[str],
    ) -> str:
        lead = supporting_evidence[0] if supporting_evidence else "upstream analysts"
        if counter_evidence:
            return (
                f"{ticker} has a credible downside case because {lead} "
                f"and the bullish evidence does not fully neutralize the risks."
            )
        return f"{ticker} has a credible downside case because {lead}."

    @staticmethod
    def _case_confidence(
        aligned_support: float,
        opposing_pressure: float,
        rebuttal_count: int,
    ) -> float:
        total = max(aligned_support + opposing_pressure, 1.0)
        edge = (aligned_support - opposing_pressure) / total
        confidence = 0.5 + max(edge, 0.0) * 0.3 + min(rebuttal_count, 3) * 0.03
        return round(min(0.9, max(0.35, confidence)), 2)

    @staticmethod
    def _bounded_confidence(value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = 0.5
        return min(1.0, max(0.0, numeric))

    @staticmethod
    def _as_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        if value is None:
            return []
        return [str(value)]

    @classmethod
    def _clean_text_list(cls, value: Any) -> list[str]:
        return cls._unique_preserve_order([item.strip() for item in cls._as_list(value) if item.strip()])

    @staticmethod
    def _coerce_score_breakdown(value: Any) -> dict[str, float]:
        if not isinstance(value, dict):
            return {}
        coerced: dict[str, float] = {}
        for key, raw in value.items():
            try:
                coerced[str(key)] = float(raw)
            except (TypeError, ValueError):
                continue
        return coerced

    @staticmethod
    def _resolve_metadata(reports: list[dict[str, Any]]) -> tuple[str, str]:
        ticker = str(reports[0]["ticker"])
        analysis_date = max(str(report.get("analysis_date", "")) for report in reports)
        return ticker, analysis_date

    @staticmethod
    def _unique_preserve_order(items: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered

    @staticmethod
    def _coerce_report(report: dict[str, Any] | Any) -> dict[str, Any]:
        if hasattr(report, "model_dump"):
            return report.model_dump(mode="json")
        if isinstance(report, dict):
            return report
        raise TypeError("Analyst reports must be dictionaries or Pydantic models.")

    @staticmethod
    def _coerce_case(case: dict[str, Any] | Any) -> dict[str, Any]:
        if hasattr(case, "model_dump"):
            return case.model_dump(mode="json")
        if isinstance(case, dict):
            return case
        raise TypeError("Debate cases must be dictionaries or Pydantic models.")
