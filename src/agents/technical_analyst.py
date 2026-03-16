"""
Technical Analyst Agent

Summary
-------
This module implements the Technical Analyst agent for DebateTrader.

Responsibilities
----------------
- Receive a technical snapshot containing price-derived indicators
- Evaluate trend, momentum, and overbought/oversold conditions
- Produce a structured JSON-friendly analysis report

Current Version
---------------
This version is rule-based and does not require an LLM. It is designed
to be stable, interpretable, and easy to integrate into later system stages.
"""

from __future__ import annotations

from src.schemas.analyst_output import AnalystOutput


class TechnicalAnalyst:
    """Rule-based technical analyst agent."""

    def analyze(self, snapshot: dict) -> AnalystOutput:
        ticker = snapshot["ticker"]
        analysis_date = snapshot["analysis_date"]
        f = snapshot["price_features"]

        bullish_factors: list[str] = []
        bearish_factors: list[str] = []
        risk_flags: list[str] = []

        bullish_score = 0
        bearish_score = 0

        close = f.get("close")
        sma_20 = f.get("sma_20")
        sma_50 = f.get("sma_50")
        ema_12 = f.get("ema_12")
        ema_26 = f.get("ema_26")
        rsi_14 = f.get("rsi_14")
        macd = f.get("macd")
        macd_signal = f.get("macd_signal")
        return_5d = f.get("return_5d")
        return_20d = f.get("return_20d")
        volatility_20d = f.get("volatility_20d")
        volume_ratio_20d = f.get("volume_ratio_20d")

        if sma_20 is not None and close is not None:
            if close > sma_20:
                bullish_score += 1
                bullish_factors.append("Price is above the 20-day moving average.")
            elif close < sma_20:
                bearish_score += 1
                bearish_factors.append("Price is below the 20-day moving average.")

        if sma_20 is not None and sma_50 is not None:
            if sma_20 > sma_50:
                bullish_score += 1
                bullish_factors.append("The 20-day moving average is above the 50-day moving average.")
            elif sma_20 < sma_50:
                bearish_score += 1
                bearish_factors.append("The 20-day moving average is below the 50-day moving average.")

        if ema_12 is not None and ema_26 is not None:
            if ema_12 > ema_26:
                bullish_score += 1
                bullish_factors.append("The 12-day EMA is above the 26-day EMA, supporting positive momentum.")
            elif ema_12 < ema_26:
                bearish_score += 1
                bearish_factors.append("The 12-day EMA is below the 26-day EMA, suggesting weak momentum.")

        if macd is not None and macd_signal is not None:
            if macd > macd_signal:
                bullish_score += 1
                bullish_factors.append("MACD is above its signal line, indicating positive momentum.")
            elif macd < macd_signal:
                bearish_score += 1
                bearish_factors.append("MACD is below its signal line, indicating weakening momentum.")

        if return_5d is not None:
            if return_5d > 0:
                bullish_score += 1
                bullish_factors.append("The stock has positive 5-day return momentum.")
            elif return_5d < 0:
                bearish_score += 1
                bearish_factors.append("The stock has negative 5-day return momentum.")

        if return_20d is not None:
            if return_20d > 0:
                bullish_score += 1
                bullish_factors.append("The stock has positive 20-day return momentum.")
            elif return_20d < 0:
                bearish_score += 1
                bearish_factors.append("The stock has negative 20-day return momentum.")

        if rsi_14 is not None:
            if rsi_14 > 70:
                bearish_score += 1
                bearish_factors.append("RSI is above 70, suggesting overbought conditions.")
                risk_flags.append("Overbought risk")
            elif rsi_14 < 30:
                bullish_score += 1
                bullish_factors.append("RSI is below 30, suggesting oversold conditions and rebound potential.")
                risk_flags.append("Oversold volatility risk")

        if volatility_20d is not None and volatility_20d > 0.04:
            risk_flags.append("Elevated short-term volatility")

        if volume_ratio_20d is not None and volume_ratio_20d > 1.5:
            bullish_factors.append("Recent trading volume is meaningfully above its 20-day average.")
        elif volume_ratio_20d is not None and volume_ratio_20d < 0.7:
            risk_flags.append("Low relative trading volume")

        score_diff = bullish_score - bearish_score

        if score_diff >= 2:
            signal = "bullish"
        elif score_diff <= -2:
            signal = "bearish"
        else:
            signal = "neutral"

        confidence = min(0.95, 0.50 + abs(score_diff) * 0.08)

        if signal == "bullish":
            summary = "Technical indicators are broadly supportive, with stronger bullish than bearish evidence."
        elif signal == "bearish":
            summary = "Technical indicators are broadly weak, with stronger bearish than bullish evidence."
        else:
            summary = "Technical indicators are mixed, without a strong directional edge."

        return AnalystOutput(
            agent_name="TechnicalAnalyst",
            ticker=ticker,
            analysis_date=analysis_date,
            signal=signal,
            confidence=round(confidence, 2),
            summary=summary,
            bullish_factors=bullish_factors,
            bearish_factors=bearish_factors,
            risk_flags=sorted(set(risk_flags)),
            key_metrics_used={
                "close": close,
                "sma_20": sma_20,
                "sma_50": sma_50,
                "ema_12": ema_12,
                "ema_26": ema_26,
                "rsi_14": rsi_14,
                "macd": macd,
                "macd_signal": macd_signal,
                "return_5d": return_5d,
                "return_20d": return_20d,
                "volatility_20d": volatility_20d,
                "volume_ratio_20d": volume_ratio_20d,
            },
        )