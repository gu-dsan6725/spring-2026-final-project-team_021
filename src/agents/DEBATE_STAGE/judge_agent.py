"""
Judge Agent for the debate stage.

The Judge Agent compares the bullish and bearish cases, calibrates a
confidence score from the debate margin, and emits a final trading signal
plus a portfolio weight recommendation.
"""

from __future__ import annotations

import json
from typing import Any

from src.prompts.debate_stage_prompt import JUDGE_SYSTEM_PROMPT
from src.schemas.debate_output import JudgeDecision
from src.tools.llm_client import call_llm, extract_json_object


class JudgeAgent:
    """Select the stronger debate case and size the resulting trade."""

    agent_name = "JudgeAgent"
    _MAX_TEXT_FIELD_LEN = 320
    _MAX_THESIS_LEN = 500

    def __init__(self, max_position_size: float = 0.08, neutral_margin: float = 0.75):
        self.max_position_size = max_position_size
        self.neutral_margin = neutral_margin

    def judge(
        self,
        bull_case: dict[str, Any] | Any,
        bear_case: dict[str, Any] | Any,
        analyst_reports: list[dict[str, Any] | Any] | None = None,
        memory_context: dict[str, Any] | None = None,
    ) -> JudgeDecision:
        bull = self._coerce_case(bull_case)
        bear = self._coerce_case(bear_case)
        reports = [self._coerce_report(report) for report in analyst_reports or []]

        try:
            print(f"[{self.agent_name}] using LLM")
            return self._judge_with_llm(
                bull=bull,
                bear=bear,
                reports=reports,
                memory_context=memory_context,
            )
        except Exception as exc:
            print(f"[{self.agent_name}] using rule fallback ({exc})")
            return self._judge_with_rules(
                bull=bull,
                bear=bear,
                reports=reports,
                memory_context=memory_context,
            )

    def _judge_with_llm(
        self,
        bull: dict[str, Any],
        bear: dict[str, Any],
        reports: list[dict[str, Any]],
        memory_context: dict[str, Any] | None,
    ) -> JudgeDecision:
        ticker, analysis_date = self._resolve_metadata(bull=bull, bear=bear, reports=reports)
        memory_used = self._summarize_memory_usage(memory_context)
        payload = {
            "ticker": ticker,
            "analysis_date": analysis_date,
            "max_position_size": self.max_position_size,
            "neutral_margin": self.neutral_margin,
            "bull_case": self._llm_case_payload(bull),
            "bear_case": self._llm_case_payload(bear),
            "analyst_reports": [self._llm_report_payload(report) for report in reports],
            "memory_context": self._llm_memory_payload(memory_context),
        }
        compact_payload = json.dumps(payload, ensure_ascii=False)
        print(f"[{self.agent_name}] compact LLM payload bytes={len(compact_payload.encode('utf-8'))}")
        raw_output = call_llm(
            messages=[{"role": "user", "content": json.dumps(payload, indent=2, ensure_ascii=False)}],
            system_prompt=JUDGE_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=1400,
        )
        parsed = extract_json_object(raw_output)
        signal = str(parsed.get("signal", "neutral")).lower()
        if signal not in {"bullish", "bearish", "neutral"}:
            signal = "neutral"

        position_size = self._coerce_position_size(parsed.get("position_size", 0.0), signal)
        return JudgeDecision(
            agent_name=self.agent_name,
            ticker=ticker,
            analysis_date=analysis_date,
            signal=signal,
            confidence=self._bounded_confidence(parsed.get("confidence", 0.5)),
            position_size=position_size,
            summary=str(parsed["summary"]),
            rationale=self._clean_text_list(parsed.get("rationale"))[:6],
            dissenting_points=self._clean_text_list(parsed.get("dissenting_points"))[:4],
            risk_flags=sorted(set(self._clean_text_list(parsed.get("risk_flags")))),
            score_breakdown=self._coerce_score_breakdown(parsed.get("score_breakdown")),
            memory_used=memory_used,
        )

    def _judge_with_rules(
        self,
        bull: dict[str, Any],
        bear: dict[str, Any],
        reports: list[dict[str, Any]],
        memory_context: dict[str, Any] | None,
    ) -> JudgeDecision:
        ticker, analysis_date = self._resolve_metadata(bull=bull, bear=bear, reports=reports)
        short_term_memory = self._short_term_memory(memory_context)
        cross_week_memory = self._cross_week_memory(memory_context)

        bull_score = self._extract_argument_score(bull)
        bear_score = self._extract_argument_score(bear)
        margin = bull_score - bear_score

        signal: str
        if abs(margin) < self.neutral_margin:
            signal = "neutral"
        elif margin > 0:
            signal = "bullish"
        else:
            signal = "bearish"

        common_risks = sorted(
            set(self._as_list(bull.get("risk_flags")))
            | set(self._as_list(bear.get("risk_flags")))
            | {
                risk
                for report in reports
                for risk in self._as_list(report.get("risk_flags"))
            }
        )
        recurring_risks = self._as_list(cross_week_memory.get("recurring_risk_flags"))
        for risk in recurring_risks[:3]:
            if risk not in common_risks:
                common_risks.append(risk)
        common_risks = sorted(set(common_risks))

        confidence = self._judge_confidence(
            bull_score=bull_score,
            bear_score=bear_score,
            bull_case=bull,
            bear_case=bear,
            risk_count=len(common_risks),
            memory_context=memory_context,
        )
        position_size = self._position_size(signal=signal, confidence=confidence)

        winning_case = bull if signal == "bullish" else bear if signal == "bearish" else None
        losing_case = bear if signal == "bullish" else bull if signal == "bearish" else None

        rationale = self._build_rationale(
            signal=signal,
            bull=bull,
            bear=bear,
            reports=reports,
            memory_context=memory_context,
        )
        dissenting_points = (
            self._as_list(losing_case.get("supporting_evidence"))[:4] if losing_case else []
        )
        summary = self._build_summary(
            signal=signal,
            ticker=ticker,
            confidence=confidence,
            winning_case=winning_case,
            memory_context=memory_context,
        )

        return JudgeDecision(
            agent_name=self.agent_name,
            ticker=ticker,
            analysis_date=analysis_date,
            signal=signal,
            confidence=confidence,
            position_size=position_size,
            summary=summary,
            rationale=rationale,
            dissenting_points=dissenting_points,
            risk_flags=common_risks,
            score_breakdown={
                "bull_case_score": round(bull_score, 3),
                "bear_case_score": round(bear_score, 3),
                "score_margin": round(margin, 3),
                "bull_case_confidence": round(float(bull.get("confidence", 0.5)), 3),
                "bear_case_confidence": round(float(bear.get("confidence", 0.5)), 3),
                "risk_count": float(len(common_risks)),
                "max_position_size": float(self.max_position_size),
            },
            memory_used=self._summarize_memory_usage(memory_context),
        )

    def _build_rationale(
        self,
        signal: str,
        bull: dict[str, Any],
        bear: dict[str, Any],
        reports: list[dict[str, Any]],
        memory_context: dict[str, Any] | None,
    ) -> list[str]:
        if signal == "neutral":
            rationale = [
                "The bull and bear cases are too close to justify a directional trade."
            ]
            rationale.extend(self._as_list(bull.get("supporting_evidence"))[:2])
            rationale.extend(self._as_list(bear.get("supporting_evidence"))[:2])
            rationale.extend(self._memory_rationale(memory_context, signal)[:1])
            return rationale[:5]

        winning_case = bull if signal == "bullish" else bear
        rationale = self._as_list(winning_case.get("supporting_evidence"))[:4]

        if reports:
            aligned_reports = [
                report.get("agent_name", "UnknownAnalyst")
                for report in reports
                if report.get("signal") == signal
            ]
            if aligned_reports:
                rationale.append(
                    f"Upstream analyst alignment favors {signal}: {', '.join(aligned_reports[:4])}."
                )

        rationale.extend(self._as_list(winning_case.get("rebuttal_points"))[:2])
        rationale.extend(self._memory_rationale(memory_context, signal)[:1])
        return rationale[:6]

    def _build_summary(
        self,
        signal: str,
        ticker: str,
        confidence: float,
        winning_case: dict[str, Any] | None,
        memory_context: dict[str, Any] | None,
    ) -> str:
        history_note = self._history_summary(memory_context, signal)
        if signal == "neutral":
            summary = (
                f"The debate on {ticker} is inconclusive, so the judge returns a neutral "
                f"signal with confidence {confidence:.2f}."
            )
            return f"{summary} {history_note}".strip()

        thesis = str(winning_case.get("thesis", "")).strip() if winning_case else ""
        if thesis:
            summary = (
                f"The judge favors the {signal} case for {ticker} with confidence "
                f"{confidence:.2f}. {thesis}"
            )
            return f"{summary} {history_note}".strip()
        summary = f"The judge favors the {signal} case for {ticker} with confidence {confidence:.2f}."
        return f"{summary} {history_note}".strip()

    def _judge_confidence(
        self,
        bull_score: float,
        bear_score: float,
        bull_case: dict[str, Any],
        bear_case: dict[str, Any],
        risk_count: int,
        memory_context: dict[str, Any] | None,
    ) -> float:
        total = max(abs(bull_score) + abs(bear_score), 1.0)
        margin_ratio = abs(bull_score - bear_score) / total
        base = 0.5 + margin_ratio * 0.35

        case_confidence_bonus = (
            max(float(bull_case.get("confidence", 0.5)), float(bear_case.get("confidence", 0.5)))
            - 0.5
        ) * 0.15
        risk_penalty = min(risk_count, 5) * 0.02
        confidence = base + case_confidence_bonus - risk_penalty

        cross_week = self._cross_week_memory(memory_context)
        signal_history = self._as_list(cross_week.get("signal_history"))[:4]
        non_neutral_history = [item for item in signal_history if item in {"bullish", "bearish"}]
        if non_neutral_history:
            majority_signal = max(
                {"bullish", "bearish"},
                key=lambda candidate: non_neutral_history.count(candidate),
            )
            current_signal = "bullish" if bull_score > bear_score else "bearish"
            if non_neutral_history.count(majority_signal) >= 2 and majority_signal == current_signal:
                confidence += 0.03
            elif non_neutral_history.count(majority_signal) >= 2 and majority_signal != current_signal:
                confidence -= 0.04

        short_term = self._short_term_memory(memory_context)
        round_history = short_term.get("round_history") or []
        if isinstance(round_history, list) and len(round_history) >= 2:
            previous_round = round_history[-2] if len(round_history) >= 2 else {}
            latest_round = round_history[-1]
            if isinstance(previous_round, dict) and isinstance(latest_round, dict):
                if previous_round.get("bull_thesis") == latest_round.get("bull_thesis"):
                    confidence -= 0.02
                if previous_round.get("bear_thesis") == latest_round.get("bear_thesis"):
                    confidence -= 0.02
        return round(min(0.9, max(0.5, confidence)), 2)

    def _position_size(self, signal: str, confidence: float) -> float:
        if signal == "neutral":
            return 0.0

        scaled = self.max_position_size * max(confidence - 0.5, 0.0) / 0.4
        return round(min(self.max_position_size, max(0.0, scaled)), 4)

    @staticmethod
    def _extract_argument_score(case: dict[str, Any]) -> float:
        score_breakdown = case.get("score_breakdown") or {}
        try:
            return float(score_breakdown.get("argument_score", 0.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _as_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        if value is None:
            return []
        return [str(value)]

    @classmethod
    def _clean_text_list(cls, value: Any) -> list[str]:
        return [item.strip() for item in cls._as_list(value) if item.strip()]

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

    def _coerce_position_size(self, value: Any, signal: str) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = 0.0
        if signal == "neutral":
            return 0.0
        return round(min(self.max_position_size, max(0.0, numeric)), 4)

    @staticmethod
    def _bounded_confidence(value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = 0.5
        return round(min(1.0, max(0.0, numeric)), 2)

    @staticmethod
    def _resolve_metadata(
        bull: dict[str, Any],
        bear: dict[str, Any],
        reports: list[dict[str, Any]],
    ) -> tuple[str, str]:
        ticker = str(bull.get("ticker") or bear.get("ticker"))
        candidate_dates = [
            str(bull.get("analysis_date", "")),
            str(bear.get("analysis_date", "")),
            *[str(report.get("analysis_date", "")) for report in reports],
        ]
        analysis_date = max(candidate_dates)
        return ticker, analysis_date

    @classmethod
    def _clip_text(cls, value: Any, limit: int | None = None) -> str:
        text = str(value or "").strip()
        max_len = limit or cls._MAX_TEXT_FIELD_LEN
        if len(text) <= max_len:
            return text
        return f"{text[: max_len - 3].rstrip()}..."

    @classmethod
    def _clip_list(cls, value: Any, limit: int, item_len: int | None = None) -> list[str]:
        return [
            cls._clip_text(item, limit=item_len)
            for item in cls._as_list(value)[:limit]
            if cls._clip_text(item, limit=item_len)
        ]

    @classmethod
    def _llm_case_payload(cls, case: dict[str, Any]) -> dict[str, Any]:
        score_breakdown = cls._coerce_score_breakdown(case.get("score_breakdown"))
        return {
            "agent_name": str(case.get("agent_name", "")),
            "ticker": str(case.get("ticker", "")),
            "analysis_date": str(case.get("analysis_date", "")),
            "stance": str(case.get("stance", "")),
            "thesis": cls._clip_text(case.get("thesis"), limit=cls._MAX_THESIS_LEN),
            "confidence": cls._bounded_confidence(case.get("confidence", 0.5)),
            "supporting_evidence": cls._clip_list(case.get("supporting_evidence"), limit=5),
            "counter_evidence": cls._clip_list(case.get("counter_evidence"), limit=4),
            "rebuttal_points": cls._clip_list(case.get("rebuttal_points"), limit=3),
            "risk_flags": cls._clip_list(case.get("risk_flags"), limit=6, item_len=120),
            "score_breakdown": {
                key: value for key, value in score_breakdown.items() if key in {"argument_score", "aligned_support", "opposing_pressure"}
            },
        }

    @classmethod
    def _llm_report_payload(cls, report: dict[str, Any]) -> dict[str, Any]:
        score_breakdown = cls._coerce_score_breakdown(report.get("score_breakdown"))
        compact: dict[str, Any] = {
            "agent_name": str(report.get("agent_name", "UnknownAnalyst")),
            "analysis_date": str(report.get("analysis_date", "")),
        }
        if report.get("ticker") is not None:
            compact["ticker"] = str(report.get("ticker", ""))
        if report.get("signal") is not None:
            compact["signal"] = str(report.get("signal", ""))
        if report.get("confidence") is not None:
            compact["confidence"] = cls._bounded_confidence(report.get("confidence", 0.5))

        text_fields = (
            "summary",
            "thesis",
            "investment_summary",
            "outlook",
        )
        for field in text_fields:
            if report.get(field):
                compact[field] = cls._clip_text(report.get(field))

        list_fields = (
            "bullish_factors",
            "bearish_factors",
            "key_drivers",
            "supporting_evidence",
            "counter_evidence",
            "risk_flags",
        )
        for field in list_fields:
            clipped = cls._clip_list(report.get(field), limit=4, item_len=220)
            if clipped:
                compact[field] = clipped

        if score_breakdown:
            compact["score_breakdown"] = dict(list(score_breakdown.items())[:6])
        return compact

    @classmethod
    def _llm_memory_payload(cls, memory_context: dict[str, Any] | None) -> dict[str, Any]:
        short_term = cls._short_term_memory(memory_context)
        cross_week = cls._cross_week_memory(memory_context)
        round_history = short_term.get("round_history") or []

        compact_rounds: list[dict[str, Any]] = []
        for item in round_history[-2:]:
            if not isinstance(item, dict):
                continue
            compact_rounds.append(
                {
                    "round": item.get("round"),
                    "bull_thesis": cls._clip_text(item.get("bull_thesis")),
                    "bear_thesis": cls._clip_text(item.get("bear_thesis")),
                    "repeated_bull_points": cls._clip_list(item.get("repeated_bull_points"), limit=2),
                    "repeated_bear_points": cls._clip_list(item.get("repeated_bear_points"), limit=2),
                }
            )

        recent_weeks = []
        for item in (cross_week.get("recent_weeks") or [])[:3]:
            if not isinstance(item, dict):
                continue
            recent_weeks.append(
                {
                    "week_end_date": str(item.get("week_end_date", "")),
                    "judge_signal": str(item.get("judge_signal", "neutral")),
                    "judge_confidence": cls._bounded_confidence(item.get("judge_confidence", 0.5)),
                    "risk_flags": cls._clip_list(item.get("risk_flags"), limit=4, item_len=120),
                    "dissenting_points": cls._clip_list(item.get("dissenting_points"), limit=3),
                }
            )

        return {
            "short_term_memory": {
                "round_history": compact_rounds,
            },
            "cross_week_memory": {
                "signal_history": cls._clip_list(cross_week.get("signal_history"), limit=4, item_len=32),
                "recurring_risk_flags": cls._clip_list(
                    cross_week.get("recurring_risk_flags"),
                    limit=4,
                    item_len=120,
                ),
                "recurring_dissenting_points": cls._clip_list(
                    cross_week.get("recurring_dissenting_points"),
                    limit=4,
                ),
                "recent_weeks": recent_weeks,
            },
        }

    @staticmethod
    def _coerce_case(case: dict[str, Any] | Any) -> dict[str, Any]:
        if hasattr(case, "model_dump"):
            return case.model_dump(mode="json")
        if isinstance(case, dict):
            return case
        raise TypeError("Debate cases must be dictionaries or Pydantic models.")

    @staticmethod
    def _coerce_report(report: dict[str, Any] | Any) -> dict[str, Any]:
        if hasattr(report, "model_dump"):
            return report.model_dump(mode="json")
        if isinstance(report, dict):
            return report
        raise TypeError("Analyst reports must be dictionaries or Pydantic models.")

    @staticmethod
    def _short_term_memory(memory_context: dict[str, Any] | None) -> dict[str, Any]:
        if isinstance(memory_context, dict):
            return dict(memory_context.get("short_term_memory") or {})
        return {}

    @staticmethod
    def _cross_week_memory(memory_context: dict[str, Any] | None) -> dict[str, Any]:
        if isinstance(memory_context, dict):
            return dict(memory_context.get("cross_week_memory") or {})
        return {}

    def _memory_rationale(self, memory_context: dict[str, Any] | None, signal: str) -> list[str]:
        cross_week = self._cross_week_memory(memory_context)
        recurring_risks = self._as_list(cross_week.get("recurring_risk_flags"))
        signal_history = self._as_list(cross_week.get("signal_history"))[:3]
        rationale: list[str] = []
        if recurring_risks:
            rationale.append(
                f"Recent debate memory still tracks recurring risks: {', '.join(recurring_risks[:3])}."
            )
        if signal_history:
            rationale.append(
                f"Recent judge history into this week: {', '.join(signal_history)}; current verdict is {signal}."
            )
        return rationale

    def _history_summary(self, memory_context: dict[str, Any] | None, signal: str) -> str:
        cross_week = self._cross_week_memory(memory_context)
        signal_history = self._as_list(cross_week.get("signal_history"))[:4]
        non_neutral_history = [item for item in signal_history if item in {"bullish", "bearish"}]
        if len(non_neutral_history) < 2 or signal not in {"bullish", "bearish"}:
            return ""
        majority_signal = max(
            {"bullish", "bearish"},
            key=lambda candidate: non_neutral_history.count(candidate),
        )
        if non_neutral_history.count(majority_signal) < 2:
            return ""
        if majority_signal == signal:
            return f"Recent debate memory supports this directional continuity."
        return f"Recent debate memory leaned {majority_signal}, so this looks more like a regime shift."

    @classmethod
    def _summarize_memory_usage(cls, memory_context: dict[str, Any] | None) -> dict[str, Any]:
        short_term = cls._short_term_memory(memory_context)
        cross_week = cls._cross_week_memory(memory_context)
        return {
            "short_term_rounds_seen": float(len(short_term.get("round_history") or [])),
            "cross_week_weeks_seen": float(len(cross_week.get("recent_weeks") or [])),
            "recent_signal_history": cls._as_list(cross_week.get("signal_history"))[:4],
        }
