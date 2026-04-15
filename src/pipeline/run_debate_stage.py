"""
Run the debate stage as a weekly batch process.

Summary
-------
Each Sunday, the debate stage reads the analyst reports dated to that same
Sunday. The weekly technical and news/trends reports already summarize the
prior week, so the debate stage should not shift them back by another week.

Reading rules:
- technical: exact same-Sunday weekly report
- news_trends: exact same-Sunday weekly report
- fundamental: latest filing report available on or before that Sunday
- macro: latest monthly macro report available on or before that Sunday

The script then runs Bull, Bear, and Judge for each configured ticker and
saves one aggregated JSON file per Sunday for:
- bull
- bear
- judge
- transcript
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.agents.DEBATE_STAGE import BearAgent, BullAgent, JudgeAgent
from src.schemas.debate_output import (
    WeeklyDebateReport,
    WeeklyDebateView,
    WeeklyJudgeReport,
    WeeklyPortfolioAllocation,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TICKERS = ["AAPL", "AMZN", "BRK.B", "GOOGL", "LLY", "XOM"]
DEFAULT_WEEK_END = None
DEFAULT_FUNDAMENTAL_DIR = "outputs/historical_analyst_reports/fundamental"
DEFAULT_TECHNICAL_DIR = "outputs/historical_analyst_reports/technical"
DEFAULT_MACRO_DIR = "outputs/historical_analyst_reports/macro"
DEFAULT_NEWS_DIR = "outputs/historical_analyst_reports/news_trends"
DEFAULT_OUTPUT_DIR = "outputs/debate_stage"
DEFAULT_DEBATE_ROUNDS = 1
DEFAULT_MEMORY_LOOKBACK_WEEKS = 4
DEFAULT_MEMORY_MAX_WEEKS = 8


def _resolve_path(path_str: str | Path) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _display_path(path: str | Path) -> str:
    resolved = _resolve_path(path)
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def save_json(data: dict, output_path: str | Path) -> None:
    resolved_output_path = _resolve_path(output_path)
    os.makedirs(resolved_output_path.parent, exist_ok=True)
    with open(resolved_output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def _parse_date(value: str) -> tuple[int, int, int]:
    year, month, day = value.split("-")
    return int(year), int(month), int(day)


def _validate_date(value: str, *, label: str) -> str:
    import datetime as _dt

    try:
        parsed = _dt.date(*_parse_date(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a valid date in YYYY-MM-DD format, got {value}") from exc
    return parsed.isoformat()


def _date_to_ordinal(value: str) -> int:
    year, month, day = _parse_date(value)
    return (year * 10000) + (month * 100) + day


def _shift_date(value: str, days: int) -> str:
    import datetime as _dt

    current = _dt.date(*_parse_date(value))
    return (current + _dt.timedelta(days=days)).isoformat()


def _is_sunday(value: str) -> bool:
    import datetime as _dt

    return _dt.date(*_parse_date(value)).weekday() == 6


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _as_list(value) -> list:
    if isinstance(value, list):
        return [item for item in value if item is not None]
    if value is None:
        return []
    return [value]


def _extract_simple_date_from_stem(stem: str, prefix: str) -> str:
    if not stem.startswith(prefix):
        raise ValueError(f"Unexpected filename format: {stem}")
    return stem[len(prefix) :]


def _extract_fundamental_filed_date(stem: str, ticker: str) -> str:
    prefix = f"{ticker}_"
    if not stem.startswith(prefix):
        raise ValueError(f"Unexpected fundamental filename format: {stem}")
    remainder = stem[len(prefix) :]
    if len(remainder) < 10:
        raise ValueError(f"Missing filed date in filename: {stem}")
    return remainder[:10]


def _select_exact_weekly_report_path(report_dir: str, ticker: str, report_date: str) -> Path:
    candidate = _resolve_path(report_dir) / f"{ticker}_{report_date}.json"
    if not candidate.exists():
        raise FileNotFoundError(
            f"Missing weekly report for {ticker} at {report_date}: {_display_path(candidate)}"
        )
    return candidate


def _select_latest_fundamental_path(report_dir: str, ticker: str, cutoff_date: str) -> Path:
    base = _resolve_path(report_dir)
    candidates = sorted(base.glob(f"{ticker}_*.json"))
    if not candidates:
        raise FileNotFoundError(
            f"No fundamental reports found for {ticker} under {_display_path(base)}"
        )

    eligible: list[tuple[str, Path]] = []
    for path in candidates:
        filed_date = _extract_fundamental_filed_date(path.stem, ticker)
        if _date_to_ordinal(filed_date) <= _date_to_ordinal(cutoff_date):
            eligible.append((filed_date, path))

    if not eligible:
        raise FileNotFoundError(
            f"No fundamental report for {ticker} on or before {cutoff_date} under {_display_path(base)}"
        )

    return max(eligible, key=lambda item: item[0])[1]


def _select_latest_macro_path(report_dir: str, cutoff_date: str) -> Path:
    base = _resolve_path(report_dir)
    candidates = sorted(base.glob("MACRO_*.json"))
    if not candidates:
        raise FileNotFoundError(f"No macro reports found under {_display_path(base)}")

    eligible: list[tuple[str, Path]] = []
    for path in candidates:
        report_date = _extract_simple_date_from_stem(path.stem, "MACRO_")
        if _date_to_ordinal(report_date) <= _date_to_ordinal(cutoff_date):
            eligible.append((report_date, path))

    if not eligible:
        raise FileNotFoundError(
            f"No macro report on or before {cutoff_date} under {_display_path(base)}"
        )

    return max(eligible, key=lambda item: item[0])[1]


def _weekly_dates_for_ticker(report_dir: str, ticker: str) -> set[str]:
    base = _resolve_path(report_dir)
    if not base.exists():
        return set()

    dates: set[str] = set()
    for path in base.glob(f"{ticker}_*.json"):
        try:
            report_date = _extract_simple_date_from_stem(path.stem, f"{ticker}_")
        except ValueError:
            continue
        if len(report_date) == 10:
            dates.add(report_date)
    return dates


def _available_input_dates(tickers: list[str], technical_dir: str, news_dir: str) -> list[str]:
    common_dates: set[str] | None = None

    for ticker in tickers:
        technical_dates = _weekly_dates_for_ticker(technical_dir, ticker)
        news_dates = _weekly_dates_for_ticker(news_dir, ticker)
        ticker_dates = technical_dates & news_dates

        if not ticker_dates:
            raise FileNotFoundError(
                f"No shared weekly technical/news dates found for {ticker} in "
                f"{_display_path(technical_dir)} and {_display_path(news_dir)}"
            )

        common_dates = ticker_dates if common_dates is None else (common_dates & ticker_dates)

    return sorted(common_dates or [])


def _has_fundamental_report(report_dir: str, ticker: str, cutoff_date: str) -> bool:
    try:
        _select_latest_fundamental_path(report_dir=report_dir, ticker=ticker, cutoff_date=cutoff_date)
        return True
    except FileNotFoundError:
        return False


def _has_macro_report(report_dir: str, cutoff_date: str) -> bool:
    try:
        _select_latest_macro_path(report_dir=report_dir, cutoff_date=cutoff_date)
        return True
    except FileNotFoundError:
        return False


def _available_complete_week_dates(
    tickers: list[str],
    technical_dir: str,
    news_dir: str,
    fundamental_dir: str,
    macro_dir: str,
) -> list[str]:
    week_dates = _available_input_dates(
        tickers=tickers,
        technical_dir=technical_dir,
        news_dir=news_dir,
    )
    complete_dates: list[str] = []

    for week_date in week_dates:
        if not _has_macro_report(report_dir=macro_dir, cutoff_date=week_date):
            continue
        if not all(
            _has_fundamental_report(report_dir=fundamental_dir, ticker=ticker, cutoff_date=week_date)
            for ticker in tickers
        ):
            continue
        complete_dates.append(week_date)

    return complete_dates


def _filter_week_dates(
    week_dates: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[str]:
    filtered = list(week_dates)

    if start_date is not None:
        start_ordinal = _date_to_ordinal(start_date)
        filtered = [week_date for week_date in filtered if _date_to_ordinal(week_date) >= start_ordinal]
    if end_date is not None:
        end_ordinal = _date_to_ordinal(end_date)
        filtered = [week_date for week_date in filtered if _date_to_ordinal(week_date) <= end_ordinal]

    return filtered


def _source_report_dates(
    fundamental_path: Path,
    technical_path: Path,
    macro_path: Path,
    news_path: Path,
) -> dict[str, str]:
    return {
        "fundamental": fundamental_path.stem.split("_", 1)[1][:10],
        "technical": technical_path.stem.rsplit("_", 1)[-1],
        "macro": macro_path.stem.rsplit("_", 1)[-1],
        "news_trends": news_path.stem.rsplit("_", 1)[-1],
    }


def _load_analyst_reports_for_week(
    ticker: str,
    input_data_date: str,
    fundamental_dir: str,
    technical_dir: str,
    macro_path: Path,
    news_dir: str,
) -> tuple[list[dict], dict[str, str]]:
    fundamental_path = _select_latest_fundamental_path(
        report_dir=fundamental_dir,
        ticker=ticker,
        cutoff_date=input_data_date,
    )
    technical_path = _select_exact_weekly_report_path(
        report_dir=technical_dir,
        ticker=ticker,
        report_date=input_data_date,
    )
    news_path = _select_exact_weekly_report_path(
        report_dir=news_dir,
        ticker=ticker,
        report_date=input_data_date,
    )

    source_dates = _source_report_dates(
        fundamental_path=fundamental_path,
        technical_path=technical_path,
        macro_path=macro_path,
        news_path=news_path,
    )

    reports = [
        _load_json(fundamental_path),
        _load_json(technical_path),
        _load_json(macro_path),
        _load_json(news_path),
    ]
    return reports, source_dates


def _supports_stance(case: dict) -> bool:
    score_breakdown = case.get("score_breakdown") or {}
    try:
        argument_score = float(score_breakdown.get("argument_score", 0.0))
    except (TypeError, ValueError):
        argument_score = 0.0

    try:
        confidence = float(case.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    return argument_score > 0 or confidence >= 0.55


def _memory_dir(output_dir: str) -> Path:
    return _resolve_path(output_dir) / "memory"


def _memory_path(output_dir: str, ticker: str) -> Path:
    return _memory_dir(output_dir) / f"{ticker}.json"


def _extract_memory_snapshot(
    week_end_date: str,
    bull_case: dict,
    bear_case: dict,
    judge_decision: dict,
) -> dict:
    bull_support = [str(item) for item in bull_case.get("supporting_evidence", [])][:3]
    bear_support = [str(item) for item in bear_case.get("supporting_evidence", [])][:3]
    combined_risks = sorted(
        {str(item) for item in bull_case.get("risk_flags", [])}
        | {str(item) for item in bear_case.get("risk_flags", [])}
        | {str(item) for item in judge_decision.get("risk_flags", [])}
    )
    return {
        "week_end_date": week_end_date,
        "bull_thesis": str(bull_case.get("thesis", "")),
        "bear_thesis": str(bear_case.get("thesis", "")),
        "bull_top_points": bull_support,
        "bear_top_points": bear_support,
        "judge_signal": str(judge_decision.get("signal", "neutral")),
        "judge_confidence": round(float(judge_decision.get("confidence", 0.0)), 2),
        "risk_flags": combined_risks[:6],
        "dissenting_points": [str(item) for item in judge_decision.get("dissenting_points", [])][:4],
    }


def _summarize_cross_week_memory(memory_data: dict, lookback: int) -> dict:
    recent_weeks = [
        item
        for item in _as_list(memory_data.get("recent_weeks"))
        if isinstance(item, dict)
    ]
    recent_weeks = sorted(
        recent_weeks,
        key=lambda item: str(item.get("week_end_date", "")),
        reverse=True,
    )[:lookback]

    recurring_risks: dict[str, int] = {}
    recurring_dissent: dict[str, int] = {}
    for week in recent_weeks:
        for risk in [str(item) for item in week.get("risk_flags", [])]:
            recurring_risks[risk] = recurring_risks.get(risk, 0) + 1
        for point in [str(item) for item in week.get("dissenting_points", [])]:
            recurring_dissent[point] = recurring_dissent.get(point, 0) + 1

    recurring_risk_flags = [
        risk for risk, count in sorted(recurring_risks.items(), key=lambda item: (-item[1], item[0]))
        if count >= 2
    ][:4]
    recurring_dissenting_points = [
        point
        for point, count in sorted(recurring_dissent.items(), key=lambda item: (-item[1], item[0]))
        if count >= 2
    ][:4]

    return {
        "recent_weeks": recent_weeks,
        "signal_history": [str(item.get("judge_signal", "neutral")) for item in recent_weeks],
        "recent_bull_theses": [str(item.get("bull_thesis", "")) for item in recent_weeks if item.get("bull_thesis")],
        "recent_bear_theses": [str(item.get("bear_thesis", "")) for item in recent_weeks if item.get("bear_thesis")],
        "recurring_risk_flags": recurring_risk_flags,
        "recurring_dissenting_points": recurring_dissenting_points,
    }


def _load_cross_week_memory(
    ticker: str,
    output_dir: str,
    lookback: int = DEFAULT_MEMORY_LOOKBACK_WEEKS,
) -> dict:
    path = _memory_path(output_dir=output_dir, ticker=ticker)
    if not path.exists():
        return {
            "ticker": ticker,
            "recent_weeks": [],
            "signal_history": [],
            "recent_bull_theses": [],
            "recent_bear_theses": [],
            "recurring_risk_flags": [],
            "recurring_dissenting_points": [],
        }

    memory_data = _load_json(path)
    summary = _summarize_cross_week_memory(memory_data=memory_data, lookback=lookback)
    summary["ticker"] = ticker
    return summary


def _save_cross_week_memory(
    ticker: str,
    week_end_date: str,
    bull_case: dict,
    bear_case: dict,
    judge_decision: dict,
    output_dir: str,
    max_weeks: int = DEFAULT_MEMORY_MAX_WEEKS,
) -> None:
    path = _memory_path(output_dir=output_dir, ticker=ticker)
    if path.exists():
        memory_data = _load_json(path)
    else:
        memory_data = {"ticker": ticker, "recent_weeks": []}

    recent_weeks = [
        item
        for item in _as_list(memory_data.get("recent_weeks"))
        if isinstance(item, dict) and str(item.get("week_end_date", "")) != week_end_date
    ]
    recent_weeks.append(
        _extract_memory_snapshot(
            week_end_date=week_end_date,
            bull_case=bull_case,
            bear_case=bear_case,
            judge_decision=judge_decision,
        )
    )
    recent_weeks = sorted(
        recent_weeks,
        key=lambda item: str(item.get("week_end_date", "")),
        reverse=True,
    )[:max_weeks]

    memory_data = {
        "ticker": ticker,
        "updated_at": week_end_date,
        "recent_weeks": recent_weeks,
    }
    save_json(memory_data, path)


def _short_term_round_summary(round_number: int, bull_case: dict, bear_case: dict) -> dict:
    bull_points = [str(item) for item in bull_case.get("supporting_evidence", [])][:3]
    bear_points = [str(item) for item in bear_case.get("supporting_evidence", [])][:3]
    return {
        "round": round_number,
        "bull_thesis": str(bull_case.get("thesis", "")),
        "bull_top_points": bull_points,
        "bear_thesis": str(bear_case.get("thesis", "")),
        "bear_top_points": bear_points,
        "repeated_bull_points": [],
        "repeated_bear_points": [],
    }


def _build_weekly_case_view(case_obj, input_data_date: str, source_report_dates: dict[str, str]) -> WeeklyDebateView:
    case = case_obj.model_dump(mode="json") if hasattr(case_obj, "model_dump") else dict(case_obj)
    return WeeklyDebateView(
        ticker=str(case.get("ticker", "")),
        input_data_date=input_data_date,
        supports_stance=_supports_stance(case),
        confidence=round(float(case.get("confidence", 0.0)), 2),
        thesis=str(case.get("thesis", "")),
        reasons=[str(item) for item in case.get("supporting_evidence", [])][:5],
        counterpoints=[str(item) for item in case.get("counter_evidence", [])][:4],
        risk_flags=sorted({str(item) for item in case.get("risk_flags", [])}),
        source_report_dates=source_report_dates,
        score_breakdown={
            str(key): float(value)
            for key, value in (case.get("score_breakdown") or {}).items()
            if isinstance(key, str) and isinstance(value, (int, float))
        },
    )


def _allocation_scores(decisions: list[dict]) -> dict[str, float]:
    bullish_scores: dict[str, float] = {}
    for decision in decisions:
        if decision.get("signal") != "bullish":
            continue
        try:
            confidence = float(decision.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        try:
            raw_size = float(decision.get("position_size", 0.0))
        except (TypeError, ValueError):
            raw_size = 0.0

        score = max(raw_size, confidence - 0.45, 0.0)
        if score > 0:
            bullish_scores[str(decision["ticker"])] = score
    return bullish_scores


def _normalized_allocations(decisions: list[dict]) -> dict[str, float]:
    scores = _allocation_scores(decisions)
    if not scores:
        return {str(decision["ticker"]): 0.0 for decision in decisions}

    total_score = sum(scores.values())
    if total_score <= 1.0:
        allocations = {
            ticker: round(score * 100.0, 2)
            for ticker, score in scores.items()
        }
    else:
        allocations = {
            ticker: round((score / total_score) * 100.0, 2)
            for ticker, score in scores.items()
        }
        total_allocated = round(sum(allocations.values()), 2)
        remainder = round(100.0 - total_allocated, 2)
        if abs(remainder) > 0 and allocations:
            top_ticker = max(allocations, key=allocations.get)
            allocations[top_ticker] = round(allocations[top_ticker] + remainder, 2)

    for decision in decisions:
        allocations.setdefault(str(decision["ticker"]), 0.0)
    return allocations


def _portfolio_summary(week_end_date: str, allocations: list[WeeklyPortfolioAllocation]) -> str:
    bullish = [item.ticker for item in allocations if item.signal == "bullish" and item.suggested_position_pct > 0]
    bearish = [item.ticker for item in allocations if item.signal == "bearish"]

    if bullish:
        return (
            f"For the week ending {week_end_date}, the judge prefers a concentrated long book in "
            f"{', '.join(bullish)} while avoiding or underweighting {', '.join(bearish) if bearish else 'the remaining names'}."
        )
    if bearish:
        return (
            f"For the week ending {week_end_date}, the judge does not see a clean long allocation and "
            f"finds the weakest setups in {', '.join(bearish)}."
        )
    return (
        f"For the week ending {week_end_date}, the judge finds the six-stock slate broadly inconclusive "
        f"and keeps the portfolio out of directional positions."
    )


def _run_debate_for_ticker(
    ticker: str,
    analyst_reports: list[dict],
    rounds: int,
    cross_week_memory: dict | None = None,
) -> tuple[object, object, object, dict]:
    bull_agent = BullAgent()
    bear_agent = BearAgent()
    judge_agent = JudgeAgent(max_position_size=1.0)
    short_term_memory = {"ticker": ticker, "round_history": []}
    memory_context = {
        "short_term_memory": short_term_memory,
        "cross_week_memory": dict(cross_week_memory or {}),
    }

    bull_round_1 = bull_agent.build_case(analyst_reports, memory_context=memory_context)
    bear_round_1 = bear_agent.rebut(analyst_reports, bull_round_1, memory_context=memory_context)
    short_term_memory["round_history"].append(
        _short_term_round_summary(
            round_number=1,
            bull_case=bull_round_1.model_dump(mode="json"),
            bear_case=bear_round_1.model_dump(mode="json"),
        )
    )

    if rounds >= 2:
        bull_final = bull_agent.rebut(analyst_reports, bear_round_1, memory_context=memory_context)
        bear_final = bear_agent.rebut(analyst_reports, bull_final, memory_context=memory_context)
        round_2_summary = _short_term_round_summary(
            round_number=2,
            bull_case=bull_final.model_dump(mode="json"),
            bear_case=bear_final.model_dump(mode="json"),
        )
        previous_round = short_term_memory["round_history"][-1]
        round_2_summary["repeated_bull_points"] = [
            point
            for point in round_2_summary.get("bull_top_points", [])
            if point in previous_round.get("bull_top_points", [])
        ][:2]
        round_2_summary["repeated_bear_points"] = [
            point
            for point in round_2_summary.get("bear_top_points", [])
            if point in previous_round.get("bear_top_points", [])
        ][:2]
        short_term_memory["round_history"].append(round_2_summary)
    else:
        bull_final = bull_round_1
        bear_final = bear_round_1

    judge_decision = judge_agent.judge(
        bull_case=bull_final,
        bear_case=bear_final,
        analyst_reports=analyst_reports,
        memory_context=memory_context,
    )

    transcript = {
        "ticker": ticker,
        "analyst_reports": analyst_reports,
        "memory_context": memory_context,
        "bull_round_1": bull_round_1.model_dump(mode="json"),
        "bear_round_1": bear_round_1.model_dump(mode="json"),
        "bull_final": bull_final.model_dump(mode="json"),
        "bear_final": bear_final.model_dump(mode="json"),
        "judge_decision": judge_decision.model_dump(mode="json"),
    }
    return bull_final, bear_final, judge_decision, transcript


def run_for_week(
    week_end_date: str,
    tickers: list[str],
    fundamental_dir: str,
    technical_dir: str,
    macro_dir: str,
    news_dir: str,
    output_dir: str,
    rounds: int,
    memory_lookback: int,
    memory_max_weeks: int,
) -> None:
    if not _is_sunday(week_end_date):
        raise ValueError(f"week_end_date must be a Sunday, got {week_end_date}")

    input_data_date = week_end_date
    macro_path = _select_latest_macro_path(report_dir=macro_dir, cutoff_date=input_data_date)

    bull_views: list[WeeklyDebateView] = []
    bear_views: list[WeeklyDebateView] = []
    judge_allocations: list[WeeklyPortfolioAllocation] = []
    transcripts: list[dict] = []
    raw_judge_decisions: list[dict] = []

    for ticker in tickers:
        analyst_reports, source_dates = _load_analyst_reports_for_week(
            ticker=ticker,
            input_data_date=input_data_date,
            fundamental_dir=fundamental_dir,
            technical_dir=technical_dir,
            macro_path=macro_path,
            news_dir=news_dir,
        )
        cross_week_memory = _load_cross_week_memory(
            ticker=ticker,
            output_dir=output_dir,
            lookback=memory_lookback,
        )

        bull_case, bear_case, judge_decision, ticker_transcript = _run_debate_for_ticker(
            ticker=ticker,
            analyst_reports=analyst_reports,
            rounds=rounds,
            cross_week_memory=cross_week_memory,
        )

        bull_views.append(
            _build_weekly_case_view(
                case_obj=bull_case,
                input_data_date=input_data_date,
                source_report_dates=source_dates,
            )
        )
        bear_views.append(
            _build_weekly_case_view(
                case_obj=bear_case,
                input_data_date=input_data_date,
                source_report_dates=source_dates,
            )
        )

        decision_dict = judge_decision.model_dump(mode="json")
        decision_dict["source_report_dates"] = source_dates
        raw_judge_decisions.append(decision_dict)
        ticker_transcript["source_report_dates"] = source_dates
        transcripts.append(ticker_transcript)
        _save_cross_week_memory(
            ticker=ticker,
            week_end_date=week_end_date,
            bull_case=bull_case.model_dump(mode="json"),
            bear_case=bear_case.model_dump(mode="json"),
            judge_decision=judge_decision.model_dump(mode="json"),
            output_dir=output_dir,
            max_weeks=memory_max_weeks,
        )

    allocations = _normalized_allocations(raw_judge_decisions)

    for decision in raw_judge_decisions:
        ticker = str(decision["ticker"])
        judge_allocations.append(
            WeeklyPortfolioAllocation(
                ticker=ticker,
                input_data_date=input_data_date,
                signal=str(decision.get("signal", "neutral")),
                confidence=round(float(decision.get("confidence", 0.0)), 2),
                suggested_position_pct=allocations.get(ticker, 0.0),
                summary=str(decision.get("summary", "")),
                rationale=[str(item) for item in decision.get("rationale", [])][:5],
                dissenting_points=[str(item) for item in decision.get("dissenting_points", [])][:4],
                risk_flags=sorted({str(item) for item in decision.get("risk_flags", [])}),
                source_report_dates=dict(decision.get("source_report_dates", {})),
                score_breakdown={
                    str(key): float(value)
                    for key, value in (decision.get("score_breakdown") or {}).items()
                    if isinstance(key, str) and isinstance(value, (int, float))
                },
            )
        )

    judge_allocations.sort(key=lambda item: (-item.suggested_position_pct, item.ticker))
    bull_views.sort(key=lambda item: item.ticker)
    bear_views.sort(key=lambda item: item.ticker)

    weekly_bull_report = WeeklyDebateReport(
        agent_name="BullAgent",
        week_end_date=week_end_date,
        input_data_date=input_data_date,
        stance="bullish",
        tickers=sorted(tickers),
        company_views=bull_views,
    )
    weekly_bear_report = WeeklyDebateReport(
        agent_name="BearAgent",
        week_end_date=week_end_date,
        input_data_date=input_data_date,
        stance="bearish",
        tickers=sorted(tickers),
        company_views=bear_views,
    )

    total_allocated_pct = round(sum(item.suggested_position_pct for item in judge_allocations), 2)
    weekly_judge_report = WeeklyJudgeReport(
        agent_name="JudgeAgent",
        week_end_date=week_end_date,
        input_data_date=input_data_date,
        tickers=sorted(tickers),
        portfolio_summary=_portfolio_summary(week_end_date, judge_allocations),
        allocation_method=(
            "Use each bullish stock's raw judge conviction as its target weight. "
            "If combined bullish weights exceed 100%, scale them down proportionally; "
            "otherwise leave the remainder as cash. Bearish and neutral names receive 0%."
        ),
        holdings=judge_allocations,
        bullish_tickers=[item.ticker for item in judge_allocations if item.signal == "bullish"],
        bearish_tickers=[item.ticker for item in judge_allocations if item.signal == "bearish"],
        neutral_tickers=[item.ticker for item in judge_allocations if item.signal == "neutral"],
        total_allocated_pct=total_allocated_pct,
        cash_pct=round(max(0.0, 100.0 - total_allocated_pct), 2),
    )

    bull_output_path = Path(output_dir) / "bull" / f"{week_end_date}.json"
    bear_output_path = Path(output_dir) / "bear" / f"{week_end_date}.json"
    judge_output_path = Path(output_dir) / "judge" / f"{week_end_date}.json"
    transcript_output_path = Path(output_dir) / "transcript" / f"{week_end_date}.json"

    save_json(weekly_bull_report.model_dump(mode="json"), bull_output_path)
    save_json(weekly_bear_report.model_dump(mode="json"), bear_output_path)
    save_json(weekly_judge_report.model_dump(mode="json"), judge_output_path)
    save_json(
        {
            "week_end_date": week_end_date,
            "input_data_date": input_data_date,
            "tickers": sorted(tickers),
            "macro_report_date": macro_path.stem.rsplit("_", 1)[-1],
            "bull_report": weekly_bull_report.model_dump(mode="json"),
            "bear_report": weekly_bear_report.model_dump(mode="json"),
            "judge_report": weekly_judge_report.model_dump(mode="json"),
            "per_ticker_transcript": transcripts,
        },
        transcript_output_path,
    )

    print(f"\n=== WEEK {week_end_date} ===")
    print(f"Input data date:      {input_data_date}")
    print(f"Bull report saved:    {_display_path(bull_output_path)}")
    print(f"Bear report saved:    {_display_path(bear_output_path)}")
    print(f"Judge report saved:   {_display_path(judge_output_path)}")
    print(f"Transcript saved:     {_display_path(transcript_output_path)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the debate stage as a weekly batch process.")
    parser.add_argument(
        "--ticker",
        nargs="+",
        default=DEFAULT_TICKERS,
        help="Ticker symbols to include in the weekly debate batch",
    )
    parser.add_argument(
        "--week-end",
        type=str,
        default=DEFAULT_WEEK_END,
        help="Optional Sunday date for the debate output in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Optional inclusive start date used to filter weekly debate runs by week_end_date",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Optional inclusive end date used to filter weekly debate runs by week_end_date",
    )
    parser.add_argument(
        "--all-weeks",
        action="store_true",
        help="Run the weekly debate stage for every available common week",
    )
    parser.add_argument(
        "--fundamental-dir",
        type=str,
        default=DEFAULT_FUNDAMENTAL_DIR,
        help="Directory containing historical fundamental analyst reports",
    )
    parser.add_argument(
        "--technical-dir",
        type=str,
        default=DEFAULT_TECHNICAL_DIR,
        help="Directory containing weekly technical analyst reports",
    )
    parser.add_argument(
        "--macro-dir",
        type=str,
        default=DEFAULT_MACRO_DIR,
        help="Directory containing monthly macro analyst reports",
    )
    parser.add_argument(
        "--news-dir",
        type=str,
        default=DEFAULT_NEWS_DIR,
        help="Directory containing weekly news/trends analyst reports",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where weekly debate outputs will be saved",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        choices=[1, 2],
        default=DEFAULT_DEBATE_ROUNDS,
        help="Debate rounds per ticker. Default is 1 to reduce LLM calls.",
    )
    parser.add_argument(
        "--memory-lookback",
        type=int,
        default=DEFAULT_MEMORY_LOOKBACK_WEEKS,
        help="Number of prior weeks of cross-week memory to summarize into the current debate context.",
    )
    parser.add_argument(
        "--memory-max-weeks",
        type=int,
        default=DEFAULT_MEMORY_MAX_WEEKS,
        help="Maximum number of weekly memory snapshots to retain per ticker.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers = [str(ticker).upper() for ticker in args.ticker]
    start_date = _validate_date(args.start_date, label="--start-date") if args.start_date else None
    end_date = _validate_date(args.end_date, label="--end-date") if args.end_date else None

    if start_date and end_date and _date_to_ordinal(start_date) > _date_to_ordinal(end_date):
        raise ValueError(f"--start-date must be on or before --end-date, got {start_date} > {end_date}")

    if args.week_end and (start_date or end_date):
        raise ValueError("--week-end cannot be combined with --start-date or --end-date")
    if args.memory_lookback < 1:
        raise ValueError(f"--memory-lookback must be at least 1, got {args.memory_lookback}")
    if args.memory_max_weeks < 1:
        raise ValueError(f"--memory-max-weeks must be at least 1, got {args.memory_max_weeks}")
    if args.memory_max_weeks < args.memory_lookback:
        raise ValueError(
            f"--memory-max-weeks must be greater than or equal to --memory-lookback, got "
            f"{args.memory_max_weeks} < {args.memory_lookback}"
        )

    if args.week_end:
        week_end_dates = [_validate_date(args.week_end, label="--week-end")]
    else:
        week_end_dates = _available_complete_week_dates(
            tickers=tickers,
            technical_dir=args.technical_dir,
            news_dir=args.news_dir,
            fundamental_dir=args.fundamental_dir,
            macro_dir=args.macro_dir,
        )
        week_end_dates = _filter_week_dates(
            week_dates=week_end_dates,
            start_date=start_date,
            end_date=end_date,
        )

    if not week_end_dates:
        raise FileNotFoundError(
            "No complete weekly datasets are available for the requested tickers "
            "within the requested date selection. Check historical technical/news/"
            "fundamental/macro reports and the selected date range."
        )

    for week_end_date in week_end_dates:
        run_for_week(
            week_end_date=week_end_date,
            tickers=tickers,
            fundamental_dir=args.fundamental_dir,
            technical_dir=args.technical_dir,
            macro_dir=args.macro_dir,
            news_dir=args.news_dir,
            output_dir=args.output_dir,
            rounds=args.rounds,
            memory_lookback=args.memory_lookback,
            memory_max_weeks=args.memory_max_weeks,
        )


if __name__ == "__main__":
    main()
