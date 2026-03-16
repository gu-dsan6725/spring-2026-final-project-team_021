"""
Technical Analyst Agent

Summary
-------
This module implements the Technical Analyst agent for the trading system.

Responsibilities
- Receive a technical snapshot (price + indicators)
- Evaluate technical signals (trend, momentum, RSI)
- Produce a structured analysis report

Input
- snapshot dictionary from technical_features.py

Output
- AnalystOutput object containing signal, confidence, and explanation
"""

from __future__ import annotations

from src.schemas.analyst_output import AnalystOutput


class TechnicalAnalyst:
    def analyze(self, snapshot: dict) -> AnalystOutput:
        ticker = snapshot["ticker"]
        f = snapshot["price_features"]

        bullish_factors = []
        bearish_factors = []
        risk_flags = []

        bullish_score = 0
        bearish_score = 0

        close = f["close"]
        sma_20 = f["sma_20"]
        sma_50 = f["sma_50"]
        rsi_14 = f["rsi_14"]
        macd = f["macd"]
        macd_signal = f["macd_signal"]
        return_20d = f["return_20d"]

        if sma_20 is not None and close > sma_20:
            bullish_score += 1
            bullish_factors.append("Price is above the 20-day moving average.")
        elif sma_20 is not None and close < sma_20:
            bearish_score += 1
            bearish_factors.append("Price is below the 20-day moving average.")

        if sma_20 is not None and sma_50 is not None and sma_20 > sma_50:
            bullish_score += 1
            bullish_factors.append("The 20-day moving average is above the 50-day moving average.")
        elif sma_20 is not None and sma_50 is not None and sma_20 < sma_50:
            bearish_score += 1
            bearish_factors.append("The 20-day moving average is below the 50-day moving average.")

        if macd is not None and macd_signal is not None and macd > macd_signal:
            bullish_score += 1
            bullish_factors.append("MACD is above its signal line, indicating positive momentum.")
        elif macd is not None and macd_signal is not None and macd < macd_signal:
            bearish_score += 1
            bearish_factors.append("MACD is below its signal line, indicating weakening momentum.")

        if return_20d is not None and return_20d > 0:
            bullish_score += 1
            bullish_factors.append("The stock has positive 20-day return momentum.")
        elif return_20d is not None and return_20d < 0:
            bearish_score += 1
            bearish_factors.append("The stock has negative 20-day return momentum.")

        if rsi_14 is not None and rsi_14 > 70:
            bearish_score += 1
            bearish_factors.append("RSI is above 70, suggesting overbought conditions.")
            risk_flags.append("Overbought risk")
        elif rsi_14 is not None and rsi_14 < 30:
            bullish_score += 1
            bullish_factors.append("RSI is below 30, suggesting oversold conditions and rebound potential.")
            risk_flags.append("Oversold volatility risk")

        score_diff = bullish_score - bearish_score

        if score_diff >= 2:
            signal = "bullish"
        elif score_diff <= -2:
            signal = "bearish"
        else:
            signal = "neutral"

        confidence = min(0.95, 0.5 + abs(score_diff) * 0.1)

        if signal == "bullish":
            summary = "Technical indicators are broadly supportive, with stronger bullish than bearish evidence."
        elif signal == "bearish":
            summary = "Technical indicators are broadly weak, with stronger bearish than bullish evidence."
        else:
            summary = "Technical indicators are mixed, without a strong directional edge."

        return AnalystOutput(
            agent_name="TechnicalAnalyst",
            ticker=ticker,
            signal=signal,
            confidence=confidence,
            summary=summary,
            bullish_factors=bullish_factors,
            bearish_factors=bearish_factors,
            risk_flags=risk_flags,
            key_metrics_used={
                "close": close,
                "sma_20": sma_20,
                "sma_50": sma_50,
                "rsi_14": rsi_14,
                "macd": macd,
                "macd_signal": macd_signal,
                "return_20d": return_20d,
            },
        )