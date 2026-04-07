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
        three_month_treasury = macro.get("three_month_treasury")
        two_year_treasury = macro.get("two_year_treasury")
        ten_year_treasury = macro.get("ten_year_treasury")
        fed_funds_rate = macro.get("fed_funds_rate")
        inflation_rate = macro.get("inflation_rate")
        unemployment = macro.get("unemployment")
        labor_force_participation = macro.get("labor_force_participation")
        yield_spread_10y2y = macro.get("yield_spread_10y2y")
        yield_spread_10y3m = macro.get("yield_spread_10y3m")
        vix = macro.get("vix")
        credit_spread = macro.get("credit_spread")
        financial_stress_index = macro.get("financial_stress_index")
        yield_curve_proxy = macro.get("yield_curve_proxy")
        gdp_growth = macro.get("gdp_growth")
        industrial_production_growth = macro.get("industrial_production_growth")
        retail_sales_growth = macro.get("retail_sales_growth")
        payroll_employment_growth = macro.get("payroll_employment_growth")
        consumer_sentiment = macro.get("consumer_sentiment")
        housing_permits_growth = macro.get("housing_permits_growth")

        if yield_curve_proxy is not None:
            if yield_curve_proxy > 0:
                bullish_score += 1
                bullish_factors.append("The yield-curve proxy is positive, which is less recessionary than an inverted curve.")
            elif yield_curve_proxy < 0:
                bearish_score += 1
                bearish_factors.append("The yield-curve proxy is negative, pointing to a more cautious macro backdrop.")
                risk_flags.append("Yield-curve inversion risk")

        if yield_spread_10y3m is not None:
            if yield_spread_10y3m > 0:
                bullish_score += 1
                bullish_factors.append("The 10Y-3M term spread is positive, which supports a healthier growth backdrop.")
            elif yield_spread_10y3m < 0:
                bearish_score += 1
                bearish_factors.append("The 10Y-3M term spread is inverted, which is historically a recession warning.")
                risk_flags.append("Front-end inversion risk")

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

        if retail_sales_growth is not None:
            if retail_sales_growth > 0:
                bullish_score += 1
                bullish_factors.append("Retail sales are growing, which supports consumer demand.")
            elif retail_sales_growth < 0:
                bearish_score += 1
                bearish_factors.append("Retail sales are contracting, suggesting weaker consumer demand.")

        if payroll_employment_growth is not None:
            if payroll_employment_growth > 0:
                bullish_score += 1
                bullish_factors.append("Payroll employment is still expanding.")
            elif payroll_employment_growth < 0:
                bearish_score += 1
                bearish_factors.append("Payroll employment is contracting.")

        if unemployment is not None:
            if unemployment <= 4.0:
                bullish_score += 1
                bullish_factors.append("Unemployment remains relatively low.")
            elif unemployment > 4.5:
                bearish_score += 1
                bearish_factors.append("Unemployment is elevated above a moderate threshold.")

        if labor_force_participation is not None and labor_force_participation < 62.0:
            bearish_score += 1
            bearish_factors.append("Labor force participation is soft, which can signal a less robust labor market.")

        if consumer_sentiment is not None:
            if consumer_sentiment >= 70:
                bullish_score += 1
                bullish_factors.append("Consumer sentiment is relatively healthy.")
            elif consumer_sentiment < 60:
                bearish_score += 1
                bearish_factors.append("Consumer sentiment is weak.")

        if inflation_rate is not None:
            if inflation_rate > 0.0035:
                bearish_score += 1
                bearish_factors.append("Monthly inflation appears elevated, which can pressure valuation multiples.")
                risk_flags.append("Inflation pressure risk")
            elif inflation_rate < 0.002:
                bullish_score += 1
                bullish_factors.append("Inflation is relatively contained in the latest reading.")

        if fed_funds_rate is not None:
            if fed_funds_rate > 4.5:
                bearish_score += 1
                bearish_factors.append("Policy rates remain relatively restrictive for risk assets.")
            elif fed_funds_rate < 3.0:
                bullish_score += 1
                bullish_factors.append("Policy rates are comparatively accommodative.")

        if ten_year_treasury is not None:
            if ten_year_treasury > 4.5:
                bearish_score += 1
                bearish_factors.append("Long-term Treasury yields are elevated, which can pressure equity valuations.")
            elif ten_year_treasury < 3.5:
                bullish_score += 1
                bullish_factors.append("Long-term Treasury yields are moderate, which is friendlier to valuation multiples.")

        if vix is not None:
            if vix >= 25:
                bearish_score += 1
                bearish_factors.append("VIX is elevated, indicating higher market stress.")
                risk_flags.append("Elevated volatility regime")
            elif vix <= 18:
                bullish_score += 1
                bullish_factors.append("VIX is contained, indicating a calmer risk backdrop.")

        if credit_spread is not None:
            if credit_spread >= 2.0:
                bearish_score += 1
                bearish_factors.append("Credit spreads are wide, suggesting tighter financial conditions.")
                risk_flags.append("Credit stress risk")
            elif credit_spread <= 1.2:
                bullish_score += 1
                bullish_factors.append("Credit spreads are tight, suggesting easier financial conditions.")

        if financial_stress_index is not None:
            if financial_stress_index > 0:
                bearish_score += 1
                bearish_factors.append("Financial stress is above neutral, which is a headwind for risk assets.")
                risk_flags.append("Financial stress risk")
            elif financial_stress_index < -0.5:
                bullish_score += 1
                bullish_factors.append("Financial stress remains subdued.")

        if housing_permits_growth is not None:
            if housing_permits_growth > 0:
                bullish_score += 1
                bullish_factors.append("Housing permits are improving, which supports cyclical growth.")
            elif housing_permits_growth < 0:
                bearish_score += 1
                bearish_factors.append("Housing permits are weakening, pointing to softer forward activity.")

        score_diff = bullish_score - bearish_score

        if score_diff >= 3:
            signal = "bullish"
        elif score_diff <= -3:
            signal = "bearish"
        else:
            signal = "neutral"

        confidence = min(0.90, 0.50 + abs(score_diff) * 0.03)

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
                "three_month_treasury": three_month_treasury,
                "two_year_treasury": two_year_treasury,
                "fed_funds_rate": fed_funds_rate,
                "inflation_rate": inflation_rate,
                "unemployment": unemployment,
                "labor_force_participation": labor_force_participation,
                "ten_year_treasury": ten_year_treasury,
                "yield_spread_10y2y": yield_spread_10y2y,
                "yield_spread_10y3m": yield_spread_10y3m,
                "vix": vix,
                "credit_spread": credit_spread,
                "financial_stress_index": financial_stress_index,
                "yield_curve_proxy": yield_curve_proxy,
                "gdp_growth": gdp_growth,
                "industrial_production_growth": industrial_production_growth,
                "retail_sales_growth": retail_sales_growth,
                "payroll_employment_growth": payroll_employment_growth,
                "consumer_sentiment": consumer_sentiment,
                "housing_permits_growth": housing_permits_growth,
            },
        )
