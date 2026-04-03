"""
Fundamental Feature Builder

Summary
-------
Reads the integrated quarterly_fundamentals.parquet (produced by
fundamental_collector.py) and returns a standardised feature snapshot
for a given ticker as of a given analysis date.

Backtesting correctness
-----------------------
The filter applied is:

    filed_date <= as_of_date

NOT period_end <= as_of_date.  Filtering on period_end would use data
that may not yet have been publicly disclosed (e.g. a quarter ending
2025-09-28 whose 10-Q was filed 2025-11-05 would leak information for
any analysis_date between 2025-09-28 and 2025-11-04).

Responsibilities
----------------
- Load historical quarterly fundamental data
- Filter to rows available as of as_of_date (using filed_date)
- Select the most recently filed quarter for the target ticker
- Convert pandas/numpy values into JSON-safe native Python types
- Standardize percentage-like fields into decimal form
- Return both normalized and raw feature dictionaries for downstream use

Standardization Rules
---------------------
- Percentage-like fields (margins, growth rates) are normalized to decimal
  Example:  15.7  →  0.157   |   0.157  →  0.157
- Ratio / absolute-scale fields are kept as-is
  Example:  pe_ratio_ttm, debt_to_equity, total_revenue
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Columns available from quarterly_fundamentals.parquet
# ---------------------------------------------------------------------------

FUNDAMENTAL_COLUMNS = [
    # Raw income statement
    "revenue",
    "gross_profit",
    "cost_of_revenue",
    "operating_income",
    "ebitda",
    "net_income",
    "r_and_d_expense",
    "sga_expense",
    "interest_expense",
    "income_tax_expense",
    "depreciation_amortization",
    # Raw balance sheet
    "total_assets",
    "current_assets",
    "total_equity",
    "total_liabilities",
    "current_liabilities",
    "long_term_debt",
    "total_debt",
    "cash_and_equivalents",
    "inventory",
    "accounts_receivable",
    "retained_earnings",
    # Raw cash flow
    "operating_cash_flow",
    "free_cash_flow",
    "capex",
    "investing_cash_flow",
    "financing_cash_flow",
    # Per-share
    "eps_diluted",
    "shares_outstanding",
    # Derived margins (decimal form)
    "gross_margin",
    "operating_margin",
    "ebitda_margin",
    "net_margin",
    # Derived return ratios
    "roe",
    "roa",
    "asset_turnover",
    # Derived liquidity
    "current_ratio",
    "quick_ratio",
    "working_capital",
    # Derived leverage
    "debt_to_equity",
    "debt_ratio",
    "net_debt",
    "interest_coverage",
    # Derived efficiency
    "capex_to_revenue",
    # Derived growth (same-quarter YoY)
    "revenue_growth_yoy",
    "operating_income_growth_yoy",
    "net_income_growth_yoy",
]

# Computed ratios already expressed as decimals — pass through as-is.
ALREADY_DECIMAL_FIELDS = {
    "gross_margin",
    "operating_margin",
    "ebitda_margin",
    "net_margin",
    "roe",
    "roa",
    "asset_turnover",
    "current_ratio",
    "quick_ratio",
    "debt_to_equity",
    "debt_ratio",
    "interest_coverage",
    "capex_to_revenue",
    "revenue_growth_yoy",
    "operating_income_growth_yoy",
    "net_income_growth_yoy",
}

PERCENTAGE_MAY_NEED_SCALING_FIELDS: set[str] = set()

# Absolute-scale fields — leave unchanged.
RAW_SCALE_FIELDS = {
    "revenue", "gross_profit", "cost_of_revenue", "operating_income",
    "ebitda", "net_income", "r_and_d_expense", "sga_expense",
    "interest_expense", "income_tax_expense", "depreciation_amortization",
    "total_assets", "current_assets", "total_equity", "total_liabilities",
    "current_liabilities", "long_term_debt", "total_debt",
    "cash_and_equivalents", "inventory", "accounts_receivable",
    "retained_earnings", "operating_cash_flow", "free_cash_flow",
    "capex", "investing_cash_flow", "financing_cash_flow",
    "eps_diluted", "shares_outstanding", "working_capital", "net_debt",
}


# ---------------------------------------------------------------------------
# Scalar conversion helpers
# ---------------------------------------------------------------------------

def to_python_scalar(value):
    """Convert pandas/numpy scalars to JSON-safe native Python types."""
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
    Normalize a value that *might* be expressed as a whole percentage to
    decimal form.

    Examples
    --------
    15.7   → 0.157
    0.157  → 0.157
    152    → 1.52
    -12.0  → -0.12
    """
    if value is None:
        return None
    if abs(value) > 1:
        return value / 100.0
    return value


