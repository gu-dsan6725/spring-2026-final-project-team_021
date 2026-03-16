"""
Technical Feature Builder

Summary
-------
This module loads historical OHLCV price data from parquet files and computes
technical indicators for a given stock.

Responsibilities
----------------
- Read price data for a selected ticker
- Compute trend and momentum indicators such as SMA, RSI, and MACD
- Build a single technical snapshot for one stock as of a chosen date

Output
------
A dictionary containing technical features that can be passed to the
Technical Analyst agent.
"""

from __future__ import annotations

import pandas as pd


def compute_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=window, min_periods=window).mean()
    avg_loss = loss.rolling(window=window, min_periods=window).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    ema_12 = series.ewm(span=12, adjust=False).mean()
    ema_26 = series.ewm(span=26, adjust=False).mean()
    macd = ema_12 - ema_26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal


def build_technical_snapshot(
    parquet_path: str,
    ticker: str,
    as_of_date: str | None = None,
) -> dict:
    df = pd.read_parquet(parquet_path)
    df = df[df["ticker"] == ticker].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    if df.empty:
        raise ValueError(f"No price data found for ticker={ticker}")

    close_col = "adj_close" if "adj_close" in df.columns else "close"

    df["sma_20"] = df[close_col].rolling(20).mean()
    df["sma_50"] = df[close_col].rolling(50).mean()
    df["return_5d"] = df[close_col].pct_change(5)
    df["return_20d"] = df[close_col].pct_change(20)
    df["volatility_20d"] = df[close_col].pct_change().rolling(20).std()
    df["avg_volume_20d"] = df["volume"].rolling(20).mean()
    df["rsi_14"] = compute_rsi(df[close_col], window=14)

    macd, macd_signal = compute_macd(df[close_col])
    df["macd"] = macd
    df["macd_signal"] = macd_signal

    if as_of_date is not None:
        as_of_date = pd.to_datetime(as_of_date)
        df = df[df["date"] <= as_of_date]

    row = df.iloc[-1]

    return {
        "ticker": ticker,
        "analysis_date": str(row["date"].date()),
        "price_features": {
            "close": float(row[close_col]),
            "sma_20": None if pd.isna(row["sma_20"]) else float(row["sma_20"]),
            "sma_50": None if pd.isna(row["sma_50"]) else float(row["sma_50"]),
            "return_5d": None if pd.isna(row["return_5d"]) else float(row["return_5d"]),
            "return_20d": None if pd.isna(row["return_20d"]) else float(row["return_20d"]),
            "volatility_20d": None if pd.isna(row["volatility_20d"]) else float(row["volatility_20d"]),
            "avg_volume_20d": None if pd.isna(row["avg_volume_20d"]) else float(row["avg_volume_20d"]),
            "latest_volume": float(row["volume"]),
            "rsi_14": None if pd.isna(row["rsi_14"]) else float(row["rsi_14"]),
            "macd": None if pd.isna(row["macd"]) else float(row["macd"]),
            "macd_signal": None if pd.isna(row["macd_signal"]) else float(row["macd_signal"]),
        },
    }