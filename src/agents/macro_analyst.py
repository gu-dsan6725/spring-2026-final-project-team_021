"""
Macro Analyst Agent

Summary
-------
This module implements the Macro Analyst agent for DebateTrader.

Responsibilities
----------------
- Receive a cleaned news/macro snapshot for a stock
- Evaluate the broad macroeconomic backdrop only
- Produce a structured JSON-friendly analysis report
"""

from __future__ import annotations

from src.schemas.analyst_output import AnalystOutput


class MacroAnalyst:
    """Rule-based macro analyst agent."""

    def analyze(self, snapshot: dict) -> AnalystOutput:
        ticker = snapshot["ticker"]
        analysis_date = snapshot["analysis_date"]
        macro = snapshot["news_macro_features"]["macro_features"]

        bullish_factors: list[str] = []
        bearish_factors: list[str] = []
        risk_flags: list[str] = []

        bullish_score = 0
        bearish_score = 0

        macro_date = macro.get("macro_date")
        macro_data_lag_days = macro.get("macro_data_lag_days")
        fed_funds_rate = macro.get("fed_funds_rate")
        inflation_rate = macro.get("inflation_rate")
        unemployment = macro.get("unemployment")
        yield_curve_proxy = macro.get("yield_curve_proxy")
        gdp_growth = macro.get("gdp_growth")
        industrial_production_growth = macro.get("industrial_production_growth")

        if yield_curve_proxy is not None:
            if yield_curve_proxy > 0:
                bullish_score += 1
                bullish_factors.append("The yield-curve proxy is positive, which is less recessionary than an inverted curve.")
            elif yield_curve_proxy < 0:
                bearish_score += 1
                bearish_factors.append("The yield-curve proxy is negative, pointing to a more cautious macro backdrop.")
                risk_flags.append("Yield-curve inversion risk")

        if gdp_growth is not None:
            if gdp_growth > 0:
                bullish_score += 1
                bullish_factors.append("GDP growth is positive in the latest macro snapshot.")
            elif gdp_growth < 0:
                bearish_score += 1
                bearish_factors.append("GDP growth is negative in the latest macro snapshot.")

        if industrial_production_growth is not None:
            if industrial_production_growth > 0:
                bullish_score += 1
                bullish_factors.append("Industrial production growth is positive in the latest macro snapshot.")
            elif industrial_production_growth < 0:
                bearish_score += 1
                bearish_factors.append("Industrial production growth is negative in the latest macro snapshot.")

        if unemployment is not None:
            if unemployment <= 4.0:
                bullish_score += 1
                bullish_factors.append("Unemployment remains relatively low.")
            elif unemployment > 4.5:
                bearish_score += 1
                bearish_factors.append("Unemployment is elevated above a moderate threshold.")

        if inflation_rate is not None:
            if inflation_rate > 0.0035:
                bearish_score += 1
                bearish_factors.append("Monthly inflation appears elevated, which can pressure valuation multiples.")
                risk_flags.append("Inflation pressure risk")

        if fed_funds_rate is not None and fed_funds_rate > 4.5:
            bearish_score += 1
            bearish_factors.append("Policy rates remain relatively restrictive for risk assets.")

        score_diff = bullish_score - bearish_score

        if score_diff >= 2:
            signal = "bullish"
        elif score_diff <= -2:
            signal = "bearish"
        else:
            signal = "neutral"

        confidence = min(0.85, 0.50 + abs(score_diff) * 0.04)

        if signal == "bullish":
            summary = "Macro conditions are broadly supportive, with more bullish than bearish evidence."
        elif signal == "bearish":
            summary = "Macro conditions lean cautious, with more bearish than bullish evidence."
        else:
            summary = "Macro conditions are mixed, without a strong directional edge."

        return AnalystOutput(
            agent_name="MacroAnalyst",
            ticker=ticker,
            analysis_date=analysis_date,
            signal=signal,
            confidence=round(confidence, 2),
            summary=summary,
            bullish_factors=bullish_factors,
            bearish_factors=bearish_factors,
            risk_flags=sorted(set(risk_flags)),
            key_metrics_used={
                "macro_date": macro_date,
                "macro_data_lag_days": macro_data_lag_days,
                "fed_funds_rate": fed_funds_rate,
                "inflation_rate": inflation_rate,
                "unemployment": unemployment,
                "yield_curve_proxy": yield_curve_proxy,
                "gdp_growth": gdp_growth,
                "industrial_production_growth": industrial_production_growth,
            },
        )