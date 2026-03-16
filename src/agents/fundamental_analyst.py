"""
Fundamental Analyst Agent

Summary
-------
This module implements the Fundamental Analyst agent for DebateTrader.

Responsibilities
----------------
- Receive a cleaned fundamental snapshot for a stock
- Evaluate valuation, growth, profitability, leverage, and liquidity
- Produce a structured JSON-friendly analysis report

Current Version
---------------
This version is rule-based and uses the Yahoo Finance fundamentals snapshot
as its input. It is designed as a milestone-stage analyst implementation.
"""

from __future__ import annotations

from src.schemas.analyst_output import AnalystOutput


class FundamentalAnalyst:
    """Rule-based fundamental analyst agent."""

    def analyze(self, snapshot: dict) -> AnalystOutput:
        ticker = snapshot["ticker"]
        analysis_date = snapshot["analysis_date"]
        f = snapshot["fundamental_features"]

        bullish_factors: list[str] = []
        bearish_factors: list[str] = []
        risk_flags: list[str] = []

        bullish_score = 0
        bearish_score = 0

        pe_ratio_ttm = f.get("pe_ratio_ttm")
        pe_ratio_forward = f.get("pe_ratio_forward")
        revenue_growth_yoy = f.get("revenue_growth_yoy")
        earnings_growth_yoy = f.get("earnings_growth_yoy")
        gross_margin = f.get("gross_margin")
        operating_margin = f.get("operating_margin")
        net_margin = f.get("net_margin")
        debt_to_equity = f.get("debt_to_equity")
        current_ratio = f.get("current_ratio")
        quick_ratio = f.get("quick_ratio")
        roe = f.get("roe")
        roa = f.get("roa")
        free_cash_flow = f.get("free_cash_flow")
        operating_cash_flow = f.get("operating_cash_flow")
        dividend_yield = f.get("dividend_yield")

        if revenue_growth_yoy is not None:
            if revenue_growth_yoy > 0.05:
                bullish_score += 1
                bullish_factors.append("Revenue growth is positive and above a modest growth threshold.")
            elif revenue_growth_yoy < 0:
                bearish_score += 1
                bearish_factors.append("Revenue growth is negative year-over-year.")

        if earnings_growth_yoy is not None:
            if earnings_growth_yoy > 0:
                bullish_score += 1
                bullish_factors.append("Earnings growth is positive year-over-year.")
            elif earnings_growth_yoy < 0:
                bearish_score += 1
                bearish_factors.append("Earnings growth is negative year-over-year.")

        if gross_margin is not None:
            if gross_margin > 0.40:
                bullish_score += 1
                bullish_factors.append("Gross margin is strong.")
            elif gross_margin < 0.20:
                bearish_score += 1
                bearish_factors.append("Gross margin is relatively weak.")

        if operating_margin is not None:
            if operating_margin > 0.15:
                bullish_score += 1
                bullish_factors.append("Operating margin indicates solid operating profitability.")
            elif operating_margin < 0.05:
                bearish_score += 1
                bearish_factors.append("Operating margin is thin.")

        if net_margin is not None:
            if net_margin > 0.10:
                bullish_score += 1
                bullish_factors.append("Net margin is healthy.")
            elif net_margin < 0:
                bearish_score += 1
                bearish_factors.append("Net margin is negative.")

        if roe is not None:
            if roe > 0.15:
                bullish_score += 1
                bullish_factors.append("Return on equity is strong.")
            elif roe < 0:
                bearish_score += 1
                bearish_factors.append("Return on equity is negative.")

        if roa is not None:
            if roa > 0.05:
                bullish_score += 1
                bullish_factors.append("Return on assets is solid.")
            elif roa < 0:
                bearish_score += 1
                bearish_factors.append("Return on assets is negative.")

        if debt_to_equity is not None:
            if debt_to_equity > 2.0:
                bearish_score += 1
                bearish_factors.append("Debt-to-equity is elevated, implying higher leverage risk.")
                risk_flags.append("Leverage risk")
            elif debt_to_equity < 1.0:
                bullish_score += 1
                bullish_factors.append("Debt-to-equity is moderate.")

        if current_ratio is not None:
            if current_ratio >= 1.2:
                bullish_score += 1
                bullish_factors.append("Current ratio suggests adequate short-term liquidity.")
            elif current_ratio < 1.0:
                bearish_score += 1
                bearish_factors.append("Current ratio is below 1.0, suggesting weaker short-term liquidity.")
                risk_flags.append("Liquidity risk")

        if quick_ratio is not None and quick_ratio < 1.0:
            risk_flags.append("Quick liquidity risk")

        if free_cash_flow is not None:
            if free_cash_flow > 0:
                bullish_score += 1
                bullish_factors.append("Free cash flow is positive.")
            elif free_cash_flow < 0:
                bearish_score += 1
                bearish_factors.append("Free cash flow is negative.")

        if operating_cash_flow is not None and operating_cash_flow < 0:
            bearish_score += 1
            bearish_factors.append("Operating cash flow is negative.")
            risk_flags.append("Cash flow risk")

        if pe_ratio_ttm is not None:
            if pe_ratio_ttm > 35:
                bearish_score += 1
                bearish_factors.append("Trailing P/E is high, suggesting valuation risk.")
                risk_flags.append("Valuation risk")
            elif 0 < pe_ratio_ttm < 20:
                bullish_score += 1
                bullish_factors.append("Trailing P/E is within a relatively moderate range.")

        if pe_ratio_forward is not None and pe_ratio_ttm is not None:
            if pe_ratio_forward < pe_ratio_ttm:
                bullish_score += 1
                bullish_factors.append("Forward P/E is below trailing P/E, implying improving earnings expectations.")

        if dividend_yield is not None and dividend_yield > 0.02:
            bullish_factors.append("Dividend yield provides some shareholder return support.")

        score_diff = bullish_score - bearish_score

        if score_diff >= 2:
            signal = "bullish"
        elif score_diff <= -2:
            signal = "bearish"
        else:
            signal = "neutral"

        confidence = min(0.95, 0.50 + abs(score_diff) * 0.07)

        if signal == "bullish":
            summary = "Fundamental indicators are broadly supportive, with stronger bullish than bearish evidence."
        elif signal == "bearish":
            summary = "Fundamental indicators are broadly weak, with stronger bearish than bullish evidence."
        else:
            summary = "Fundamental indicators are mixed, without a strong directional edge."

        return AnalystOutput(
            agent_name="FundamentalAnalyst",
            ticker=ticker,
            analysis_date=analysis_date,
            signal=signal,
            confidence=round(confidence, 2),
            summary=summary,
            bullish_factors=bullish_factors,
            bearish_factors=bearish_factors,
            risk_flags=sorted(set(risk_flags)),
            key_metrics_used={
                "pe_ratio_ttm": pe_ratio_ttm,
                "pe_ratio_forward": pe_ratio_forward,
                "revenue_growth_yoy": revenue_growth_yoy,
                "earnings_growth_yoy": earnings_growth_yoy,
                "gross_margin": gross_margin,
                "operating_margin": operating_margin,
                "net_margin": net_margin,
                "debt_to_equity": debt_to_equity,
                "current_ratio": current_ratio,
                "quick_ratio": quick_ratio,
                "roe": roe,
                "roa": roa,
                "free_cash_flow": free_cash_flow,
                "operating_cash_flow": operating_cash_flow,
                "dividend_yield": dividend_yield,
            },
        )