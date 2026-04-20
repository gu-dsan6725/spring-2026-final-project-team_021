"""
Run an end-to-end DebateTrader project demo on bundled sample data.

This script is intentionally showcase-oriented:
- builds technical, fundamental, news/trends, and macro snapshots
- runs all four analyst stages
- runs bull vs bear debate plus judge decision
- works even without LLM credentials by falling back to rule summaries

Usage
-----
uv run python -m src.demo.run_project_demo
uv run python -m src.demo.run_project_demo --ticker AAPL --date 2026-04-11
uv run python -m src.demo.run_project_demo --save outputs/demo/aapl_demo.json
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.agents.DEBATE_STAGE import BearAgent, BullAgent, JudgeAgent
from src.agents.fundamental_analyst import FundamentalAnalyst
from src.agents.macro_analyst import MacroAnalyst
from src.agents.news_trends_analyst import NewsTrendsAnalyst
from src.agents.technical_analyst import TechnicalAnalyst
from src.features.fundamental_features import build_fundamental_snapshot
from src.features.news_macro_features import build_news_macro_snapshot
from src.features.technical_features import build_technical_snapshot
from src.schemas.analyst_output import AnalystOutput


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TICKER = "AAPL"
DEFAULT_PRICE_PATH = "data/sample/price/price_ohlcv.csv"
DEFAULT_FUNDAMENTALS_PATH = "data/sample/fundamentals/quarterly_fundamentals.csv"
DEFAULT_NEWS_PATH = "data/sample/news/all_news.csv"
DEFAULT_MACRO_PATH = "data/sample/macro/macro_all_daily_ffill.csv"
DEFAULT_TRENDS_PATH = "data/sample/sentiment/google_trends_daily.csv"

COMPANY_NAMES = {
    "AAPL": "Apple",
    "AMZN": "Amazon",
    "BRK.B": "Berkshire Hathaway",
    "GOOGL": "Alphabet",
    "LLY": "Eli Lilly",
    "XOM": "Exxon Mobil",
}


def _resolve_path(path_str: str) -> str:
    path = Path(path_str)
    if path.is_absolute():
        return str(path)
    return str(PROJECT_ROOT / path)


def _rule_signal(
    bullish_factors: list[str],
    bearish_factors: list[str],
    risk_flags: list[str],
) -> tuple[str, float]:
    score = len(bullish_factors) - len(bearish_factors) - (0.35 * len(risk_flags))
    if score >= 1.0:
        signal = "bullish"
    elif score <= -1.0:
        signal = "bearish"
    else:
        signal = "neutral"

    confidence = 0.52 + min(abs(score), 4.0) * 0.07
    confidence = max(0.5, min(0.84, confidence))
    return signal, round(confidence, 2)


def _rule_summary(
    label: str,
    signal: str,
    bullish_factors: list[str],
    bearish_factors: list[str],
    risk_flags: list[str],
) -> str:
    if signal == "bullish":
        anchor = bullish_factors[0] if bullish_factors else "bullish evidence outweighs bearish evidence"
        return f"{label} view is bullish because {anchor.lower()}"
    if signal == "bearish":
        anchor = bearish_factors[0] if bearish_factors else "bearish evidence outweighs bullish evidence"
        return f"{label} view is bearish because {anchor.lower()}"

    if risk_flags:
        return f"{label} view is neutral because signals are mixed and key risk remains {risk_flags[0].lower()}"
    return f"{label} view is neutral because bullish and bearish evidence are balanced"


def _fallback_technical_report(snapshot: dict) -> AnalystOutput:
    agent = TechnicalAnalyst()
    bullish_factors, bearish_factors, risk_flags, key_metrics_used = agent._extract_evidence(snapshot)
    signal, confidence = _rule_signal(bullish_factors, bearish_factors, risk_flags)
    return AnalystOutput(
        agent_name="TechnicalAnalyst",
        ticker=snapshot["ticker"],
        analysis_date=snapshot["analysis_date"],
        signal=signal,
        confidence=confidence,
        summary=_rule_summary("Technical", signal, bullish_factors, bearish_factors, risk_flags),
        bullish_factors=bullish_factors,
        bearish_factors=bearish_factors,
        risk_flags=risk_flags,
        key_metrics_used=key_metrics_used,
    )


def _fallback_fundamental_report(snapshot: dict) -> AnalystOutput:
    agent = FundamentalAnalyst()
    bullish_factors, bearish_factors, risk_flags, key_metrics_used = agent._extract_evidence(snapshot)
    signal, confidence = _rule_signal(bullish_factors, bearish_factors, risk_flags)
    return AnalystOutput(
        agent_name="FundamentalAnalyst",
        ticker=snapshot["ticker"],
        analysis_date=snapshot["analysis_date"],
        signal=signal,
        confidence=confidence,
        summary=_rule_summary("Fundamental", signal, bullish_factors, bearish_factors, risk_flags),
        bullish_factors=bullish_factors,
        bearish_factors=bearish_factors,
        risk_flags=risk_flags,
        key_metrics_used=key_metrics_used,
    )


def _run_with_fallback(agent, snapshot: dict, fallback_builder):
    try:
        report = agent.analyze(snapshot)
        return report, "llm"
    except Exception as exc:
        report = fallback_builder(snapshot)
        return report, f"rules ({exc})"


def _print_analyst_report(report: AnalystOutput) -> None:
    print(f"- {report.agent_name}: {report.signal.upper()} | confidence={report.confidence:.2f}")
    print(f"  summary: {report.summary}")
    if report.bullish_factors:
        print(f"  bullish: {report.bullish_factors[0]}")
    if report.bearish_factors:
        print(f"  bearish: {report.bearish_factors[0]}")
    if report.risk_flags:
        print(f"  risk: {report.risk_flags[0]}")


def build_demo_payload(ticker: str, analysis_date: str | None = None) -> tuple[dict, dict]:
    ticker = ticker.upper()
    company_name = COMPANY_NAMES.get(ticker, ticker)

    technical_snapshot = build_technical_snapshot(
        parquet_path=_resolve_path(DEFAULT_PRICE_PATH),
        ticker=ticker,
        as_of_date=analysis_date,
    )
    effective_date = analysis_date or technical_snapshot["analysis_date"]
    fundamental_snapshot = build_fundamental_snapshot(
        parquet_path=_resolve_path(DEFAULT_FUNDAMENTALS_PATH),
        ticker=ticker,
        as_of_date=effective_date,
    )
    news_macro_snapshot = build_news_macro_snapshot(
        news_csv_path=_resolve_path(DEFAULT_NEWS_PATH),
        macro_csv_path=_resolve_path(DEFAULT_MACRO_PATH),
        ticker=ticker,
        as_of_date=effective_date,
        google_trends_csv_path=_resolve_path(DEFAULT_TRENDS_PATH),
        company_name=company_name,
    )

    technical_report, technical_mode = _run_with_fallback(
        TechnicalAnalyst(),
        technical_snapshot,
        _fallback_technical_report,
    )
    fundamental_report, fundamental_mode = _run_with_fallback(
        FundamentalAnalyst(),
        fundamental_snapshot,
        _fallback_fundamental_report,
    )
    news_report = NewsTrendsAnalyst().analyze(news_macro_snapshot)
    macro_report = MacroAnalyst().analyze(news_macro_snapshot)

    analyst_reports = [
        technical_report,
        fundamental_report,
        news_report,
        macro_report,
    ]

    bull_case = BullAgent().build_case(analyst_reports)
    bear_case = BearAgent().build_case(analyst_reports, opponent_case=bull_case)
    judge_decision = JudgeAgent(max_position_size=0.10).judge(
        bull_case=bull_case,
        bear_case=bear_case,
        analyst_reports=analyst_reports,
    )

    payload = {
        "ticker": ticker,
        "analysis_date": effective_date,
        "run_modes": {
            "technical": technical_mode,
            "fundamental": fundamental_mode,
            "news_trends": "rules",
            "macro": "rules",
            "debate": "llm_or_rules_fallback",
            "judge": "llm_or_rules_fallback",
        },
        "analyst_reports": [report.model_dump(mode="json") for report in analyst_reports],
        "bull_case": bull_case.model_dump(mode="json"),
        "bear_case": bear_case.model_dump(mode="json"),
        "judge_decision": judge_decision.model_dump(mode="json"),
    }
    context = {
        "technical_snapshot": technical_snapshot,
        "fundamental_snapshot": fundamental_snapshot,
        "news_macro_snapshot": news_macro_snapshot,
    }
    return payload, context


def _disable_llm_providers() -> None:
    for env_name in (
        "ANTHROPIC_API_KEY",
        "GROQ_API_KEY",
        "DEBATETRADER_LLM_PROVIDER",
        "DEBATETRADER_LLM_MODEL",
    ):
        os.environ.pop(env_name, None)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an end-to-end DebateTrader demo.")
    parser.add_argument("--ticker", type=str, default=DEFAULT_TICKER, help="Ticker to showcase")
    parser.add_argument("--date", type=str, default=None, help="Optional analysis date in YYYY-MM-DD")
    parser.add_argument("--save", type=str, default=None, help="Optional JSON output path")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force local rule-based fallbacks instead of live LLM calls",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.offline:
        _disable_llm_providers()
    payload, _ = build_demo_payload(ticker=args.ticker, analysis_date=args.date)

    print(f"DebateTrader Demo | ticker={payload['ticker']} | analysis_date={payload['analysis_date']}")
    print("")
    print("Analyst stage")
    for report_data in payload["analyst_reports"]:
        _print_analyst_report(AnalystOutput(**report_data))

    print("")
    print("Debate stage")
    print(f"- Bull thesis: {payload['bull_case']['thesis']}")
    print(f"- Bear thesis: {payload['bear_case']['thesis']}")

    judge = payload["judge_decision"]
    print("")
    print("Judge decision")
    print(
        f"- Final signal: {judge['signal'].upper()} | confidence={judge['confidence']:.2f} "
        f"| position_size={judge['position_size']:.2%}"
    )
    print(f"- Summary: {judge['summary']}")

    if args.save:
        save_path = Path(args.save)
        if not save_path.is_absolute():
            save_path = PROJECT_ROOT / save_path
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print("")
        print(f"Saved full demo payload to {save_path}")


if __name__ == "__main__":
    main()
