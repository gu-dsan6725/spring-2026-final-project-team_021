"""
Technical Analyst Agent

Summary
-------
This module implements the Technical Analyst agent for DebateTrader.

Current Version
---------------
This version uses a hybrid design:
- deterministic rules extract bullish/bearish factors and risk flags
- an LLM synthesizes the final signal, confidence, and summary
"""

from __future__ import annotations

import json

from src.prompts.technical_prompt import TECHNICAL_SYSTEM_PROMPT
from src.schemas.analyst_output import AnalystOutput
from src.tools.llm_client import call_llm


class TechnicalAnalyst:
    """Hybrid technical analyst agent."""

    def _extract_evidence(self, snapshot: dict) -> tuple[list[str], list[str], list[str], dict]:
        f = snapshot["price_features"]

        bullish_factors: list[str] = []
        bearish_factors: list[str] = []
        risk_flags: list[str] = []

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
                bullish_factors.append("Price is above the 20-day moving average.")
            elif close < sma_20:
                bearish_factors.append("Price is below the 20-day moving average.")

        if sma_20 is not None and sma_50 is not None:
            if sma_20 > sma_50:
                bullish_factors.append("The 20-day moving average is above the 50-day moving average.")
            elif sma_20 < sma_50:
                bearish_factors.append("The 20-day moving average is below the 50-day moving average.")

        if ema_12 is not None and ema_26 is not None:
            if ema_12 > ema_26:
                bullish_factors.append("The 12-day EMA is above the 26-day EMA, supporting positive momentum.")
            elif ema_12 < ema_26:
                bearish_factors.append("The 12-day EMA is below the 26-day EMA, suggesting weak momentum.")

        if macd is not None and macd_signal is not None:
            if macd > macd_signal:
                bullish_factors.append("MACD is above its signal line, indicating positive momentum.")
            elif macd < macd_signal:
                bearish_factors.append("MACD is below its signal line, indicating weakening momentum.")

        if return_5d is not None:
            if return_5d > 0:
                bullish_factors.append("The stock has positive 5-day return momentum.")
            elif return_5d < 0:
                bearish_factors.append("The stock has negative 5-day return momentum.")

        if return_20d is not None:
            if return_20d > 0:
                bullish_factors.append("The stock has positive 20-day return momentum.")
            elif return_20d < 0:
                bearish_factors.append("The stock has negative 20-day return momentum.")

        if rsi_14 is not None:
            if rsi_14 > 70:
                bearish_factors.append("RSI is above 70, suggesting overbought conditions.")
                risk_flags.append("Overbought risk")
            elif rsi_14 < 30:
                bullish_factors.append("RSI is below 30, suggesting oversold conditions and rebound potential.")
                risk_flags.append("Oversold volatility risk")

        if volatility_20d is not None and volatility_20d > 0.04:
            risk_flags.append("Elevated short-term volatility")

        if volume_ratio_20d is not None and volume_ratio_20d > 1.5:
            bullish_factors.append("Recent trading volume is meaningfully above its 20-day average.")
        elif volume_ratio_20d is not None and volume_ratio_20d < 0.7:
            risk_flags.append("Low relative trading volume")

        key_metrics_used = {
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
        }

        return bullish_factors, bearish_factors, sorted(set(risk_flags)), key_metrics_used

    def _build_prompt(
        self,
        ticker: str,
        analysis_date: str,
        bullish_factors: list[str],
        bearish_factors: list[str],
        risk_flags: list[str],
        key_metrics_used: dict,
    ) -> str:
        payload = {
            "ticker": ticker,
            "analysis_date": analysis_date,
            "bullish_factors": bullish_factors,
            "bearish_factors": bearish_factors,
            "risk_flags": risk_flags,
            "key_metrics_used": key_metrics_used,
        }
        return json.dumps(payload, indent=2, ensure_ascii=False, default=str)

    def analyze(self, snapshot: dict) -> AnalystOutput:
        ticker = snapshot["ticker"]
        analysis_date = snapshot["analysis_date"]

        bullish_factors, bearish_factors, risk_flags, key_metrics_used = self._extract_evidence(snapshot)

        user_prompt = self._build_prompt(
            ticker=ticker,
            analysis_date=analysis_date,
            bullish_factors=bullish_factors,
            bearish_factors=bearish_factors,
            risk_flags=risk_flags,
            key_metrics_used=key_metrics_used,
        )

        raw_output = call_llm(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=TECHNICAL_SYSTEM_PROMPT,
        )

        parsed = json.loads(raw_output)

        return AnalystOutput(
            agent_name="TechnicalAnalyst",
            ticker=ticker,
            analysis_date=analysis_date,
            signal=parsed["signal"],
            confidence=round(float(parsed["confidence"]), 2),
            summary=parsed["summary"],
            bullish_factors=bullish_factors,
            bearish_factors=bearish_factors,
            risk_flags=risk_flags,
            key_metrics_used=key_metrics_used,
        )