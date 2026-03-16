"""
Technical Feature Builder

Summary
-------
This module reads OHLCV price data from a parquet file and computes
technical indicators for a selected ticker as of a chosen date.

Responsibilities
----------------
- Load historical OHLCV price data
- Filter data for a target ticker
- Compute technical indicators such as SMA, EMA, RSI, MACD, returns,
  volatility, and volume ratio
- Return a single technical snapshot dictionary for downstream use

Input
-----
- parquet_path: path to OHLCV parquet file
- ticker: stock ticker
- as_of_date: optional end date for the snapshot

Output
------
A dictionary containing a technical feature snapshot for one ticker.
"""

from __future__ import annotations

import pandas as pd


def compute_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Compute Relative Strength Index (RSI)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=window, min_periods=window).mean()
    avg_loss = loss.rolling(window=window, min_periods=window).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Compute MACD and MACD signal line."""
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
    """
    Build a technical feature snapshot for a ticker.

    Parameters
    ----------
    parquet_path : str
        Path to OHLCV parquet file.
    ticker : str
        Stock ticker.
    as_of_date : str | None
        Optional date cutoff in YYYY-MM-DD format. If None, use latest date.

    Returns
    -------
    dict
        Technical snapshot dictionary.
    """
    df = pd.read_parquet(parquet_path)
    df["ticker"] = df["ticker"].astype(str).str.upper()
    ticker = ticker.upper()
    df = df[df["ticker"] == ticker].copy()

    if df.empty:
        raise ValueError(f"No price data found for ticker={ticker}")

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    if as_of_date is not None:
        cutoff = pd.to_datetime(as_of_date)
        df = df[df["date"] <= cutoff].copy()

    if df.empty:
        raise ValueError(f"No price data found for ticker={ticker} on or before {as_of_date}")

    close_col = "adj_close" if "adj_close" in df.columns else "close"

    df["sma_20"] = df[close_col].rolling(20).mean()
    df["sma_50"] = df[close_col].rolling(50).mean()
    df["ema_12"] = df[close_col].ewm(span=12, adjust=False).mean()
    df["ema_26"] = df[close_col].ewm(span=26, adjust=False).mean()
    df["return_5d"] = df[close_col].pct_change(5)
    df["return_20d"] = df[close_col].pct_change(20)
    df["volatility_20d"] = df[close_col].pct_change().rolling(20).std()
    df["avg_volume_20d"] = df["volume"].rolling(20).mean()
    df["volume_ratio_20d"] = df["volume"] / df["avg_volume_20d"]
    df["rsi_14"] = compute_rsi(df[close_col], window=14)

    macd, macd_signal = compute_macd(df[close_col])
    df["macd"] = macd
    df["macd_signal"] = macd_signal

    row = df.iloc[-1]

    def _safe_float(value):
        return None if pd.isna(value) else float(value)

    return {
        "ticker": ticker,
        "analysis_date": str(row["date"].date()),
        "price_features": {
            "close": _safe_float(row[close_col]),
            "sma_20": _safe_float(row["sma_20"]),
            "sma_50": _safe_float(row["sma_50"]),
            "ema_12": _safe_float(row["ema_12"]),
            "ema_26": _safe_float(row["ema_26"]),
            "return_5d": _safe_float(row["return_5d"]),
            "return_20d": _safe_float(row["return_20d"]),
            "volatility_20d": _safe_float(row["volatility_20d"]),
            "avg_volume_20d": _safe_float(row["avg_volume_20d"]),
            "latest_volume": _safe_float(row["volume"]),
            "volume_ratio_20d": _safe_float(row["volume_ratio_20d"]),
            "rsi_14": _safe_float(row["rsi_14"]),
            "macd": _safe_float(row["macd"]),
            "macd_signal": _safe_float(row["macd_signal"]),
        },
    }