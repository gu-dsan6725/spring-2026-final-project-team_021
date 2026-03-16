"""
Fundamental Feature Builder

Summary
-------
This module reads the Yahoo Finance fundamentals snapshot parquet file
and extracts a cleaned and standardized fundamental snapshot for a
selected ticker.

Responsibilities
----------------
- Load point-in-time fundamental snapshot data
- Filter data for a target ticker
- Select the most useful fields for analysis
- Convert pandas/numpy values into JSON-safe native Python types
- Standardize percentage-like fields into decimal form
- Return both normalized and raw feature dictionaries for downstream use

Standardization Rules
---------------------
- Percentage-like fields are normalized to decimal form
  Example:
    15.7   -> 0.157
    0.157  -> 0.157
    152    -> 1.52
- Ratio / multiple fields are kept in their original numeric scale
  Example:
    pe_ratio_ttm, debt_to_equity, current_ratio
"""

from __future__ import annotations

import numpy as np
import pandas as pd


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

ALREADY_DECIMAL_FIELDS = {
    "gross_margin",
    "operating_margin",
    "net_margin",
    "roa",
    "roe",
}

PERCENTAGE_MAY_NEED_SCALING_FIELDS = {
    "revenue_growth_yoy",
    "earnings_growth_yoy",
    "dividend_yield",
    "payout_ratio",
}

RAW_SCALE_FIELDS = {
    "market_cap",
    "pe_ratio_ttm",
    "pe_ratio_forward",
    "price_to_book",
    "ev_to_revenue",
    "ev_to_ebitda",
    "eps_ttm",
    "eps_forward",
    "book_value_per_share",
    "debt_to_equity",
    "current_ratio",
    "quick_ratio",
    "total_revenue",
    "total_debt",
    "total_cash",
    "free_cash_flow",
    "operating_cash_flow",
    "beta",
}


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


def normalize_percentage_like(value: float | int | None) -> float | None:
    """
    Normalize percentage-like values to decimal form.

    Examples
    --------
    15.7   -> 0.157
    0.157  -> 0.157
    152    -> 1.52
    0.42   -> 0.42
    -12.0  -> -0.12
    """
    if value is None:
        return None

    if abs(value) > 1:
        return value / 100.0

    return value


def normalize_fundamental_value(field_name: str, value):
    """
    Normalize a raw fundamental value into the project's internal scale.
    """
    value = to_python_scalar(value)

    if value is None:
        return None

    if field_name in ALREADY_DECIMAL_FIELDS:
        return value

    if field_name in PERCENTAGE_MAY_NEED_SCALING_FIELDS:
        return normalize_percentage_like(value)

    return value


def build_fundamental_snapshot(
    parquet_path: str,
    ticker: str,
    as_of_date: str | None = None,
) -> dict:
    """
    Build a standardized fundamental snapshot for a ticker.

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
        Fundamental snapshot dictionary containing:
        - ticker
        - analysis_date
        - company_info
        - fundamental_features (normalized)
        - raw_fundamental_features (raw source values)
    """
    df = pd.read_parquet(parquet_path)
    df["ticker"] = df["ticker"].astype(str).str.upper()
    ticker = ticker.upper()

    df = df[df["ticker"] == ticker].copy()

    if df.empty:
        available_tickers = sorted(
            pd.read_parquet(parquet_path)["ticker"]
            .astype(str)
            .str.upper()
            .dropna()
            .unique()
            .tolist()
        )
        raise ValueError(
            f"No fundamentals data found for ticker={ticker}. "
            f"Available tickers in fundamentals parquet: {available_tickers}"
        )

    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df = df.sort_values("snapshot_date")

    if as_of_date is not None:
        cutoff = pd.to_datetime(as_of_date)
        df = df[df["snapshot_date"] <= cutoff].copy()

    if df.empty:
        raise ValueError(
            f"No fundamentals data found for ticker={ticker} on or before {as_of_date}"
        )

    row = df.iloc[-1]

    raw_features = {}
    normalized_features = {}

    for col in FUNDAMENTAL_COLUMNS:
        if col in df.columns:
            raw_value = to_python_scalar(row[col])
            raw_features[col] = raw_value
            normalized_features[col] = normalize_fundamental_value(col, raw_value)

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
        "fundamental_features": normalized_features,
        "raw_fundamental_features": raw_features,
    }