"""
Fundamental Feature Builder

Summary
-------
This module reads the Yahoo Finance fundamentals snapshot parquet file
and extracts a cleaned fundamental snapshot for a selected ticker.

Responsibilities
----------------
- Load point-in-time fundamental snapshot data
- Filter data for a target ticker
- Select the most useful fields for analysis
- Convert pandas/numpy values into JSON-safe Python types
- Return a single fundamental snapshot dictionary

Input
-----
- parquet_path: path to fundamentals snapshot parquet file
- ticker: stock ticker
- as_of_date: optional date filter; if omitted, use the latest available row

Output
------
A dictionary containing fundamental features for one ticker.
"""

from __future__ import annotations

import pandas as pd
import numpy as np


FUNDAMENTAL_COLUMNS = [
    "market_cap",
    "pe_ratio_ttm",
    "pe_ratio_forward",
    "price_to_book",
    "ev_to_revenue",
    "ev_to_ebitda",
    "eps_ttm",
    "eps_forward",
    "book_value_per_share",
    "revenue_growth_yoy",
    "earnings_growth_yoy",
    "gross_margin",
    "operating_margin",
    "net_margin",
    "debt_to_equity",
    "current_ratio",
    "quick_ratio",
    "roe",
    "roa",
    "total_revenue",
    "total_debt",
    "total_cash",
    "free_cash_flow",
    "operating_cash_flow",
    "beta",
    "dividend_yield",
    "payout_ratio",
]


def to_python_scalar(value):
    """
    Convert pandas/numpy scalar values into JSON-safe native Python types.
    """
    if pd.isna(value):
        return None

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        return float(value)

    if isinstance(value, np.bool_):
        return bool(value)

    return value


def build_fundamental_snapshot(
    parquet_path: str,
    ticker: str,
    as_of_date: str | None = None,
) -> dict:
    """
    Build a fundamental snapshot for a ticker.

    Parameters
    ----------
    parquet_path : str
        Path to Yahoo Finance fundamentals snapshot parquet file.
    ticker : str
        Stock ticker.
    as_of_date : str | None
        Optional date cutoff in YYYY-MM-DD format. If None, use latest row.

    Returns
    -------
    dict
        Fundamental snapshot dictionary.
    """
    df = pd.read_parquet(parquet_path)
    df["ticker"] = df["ticker"].astype(str).str.upper()
    ticker = ticker.upper()
    df = df[df["ticker"] == ticker].copy()

    if df.empty:
        raise ValueError(f"No fundamentals data found for ticker={ticker}")

    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df = df.sort_values("snapshot_date")

    if as_of_date is not None:
        cutoff = pd.to_datetime(as_of_date)
        df = df[df["snapshot_date"] <= cutoff].copy()

    if df.empty:
        raise ValueError(f"No fundamentals data found for ticker={ticker} on or before {as_of_date}")

    row = df.iloc[-1]

    features = {}
    for col in FUNDAMENTAL_COLUMNS:
        if col in df.columns:
            features[col] = to_python_scalar(row[col])

    company_name = row["company_name"] if "company_name" in row.index else None
    sector = row["sector"] if "sector" in row.index else None
    industry = row["industry"] if "industry" in row.index else None

    return {
        "ticker": ticker,
        "analysis_date": str(row["snapshot_date"].date()),
        "company_info": {
            "company_name": None if pd.isna(company_name) else str(company_name),
            "sector": None if pd.isna(sector) else str(sector),
            "industry": None if pd.isna(industry) else str(industry),
        },
        "fundamental_features": features,
    }