def normalize_fundamental_value(field_name: str, value) -> float | None:
    """Normalize a raw fundamental value to the project's internal scale."""
    value = to_python_scalar(value)
    if value is None:
        return None
    if field_name in ALREADY_DECIMAL_FIELDS:
        return value
    if field_name in PERCENTAGE_MAY_NEED_SCALING_FIELDS:
        return normalize_percentage_like(value)
    return value


def _read_fundamental_table(path: str) -> pd.DataFrame:
    """Read fundamentals input from parquet or CSV based on file suffix."""
    file_path = Path(path)
    if file_path.suffix.lower() == ".csv":
        return pd.read_csv(file_path)
    return pd.read_parquet(file_path)


def _snapshot_from_row(row, ticker: str | None = None) -> dict:
    """Build the standard snapshot dictionary from a selected fundamentals row."""
    resolved_ticker = ticker or str(row["ticker"]).upper()

    raw_features: dict = {}
    normalized_features: dict = {}
    for col in FUNDAMENTAL_COLUMNS:
        if col in row.index:
            raw_value = to_python_scalar(row[col])
            raw_features[col] = raw_value
            normalized_features[col] = normalize_fundamental_value(col, raw_value)

    period_end = row["period_end"] if "period_end" in row.index else None
    fiscal_year = row["fiscal_year"] if "fiscal_year" in row.index else None
    fiscal_period = row["fiscal_period"] if "fiscal_period" in row.index else None
    filed_date = pd.to_datetime(row["filed_date"]).date()

    return {
        "ticker": resolved_ticker,
        "analysis_date": str(filed_date),
        "period_end": (
            str(pd.to_datetime(period_end).date())
            if period_end is not None and not pd.isna(period_end)
            else None
        ),
        "fiscal_info": {
            "fiscal_year": None if fiscal_year is None or pd.isna(fiscal_year) else int(fiscal_year),
            "fiscal_period": None if fiscal_period is None or pd.isna(fiscal_period) else str(fiscal_period),
        },
        "fundamental_features": normalized_features,
        "raw_fundamental_features": raw_features,
    }


def build_fundamental_snapshot_from_row(row, ticker: str | None = None) -> dict:
    """Build a standardized fundamental snapshot directly from one row."""
    if isinstance(row, dict):
        row = pd.Series(row)
    return _snapshot_from_row(row=row, ticker=ticker)


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_fundamental_snapshot(
    parquet_path: str,
    ticker: str,
    as_of_date: str | None = None,
) -> dict:
    """
    Build a standardized fundamental snapshot for *ticker* as of *as_of_date*.

    Parameters
    ----------
    parquet_path : str
        Path to quarterly_fundamentals.parquet (produced by
        fundamental_collector.py).
    ticker : str
        Stock ticker symbol (case-insensitive).
    as_of_date : str | None
        Analysis date in YYYY-MM-DD format.
        Only rows where ``filed_date <= as_of_date`` are considered, which
        prevents any look-ahead bias.  If None, the most recent row is used.

    Returns
    -------
    dict with keys:
        ticker            : str
        analysis_date     : str   (filed_date of the selected row)
        period_end        : str   (fiscal quarter end date of the selected row)
        fiscal_info       : dict  (fiscal_year, fiscal_period)
        fundamental_features      : dict  (normalized values)
        raw_fundamental_features  : dict  (raw source values)
    """
    df = _read_fundamental_table(parquet_path)
    df["ticker"] = df["ticker"].astype(str).str.upper()
    ticker = ticker.upper()

    df = df[df["ticker"] == ticker].copy()
    if df.empty:
        available = sorted(
            _read_fundamental_table(parquet_path)["ticker"]
            .astype(str)
            .str.upper()
            .dropna()
            .unique()
            .tolist()
        )
        raise ValueError(
            f"No fundamentals data found for ticker={ticker}. "
            f"Available tickers: {available}"
        )

    # Use filed_date for backtesting-safe filtering
    df["filed_date"] = pd.to_datetime(df["filed_date"])
    df = df.sort_values("filed_date")

    if as_of_date is not None:
        cutoff = pd.to_datetime(as_of_date)
        df = df[df["filed_date"] <= cutoff].copy()

    if df.empty:
        full_df = _read_fundamental_table(parquet_path)
        full_df["ticker"] = full_df["ticker"].astype(str).str.upper()
        earliest_filed = full_df[full_df["ticker"] == ticker]["filed_date"].min()
        raise ValueError(
            f"No fundamentals data available for ticker={ticker} "
            f"with filed_date <= {as_of_date}. "
            f"Earliest filed_date in dataset: "
            f"{earliest_filed}"
        )

    # Most recently filed row (latest information available as of as_of_date)
    row = df.iloc[-1]
    return _snapshot_from_row(row=row, ticker=ticker)
