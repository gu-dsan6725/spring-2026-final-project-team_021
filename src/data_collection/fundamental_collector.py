"""Integrated fundamental data collector for DebateTrader.

Merges two sources into a single historical quarterly time series:

  1. SEC EDGAR XBRL companyfacts API  ── PRIMARY / AUTHORITATIVE
       Income statement : revenue, gross_profit, cost_of_revenue,
                          operating_income, net_income, r_and_d_expense,
                          sga_expense, interest_expense, income_tax_expense,
                          depreciation_amortization
       Balance sheet    : total_assets, current_assets, total_equity,
                          total_liabilities, current_liabilities,
                          long_term_debt, inventory, accounts_receivable,
                          retained_earnings
       Cash flow        : capex, shares_outstanding

  2. Yahoo Finance quarterly statements  ── SUPPLEMENTARY
       Income statement : gross_profit, ebitda, interest_expense,
                          income_tax_expense, eps_diluted, shares_outstanding,
                          depreciation_amortization
       Balance sheet    : total_debt, cash_and_equivalents, current_assets,
                          current_liabilities, inventory, accounts_receivable,
                          long_term_debt, retained_earnings
       Cash flow        : free_cash_flow, operating_cash_flow, capex,
                          investing_cash_flow, financing_cash_flow

Merge rule
----------
SEC EDGAR values take precedence wherever both sources provide the same
metric.  Yahoo Finance fills gaps with supplementary figures.
All derived ratios are computed from the merged raw figures so they are
internally consistent.

Backtesting / look-ahead note
------------------------------
Each row carries TWO dates:

  period_end  — when the fiscal quarter ended (period identifier)
  filed_date  — when the 10-Q / 10-K was publicly filed with the SEC

Downstream consumers MUST filter rows so that  filed_date <= analysis_date
to avoid any look-ahead bias.  Using period_end as the filter would be
incorrect and would leak future information into the model.

Output
------
data/sample/fundamentals/quarterly_fundamentals.parquet

Raw fields (26)
---------------
revenue, gross_profit, cost_of_revenue, operating_income, net_income,
ebitda, r_and_d_expense, sga_expense, interest_expense, income_tax_expense,
depreciation_amortization,
total_assets, current_assets, total_equity, total_liabilities,
current_liabilities, long_term_debt, total_debt, cash_and_equivalents,
inventory, accounts_receivable, retained_earnings,
free_cash_flow, operating_cash_flow, capex,
investing_cash_flow, financing_cash_flow,
eps_diluted, shares_outstanding

Derived ratios (14)
-------------------
gross_margin, operating_margin, ebitda_margin, net_margin,
roe, roa, asset_turnover,
current_ratio, quick_ratio,
debt_to_equity, debt_ratio, net_debt,
interest_coverage, capex_to_revenue,
revenue_growth_yoy, net_income_growth_yoy, operating_income_growth_yoy
"""
from __future__ import annotations

import sys
import os
import time
import logging
from typing import Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from src.data_collection.config import (
    TICKERS,
    YFINANCE_TICKER_MAP,
    SAMPLE_END,
    FUNDAMENTALS_DIR,
    FUNDAMENTAL_HISTORY_YEARS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEC_HEADERS = {"User-Agent": "DebateTrader Research (lh1085@georgetown.edu)"}
SEC_RATE_SLEEP = 0.2          # seconds between SEC API calls (be polite)
# FUNDAMENTAL_HISTORY_YEARS is imported from config.py

# SEC EDGAR sometimes uses different ticker symbols
SEC_TICKER_MAP = {"BRK.B": "BRK-B"}

# Internal key columns used for all merges
_KEY_COLS = ["period_end", "fiscal_year", "fiscal_period"]

# Minimum / maximum days in a "one quarter" duration window.
# Filters out YTD / full-year accumulations from income-statement XBRL entries.
_QUARTER_DAYS_MIN = 60
_QUARTER_DAYS_MAX = 120

# Duration window for annual (10-K) filings used in Q4 derivation.
_ANNUAL_DAYS_MIN = 330
_ANNUAL_DAYS_MAX = 400

# Flow metrics: Q4 = Annual − (Q1+Q2+Q3).  Balance-sheet metrics are
# instantaneous, so Q4 value = the annual year-end value directly.
_FLOW_METRICS = frozenset([
    "revenue", "gross_profit", "cost_of_revenue", "operating_income",
    "net_income", "r_and_d_expense", "sga_expense", "interest_expense",
    "income_tax_expense", "depreciation_amortization", "capex",
    "ebitda", "free_cash_flow", "operating_cash_flow",
    "investing_cash_flow", "financing_cash_flow",
])

# ---------------------------------------------------------------------------
# SEC EDGAR helpers
# ---------------------------------------------------------------------------


def _get_cik_map() -> dict[str, str]:
    """Fetch SEC company_tickers.json → {TICKER: zero-padded CIK}."""
    r = requests.get(
        "https://www.sec.gov/files/company_tickers.json",
        headers=SEC_HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    return {
        item["ticker"]: str(item["cik_str"]).zfill(10)
        for item in r.json().values()
    }


def _get_companyfacts(cik: str) -> Optional[dict]:
    """Fetch XBRL companyfacts JSON for one CIK."""
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    r = requests.get(url, headers=SEC_HEADERS, timeout=30)
    if r.status_code != 200:
        logger.warning(f"  SEC returned {r.status_code} for CIK {cik}")
        return None
    return r.json()


def _extract_sec_series(
    facts: dict,
    concepts: list[str],
    start_year: int,
    is_flow: bool = True,
) -> Optional[pd.DataFrame]:
    """
    Try each GAAP concept in *concepts* order; return the first non-empty
    quarterly series as a DataFrame.

    Parameters
    ----------
    is_flow : bool
        True  → income-statement concept (duration ~90 days).
                 Entries whose reported period spans more than one quarter
                 (e.g. YTD 9-month values) are dropped.
        False → balance-sheet concept (instantaneous; no duration filter).

    Returns
    -------
    DataFrame with columns:
        period_end (datetime64[ns])
        filed_date (datetime64[ns])   ← public availability date
        fiscal_year  (int)
        fiscal_period (str, e.g. "Q1")
        <concept_name> (float)
    or None if no valid data found.
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})

    for concept in concepts:
        if concept not in us_gaap:
            continue
        usd_units = us_gaap[concept].get("units", {}).get("USD")
        if not usd_units:
            continue

        df = pd.DataFrame(usd_units)

        # Require minimum columns
        needed = {"end", "val", "fp", "fy", "form", "filed"}
        if not needed.issubset(df.columns):
            continue

        # --- Filter: quarterly fiscal periods only ---
        df = df[df["fp"].isin(["Q1", "Q2", "Q3", "Q4"])].copy()
        # Keep only standard US annual / quarterly filings
        df = df[df["form"].isin(["10-Q", "10-K"])].copy()
        # Fiscal year scope
        df["_fy_int"] = pd.to_numeric(df["fy"], errors="coerce")
        df = df[df["_fy_int"] >= start_year].copy()

        if df.empty:
            continue

        df["period_end"] = pd.to_datetime(df["end"])
        df["filed_date"] = pd.to_datetime(df["filed"])
        df["fiscal_year"] = df["_fy_int"].astype(int)
        df["fiscal_period"] = df["fp"].astype(str)
        df["val"] = pd.to_numeric(df["val"], errors="coerce")
        df = df.drop(columns=["_fy_int"])

        # --- Sanity check: period_end year must be within ±1 of fiscal_year ---
        # Rejects mislabeled XBRL entries (e.g. comparative-period data tagged
        # with the current fiscal_year) that would corrupt Q1–Q3 sums.
        # Allows a 1-year gap for companies like AAPL whose Q1 ends in
        # December of the prior calendar year (fiscal_year=2022, period_end.year=2021).
        df = df[abs(df["period_end"].dt.year - df["fiscal_year"]) <= 1].copy()

        # --- For flow metrics: drop YTD / annual accumulations ---
        # Many companies report both a 9-month YTD figure (in 10-Q) and a
        # Q3-only figure; the `start` field lets us compute the duration.
        if is_flow and "start" in df.columns:
            df["_start"] = pd.to_datetime(df["start"], errors="coerce")
            df["_dur"] = (df["period_end"] - df["_start"]).dt.days
            df = df[
                (df["_dur"] >= _QUARTER_DAYS_MIN) & (df["_dur"] <= _QUARTER_DAYS_MAX)
            ].copy()
            df = df.drop(columns=["_start", "_dur"])

        if df.empty:
            continue

        # --- Deduplicate ---
        # Step 1: same (period_end, fp, fy) → keep latest filed_date (handles amendments)
        df = df.sort_values("filed_date").drop_duplicates(
            subset=["period_end", "fiscal_period", "fiscal_year"], keep="last"
        )
        # Step 2: same (fp, fy) → pick the row with the LATEST period_end.
        #
        # Flow metrics (is_flow=True): period_end is driven by the reporting window;
        #   latest filed_date = most recently amended figure → sort by filed_date.
        # Balance-sheet metrics (is_flow=False): multiple period_end values appear
        #   for the same (fy, fp) because 10-Q filings include both the CURRENT
        #   quarter-end date AND the prior year-end as a comparative column.
        #   The correct row is always the one with the LATER period_end (actual
        #   quarter end), not the comparative prior-year-end.  Sort by period_end.
        if is_flow:
            df = df.sort_values("filed_date").drop_duplicates(
                subset=["fiscal_year", "fiscal_period"], keep="last"
            )
        else:
            df = df.sort_values("period_end").drop_duplicates(
                subset=["fiscal_year", "fiscal_period"], keep="last"
            )

        df = (
            df[["period_end", "filed_date", "fiscal_year", "fiscal_period", "val"]]
            .rename(columns={"val": concept})
            .reset_index(drop=True)
        )
        logger.debug(f"    SEC concept={concept}  rows={len(df)}")
        return df

    return None


def _extract_sec_annual_series(
    facts: dict,
    concepts: list[str],
    start_year: int,
    is_flow: bool = True,
) -> Optional[pd.DataFrame]:
    """
    Extract full-year (10-K) data for a metric.  Used to derive Q4 values.

    Returns a DataFrame with columns:
        period_end, filed_date, fiscal_year, <concept_name>
    One row per fiscal_year (latest 10-K if multiple).
    Returns None if no valid annual data found.
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})

    for concept in concepts:
        if concept not in us_gaap:
            continue
        usd_units = us_gaap[concept].get("units", {}).get("USD")
        if not usd_units:
            continue

        df = pd.DataFrame(usd_units)
        needed = {"end", "val", "fp", "fy", "form", "filed"}
        if not needed.issubset(df.columns):
            continue

        # Annual 10-K rows only
        df = df[(df["fp"] == "FY") & (df["form"] == "10-K")].copy()
        df["_fy_int"] = pd.to_numeric(df["fy"], errors="coerce")
        df = df[df["_fy_int"] >= start_year].copy()

        if df.empty:
            continue

        df["period_end"] = pd.to_datetime(df["end"])
        df["filed_date"] = pd.to_datetime(df["filed"])
        df["fiscal_year"] = df["_fy_int"].astype(int)
        df["val"] = pd.to_numeric(df["val"], errors="coerce")
        df = df.drop(columns=["_fy_int"])

        # Sanity check: period_end year must be within ±1 of fiscal_year
        df = df[abs(df["period_end"].dt.year - df["fiscal_year"]) <= 1].copy()

        # For flow metrics: keep only full-year durations (~365 days)
        if is_flow and "start" in df.columns:
            df["_start"] = pd.to_datetime(df["start"], errors="coerce")
            df["_dur"] = (df["period_end"] - df["_start"]).dt.days
            df = df[
                (df["_dur"] >= _ANNUAL_DAYS_MIN) & (df["_dur"] <= _ANNUAL_DAYS_MAX)
            ].copy()
            df = df.drop(columns=["_start", "_dur"])

        if df.empty:
            continue

        # One row per fiscal_year: keep latest filed_date
        df = df.sort_values("filed_date").drop_duplicates(
            subset=["fiscal_year"], keep="last"
        )

        df = (
            df[["period_end", "filed_date", "fiscal_year", "val"]]
            .rename(columns={"val": concept})
            .reset_index(drop=True)
        )
        return df

    return None


def _derive_q4_rows(
    quarterly_df: pd.DataFrame,
    annual_frames: dict[str, pd.DataFrame],
    is_flow_map: dict[str, bool],
) -> pd.DataFrame:
    """
    Derive Q4 rows from annual (FY) and quarterly (Q1+Q2+Q3) data.

    For flow metrics  : Q4 = Annual − (Q1 + Q2 + Q3)
    For balance-sheet : Q4 = annual year-end value (same physical date)

    Only generates Q4 for fiscal years where Q1, Q2, AND Q3 are all present
    in quarterly_df and where annual data exists.

    Returns a DataFrame of Q4 rows (may be empty).
    """
    if not annual_frames:
        return pd.DataFrame()

    # Determine period_end and filed_date for Q4 from ANY annual frame
    annual_meta: dict[int, dict] = {}
    for metric, adf in annual_frames.items():
        for _, arow in adf.iterrows():
            fy = int(arow["fiscal_year"])
            if fy not in annual_meta:
                annual_meta[fy] = {
                    "period_end": arow["period_end"],
                    "filed_date": arow["filed_date"],
                }

    q4_rows = []
    for fy, meta in annual_meta.items():
        q_sub = quarterly_df[quarterly_df["fiscal_year"] == fy]
        present = set(q_sub["fiscal_period"].tolist())
        if not {"Q1", "Q2", "Q3"}.issubset(present):
            continue  # incomplete quarter data — skip

        row: dict = {
            "fiscal_year":   fy,
            "fiscal_period": "Q4",
            "period_end":    meta["period_end"],
            "filed_date":    meta["filed_date"],
        }

        for metric, adf in annual_frames.items():
            a_rows = adf[adf["fiscal_year"] == fy]
            if a_rows.empty or metric not in a_rows.columns:
                continue
            annual_val = a_rows.iloc[0][metric]

            if is_flow_map.get(metric, True):
                # Flow: Q4 = Annual − sum(Q1+Q2+Q3)
                if metric not in q_sub.columns:
                    row[metric] = float("nan")
                else:
                    q_vals = q_sub[q_sub["fiscal_period"].isin(["Q1", "Q2", "Q3"])][metric]
                    if pd.isna(annual_val) or q_vals.isna().all():
                        row[metric] = float("nan")
                    else:
                        row[metric] = annual_val - q_vals.sum(min_count=1)
            else:
                # Balance sheet: year-end value IS Q4
                row[metric] = annual_val

        q4_rows.append(row)

    return pd.DataFrame(q4_rows) if q4_rows else pd.DataFrame()


# ---------------------------------------------------------------------------
# SEC EDGAR concept fallback chains (most common → less common)
# ---------------------------------------------------------------------------

# Income statement (flow metrics — duration filter applied)
_REVENUE_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "RevenueNet",
    "SalesRevenueGoodsNet",
]
_GROSS_PROFIT_CONCEPTS = ["GrossProfit"]
_COST_OF_REVENUE_CONCEPTS = [
    "CostOfRevenue",
    "CostOfGoodsSold",
    "CostOfGoodsSoldAndServicesSold",
    "CostOfGoodsAndServicesSold",
]
_NET_INCOME_CONCEPTS = ["NetIncomeLoss", "NetIncome"]
_OP_INCOME_CONCEPTS = [
    "OperatingIncomeLoss",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
]
_RD_CONCEPTS = [
    "ResearchAndDevelopmentExpense",
    "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
]
_SGA_CONCEPTS = [
    "SellingGeneralAndAdministrativeExpense",
    "GeneralAndAdministrativeExpense",
]
_INTEREST_EXPENSE_CONCEPTS = [
    "InterestExpense",
    "InterestAndDebtExpense",
    "InterestExpenseDebt",
]
_TAX_CONCEPTS = [
    "IncomeTaxExpenseBenefit",
    "CurrentIncomeTaxExpenseBenefit",
]
_DA_CONCEPTS = [
    "DepreciationDepletionAndAmortization",
    "DepreciationAndAmortization",
    "Depreciation",
]
_CAPEX_CONCEPTS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "AcquisitionsNetOfCashAcquiredAndPurchasesOfBusinesses",
]

# Balance sheet (instantaneous — no duration filter)
_ASSETS_CONCEPTS = ["Assets"]
_CURRENT_ASSETS_CONCEPTS = ["AssetsCurrent"]
_EQUITY_CONCEPTS = [
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
]
_LIABILITIES_CONCEPTS = ["Liabilities"]
_CURRENT_LIABILITIES_CONCEPTS = ["LiabilitiesCurrent"]
_LT_DEBT_CONCEPTS = [
    "LongTermDebt",
    "LongTermDebtNoncurrent",
    "LongTermNotesPayable",
]
_INVENTORY_CONCEPTS = [
    "InventoryNet",
    "Inventories",
    "Inventory",
]
_AR_CONCEPTS = [
    "AccountsReceivableNetCurrent",
    "ReceivablesNetCurrent",
]
_RETAINED_EARNINGS_CONCEPTS = [
    "RetainedEarningsAccumulatedDeficit",
    "RetainedEarnings",
]
_SHARES_CONCEPTS = [
    "CommonStockSharesOutstanding",
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "WeightedAverageNumberOfSharesOutstandingBasic",
]


def _fetch_sec_fundamentals(cik: str, start_year: int) -> Optional[pd.DataFrame]:
    """
    Pull all SEC EDGAR metrics for one company and merge into a single
    wide DataFrame keyed on (period_end, fiscal_year, fiscal_period).
    """
    facts = _get_companyfacts(cik)
    if facts is None:
        return None

    # (metric_name, concept_list, is_flow)
    metric_specs = [
        # Income statement
        ("revenue",                  _REVENUE_CONCEPTS,           True),
        ("gross_profit",             _GROSS_PROFIT_CONCEPTS,      True),
        ("cost_of_revenue",          _COST_OF_REVENUE_CONCEPTS,   True),
        ("operating_income",         _OP_INCOME_CONCEPTS,         True),
        ("net_income",               _NET_INCOME_CONCEPTS,        True),
        ("r_and_d_expense",          _RD_CONCEPTS,                True),
        ("sga_expense",              _SGA_CONCEPTS,               True),
        ("interest_expense",         _INTEREST_EXPENSE_CONCEPTS,  True),
        ("income_tax_expense",       _TAX_CONCEPTS,               True),
        ("depreciation_amortization", _DA_CONCEPTS,               True),
        ("capex",                    _CAPEX_CONCEPTS,             True),
        # Balance sheet
        ("total_assets",             _ASSETS_CONCEPTS,            False),
        ("current_assets",           _CURRENT_ASSETS_CONCEPTS,    False),
        ("total_equity",             _EQUITY_CONCEPTS,            False),
        ("total_liabilities",        _LIABILITIES_CONCEPTS,       False),
        ("current_liabilities",      _CURRENT_LIABILITIES_CONCEPTS, False),
        ("long_term_debt",           _LT_DEBT_CONCEPTS,           False),
        ("inventory",                _INVENTORY_CONCEPTS,         False),
        ("accounts_receivable",      _AR_CONCEPTS,                False),
        ("retained_earnings",        _RETAINED_EARNINGS_CONCEPTS, False),
        ("shares_outstanding",       _SHARES_CONCEPTS,            False),
    ]

    frames: dict[str, pd.DataFrame] = {}
    annual_frames: dict[str, pd.DataFrame] = {}
    is_flow_map: dict[str, bool] = {}

    for metric, concepts, is_flow in metric_specs:
        is_flow_map[metric] = is_flow

        # Quarterly (Q1–Q3) series
        s = _extract_sec_series(facts, concepts, start_year, is_flow)
        if s is not None:
            val_col = [c for c in s.columns if c not in _KEY_COLS + ["filed_date"]][0]
            frames[metric] = s.rename(columns={val_col: metric})
        else:
            logger.debug(f"    {metric}: no SEC quarterly data found")

        # Annual (FY / 10-K) series — used to derive Q4
        a = _extract_sec_annual_series(facts, concepts, start_year, is_flow)
        if a is not None:
            val_col = [c for c in a.columns if c not in ["period_end", "filed_date", "fiscal_year"]][0]
            annual_frames[metric] = a.rename(columns={val_col: metric})

    if not frames:
        return None

    # --- Merge all quarterly metric frames on (fiscal_year, fiscal_period) ---
    # Join on (fy, fp) only; reconcile period_end by taking the MAX across all
    # sources (the most-recent date is almost always the correct period_end).
    _MERGE_KEYS = ["fiscal_year", "fiscal_period"]
    merged: Optional[pd.DataFrame] = None
    pe_cols: list[str] = []   # track all period_end columns across merges
    fd_cols: list[str] = []   # track all filed_date columns

    for i, (metric, df) in enumerate(frames.items()):
        metric_col = [c for c in df.columns if c not in _KEY_COLS + ["filed_date"]][0]
        pe_col = f"_pe_{i}"
        fd_col = f"_fd_{i}"
        right = (
            df[_MERGE_KEYS + ["period_end", "filed_date", metric_col]]
            .rename(columns={"period_end": pe_col, "filed_date": fd_col})
        )
        pe_cols.append(pe_col)
        fd_cols.append(fd_col)

        if merged is None:
            merged = right
        else:
            merged = pd.merge(merged, right, on=_MERGE_KEYS, how="outer")

    if merged is None:
        return None

    # Reconcile period_end: use MAX across all concept sources (most accurate)
    merged["period_end"] = merged[pe_cols].max(axis=1)
    merged["filed_date"] = merged[fd_cols].max(axis=1)
    merged = merged.drop(columns=pe_cols + fd_cols)

    # Fallback: derive total_liabilities = assets − equity when direct value
    # is unavailable (common for financial companies like BRK.B).
    if "total_liabilities" not in merged.columns:
        if "total_assets" in merged.columns and "total_equity" in merged.columns:
            merged["total_liabilities"] = (
                merged["total_assets"] - merged["total_equity"]
            )
            logger.debug("  total_liabilities derived from assets − equity")

    # --- Derive Q4 rows from annual (10-K) data ---
    q4_df = _derive_q4_rows(merged, annual_frames, is_flow_map)
    if not q4_df.empty:
        logger.info(f"  SEC: derived {len(q4_df)} Q4 rows from annual filings")
        merged = pd.concat([merged, q4_df], ignore_index=True)

    merged = merged.sort_values(["fiscal_year", "fiscal_period"]).reset_index(drop=True)
    logger.info(f"  SEC: {len(merged)} rows total (Q1–Q4)")
    return merged


# ---------------------------------------------------------------------------
# Yahoo Finance quarterly supplementary data
# ---------------------------------------------------------------------------

# Each entry maps our canonical name → list of yfinance column name candidates.
# yfinance column names vary across versions (0.1.x used spaces; 0.2.x is
# CamelCase); we try both forms for robustness.
_YF_COL_CANDIDATES: dict[str, list[str]] = {
    # ---------- income statement ----------
    "gross_profit": [
        "Gross Profit", "GrossProfit",
    ],
    "ebitda": [
        "EBITDA", "Ebitda", "Normalized EBITDA", "NormalizedEBITDA",
    ],
    "interest_expense": [
        "Interest Expense", "InterestExpense",
        "Interest Expense Non Operating", "InterestExpenseNonOperating",
        "Net Interest Income", "NetInterestIncome",
    ],
    "income_tax_expense": [
        "Tax Provision", "TaxProvision",
        "Income Tax Expense", "IncomeTaxExpense",
    ],
    "depreciation_amortization": [
        "Reconciled Depreciation", "ReconciledDepreciation",
        "Depreciation Amortization Depletion", "DepreciationAmortizationDepletion",
        "Depreciation And Amortization In Income Statement",
    ],
    "eps_diluted": [
        "Diluted EPS", "DilutedEPS",
        "Basic EPS", "BasicEPS",
    ],
    "shares_outstanding": [
        "Diluted Average Shares", "DilutedAverageShares",
        "Basic Average Shares", "BasicAverageShares",
        "Ordinary Shares Number", "OrdinarySharesNumber",
    ],
    # ---------- balance sheet ----------
    "total_debt": [
        "Total Debt", "TotalDebt",
        "Long Term Debt And Capital Lease Obligation",
        "LongTermDebtAndCapitalLeaseObligation",
    ],
    "cash_and_equivalents": [
        "Cash And Cash Equivalents", "CashAndCashEquivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "CashCashEquivalentsAndShortTermInvestments",
    ],
    "current_assets": [
        "Current Assets", "CurrentAssets",
    ],
    "current_liabilities": [
        "Current Liabilities", "CurrentLiabilities",
    ],
    "long_term_debt": [
        "Long Term Debt", "LongTermDebt",
        "Long Term Debt And Capital Lease Obligation",
        "LongTermDebtAndCapitalLeaseObligation",
    ],
    "inventory": [
        "Inventory", "Inventories",
        "Finished Goods", "FinishedGoods",
    ],
    "accounts_receivable": [
        "Accounts Receivable", "AccountsReceivable",
        "Net Receivables", "NetReceivables",
        "Receivables", "ReceivablesAdjustedForDoubtfulAccountsCurrentLiabilities",
    ],
    "retained_earnings": [
        "Retained Earnings", "RetainedEarnings",
        "Accumulated Other Comprehensive Income", "AccumulatedOtherComprehensiveIncome",
    ],
    # ---------- cash flow ----------
    "free_cash_flow": [
        "Free Cash Flow", "FreeCashFlow",
    ],
    "operating_cash_flow": [
        "Operating Cash Flow", "OperatingCashFlow",
    ],
    "capex": [
        "Capital Expenditure", "CapitalExpenditure",
        "Purchase Of PPE", "PurchaseOfPPE",
        "Purchases Of Property Plant And Equipment",
    ],
    "investing_cash_flow": [
        "Investing Cash Flow", "InvestingCashFlow",
        "Net Cash Used For Investing Activities",
        "NetCashUsedForInvestingActivities",
    ],
    "financing_cash_flow": [
        "Financing Cash Flow", "FinancingCashFlow",
        "Net Cash Used Provided By Financing Activities",
        "NetCashUsedProvidedByFinancingActivities",
    ],
}


def _first_matching_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """Return the first candidate column that exists in *df*, or None."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _transpose_stmt(stmt, ticker: str) -> Optional[pd.DataFrame]:
    """
    Transpose a yfinance quarterly statement (metrics × periods) into
    long format (periods × metrics) with a period_end column.
    """
    if stmt is None or stmt.empty:
        return None
    df = stmt.T.copy()
    df.index = pd.to_datetime(df.index, errors="coerce").tz_localize(None)
    df.index.name = "period_end"
    df = df.reset_index()
    return df


def _fetch_yf_quarterly(ticker: str) -> Optional[pd.DataFrame]:
    """
    Fetch supplementary quarterly metrics from Yahoo Finance.

    Uses quarterly_income_stmt, quarterly_balance_sheet, and
    quarterly_cashflow — all of which are genuinely historical and do NOT
    suffer from the point-in-time snapshot issue.

    Returns DataFrame: period_end | gross_profit | total_debt
                       | cash_and_equivalents | free_cash_flow
                       | operating_cash_flow  | eps_diluted
    or None if no data available.
    """
    yf_sym = YFINANCE_TICKER_MAP.get(ticker, ticker)
    t = yf.Ticker(yf_sym)

    inc = _transpose_stmt(t.quarterly_income_stmt,  ticker)
    bal = _transpose_stmt(t.quarterly_balance_sheet, ticker)
    cf  = _transpose_stmt(t.quarterly_cashflow,      ticker)

    result: Optional[pd.DataFrame] = None

    def _pull(stmt_df: Optional[pd.DataFrame], metric: str) -> None:
        nonlocal result
        if stmt_df is None:
            return
        col = _first_matching_col(stmt_df, _YF_COL_CANDIDATES[metric])
        if col is None:
            logger.debug(
                f"  YF {ticker}: {metric} not found "
                f"(tried {_YF_COL_CANDIDATES[metric]})"
            )
            return
        sub = stmt_df[["period_end", col]].rename(columns={col: metric}).dropna(
            subset=[metric]
        )
        if result is None:
            result = sub
        else:
            result = pd.merge(result, sub, on="period_end", how="outer")

    # Income statement
    _pull(inc, "gross_profit")
    _pull(inc, "ebitda")
    _pull(inc, "interest_expense")
    _pull(inc, "income_tax_expense")
    _pull(inc, "depreciation_amortization")
    _pull(inc, "eps_diluted")
    _pull(inc, "shares_outstanding")
    # Balance sheet
    _pull(bal, "total_debt")
    _pull(bal, "cash_and_equivalents")
    _pull(bal, "current_assets")
    _pull(bal, "current_liabilities")
    _pull(bal, "long_term_debt")
    _pull(bal, "inventory")
    _pull(bal, "accounts_receivable")
    _pull(bal, "retained_earnings")
    # Cash flow
    _pull(cf,  "free_cash_flow")
    _pull(cf,  "operating_cash_flow")
    _pull(cf,  "capex")
    _pull(cf,  "investing_cash_flow")
    _pull(cf,  "financing_cash_flow")

    if result is None or result.empty:
        return None

    result["period_end"] = pd.to_datetime(result["period_end"]).dt.tz_localize(None)
    result = result.sort_values("period_end").reset_index(drop=True)
    logger.info(
        f"  YF: {len(result)} quarterly rows, "
        f"cols={[c for c in result.columns if c != 'period_end']}"
    )
    return result


# ---------------------------------------------------------------------------
# Merge SEC (primary) + YF (supplementary)
# ---------------------------------------------------------------------------


def _merge_sources(
    sec_df: pd.DataFrame,
    yf_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """
    Left-join SEC data (primary) with Yahoo Finance (supplementary) on
    period_end, using a ±5-day nearest-match to absorb minor date
    discrepancies between the two sources.

    SEC values always win when both sources carry the same column name.
    Yahoo Finance columns are added only where SEC has no data.
    """
    if yf_df is None or yf_df.empty:
        return sec_df.copy()

    sec_df = sec_df.copy()
    sec_df["period_end"] = pd.to_datetime(sec_df["period_end"]).dt.tz_localize(None)

    sec_sorted = sec_df.sort_values("period_end")
    yf_sorted  = yf_df.sort_values("period_end")

    merged = pd.merge_asof(
        sec_sorted,
        yf_sorted,
        on="period_end",
        direction="nearest",
        tolerance=pd.Timedelta(days=5),
        suffixes=("", "_yf"),
    )

    # Drop any YF shadow-columns (SEC takes precedence for overlapping names)
    drop_cols = [c for c in merged.columns if c.endswith("_yf")]
    merged = merged.drop(columns=drop_cols)

    merged = merged.sort_values("period_end").reset_index(drop=True)
    logger.info(f"  Merged: {len(merged)} rows")
    return merged


# ---------------------------------------------------------------------------
# Derived ratio computation
# ---------------------------------------------------------------------------


def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    """Element-wise division; returns NaN when denominator is zero or NaN."""
    mask = den.abs() > 0
    result = pd.Series(index=num.index, dtype=float)
    result[mask]  = num[mask] / den[mask]
    result[~mask] = np.nan
    return result


def _compute_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived ratio columns from raw fundamental figures."""
    df = df.copy()

    # --- Margin ratios ---
    if "gross_profit" in df and "revenue" in df:
        df["gross_margin"] = _safe_div(df["gross_profit"], df["revenue"])
    if "operating_income" in df and "revenue" in df:
        df["operating_margin"] = _safe_div(df["operating_income"], df["revenue"])
    if "ebitda" in df and "revenue" in df:
        df["ebitda_margin"] = _safe_div(df["ebitda"], df["revenue"])
    if "net_income" in df and "revenue" in df:
        df["net_margin"] = _safe_div(df["net_income"], df["revenue"])

    # --- Return ratios (annualized: quarterly figure × 4) ---
    # Multiplying by 4 makes these comparable to the annual ROE/ROA figures
    # reported by financial data providers and avoids understatement vs. a
    # company reporting on an annual basis.
    if "net_income" in df and "total_equity" in df:
        df["roe"] = _safe_div(df["net_income"] * 4, df["total_equity"])
    if "net_income" in df and "total_assets" in df:
        df["roa"] = _safe_div(df["net_income"] * 4, df["total_assets"])
    # Asset turnover annualized: (quarterly revenue × 4) / ending assets
    if "revenue" in df and "total_assets" in df:
        df["asset_turnover"] = _safe_div(df["revenue"] * 4, df["total_assets"])

    # --- Liquidity ratios ---
    if "current_assets" in df and "current_liabilities" in df:
        df["current_ratio"] = _safe_div(df["current_assets"], df["current_liabilities"])
        df["working_capital"] = df["current_assets"] - df["current_liabilities"]
    # Quick ratio excludes inventory (less liquid asset)
    if "current_assets" in df and "current_liabilities" in df:
        inv = df["inventory"] if "inventory" in df else pd.Series(0, index=df.index)
        df["quick_ratio"] = _safe_div(
            df["current_assets"] - inv.fillna(0), df["current_liabilities"]
        )

    # --- Leverage ratios ---
    if "total_debt" in df and "total_equity" in df:
        df["debt_to_equity"] = _safe_div(df["total_debt"], df["total_equity"])
    if "total_liabilities" in df and "total_assets" in df:
        df["debt_ratio"] = _safe_div(df["total_liabilities"], df["total_assets"])
    # Net debt: total debt minus cash (negative = net cash position)
    if "total_debt" in df and "cash_and_equivalents" in df:
        df["net_debt"] = df["total_debt"] - df["cash_and_equivalents"]

    # --- Coverage ratios ---
    # Interest coverage: how many times operating income covers interest payments
    if "operating_income" in df and "interest_expense" in df:
        df["interest_coverage"] = _safe_div(
            df["operating_income"], df["interest_expense"].abs()
        )

    # --- Capex intensity ---
    if "capex" in df and "revenue" in df:
        # capex is typically reported as negative (cash outflow); take abs
        df["capex_to_revenue"] = _safe_div(df["capex"].abs(), df["revenue"])

    return df


def _compute_yoy_growth(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add YoY growth columns using same-quarter prior-year comparison.

    For example:
        revenue_growth_yoy[Q2 FY2025]
            = (revenue[Q2 FY2025] − revenue[Q2 FY2024]) / |revenue[Q2 FY2024]|

    When the prior-year value is negative (e.g. a loss quarter), the growth
    percentage is economically meaningless and is set to NaN.

    This correctly removes seasonality effects; computing QoQ growth on
    a quarterly time series is generally not meaningful for fundamental
    analysis of cyclical businesses.
    """
    df = df.copy().sort_values("period_end").reset_index(drop=True)

    for metric, growth_col in [
        ("revenue",           "revenue_growth_yoy"),
        ("net_income",        "net_income_growth_yoy"),
        ("operating_income",  "operating_income_growth_yoy"),
    ]:
        if metric not in df.columns:
            continue

        prior = (
            df[["fiscal_period", "fiscal_year", metric]]
            .copy()
            .assign(fiscal_year=lambda x: x["fiscal_year"] + 1)
            .rename(columns={metric: f"_{metric}_prior"})
        )
        df = pd.merge(df, prior, on=["fiscal_period", "fiscal_year"], how="left")
        prior_col = f"_{metric}_prior"
        df[growth_col] = _safe_div(
            df[metric] - df[prior_col],
            df[prior_col].abs(),
        )
        # Growth rate is undefined when the base period is negative
        df.loc[df[prior_col] < 0, growth_col] = float("nan")
        df = df.drop(columns=[prior_col])

    return df.sort_values("period_end").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Per-ticker pipeline
# ---------------------------------------------------------------------------

# Final canonical column order for the output parquet
_OUTPUT_COLS = [
    "ticker", "period_end", "filed_date", "fiscal_year", "fiscal_period",
    # ── Raw: income statement ──────────────────────────────────────────────
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
    # ── Raw: balance sheet ────────────────────────────────────────────────
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
    # ── Raw: cash flow ────────────────────────────────────────────────────
    "operating_cash_flow",
    "free_cash_flow",
    "capex",
    "investing_cash_flow",
    "financing_cash_flow",
    # ── Raw: per-share ────────────────────────────────────────────────────
    "eps_diluted",
    "shares_outstanding",
    # ── Derived: margin ratios ────────────────────────────────────────────
    "gross_margin",
    "operating_margin",
    "ebitda_margin",
    "net_margin",
    # ── Derived: return ratios ────────────────────────────────────────────
    "roe",
    "roa",
    "asset_turnover",
    # ── Derived: liquidity ────────────────────────────────────────────────
    "current_ratio",
    "quick_ratio",
    "working_capital",
    # ── Derived: leverage ─────────────────────────────────────────────────
    "debt_to_equity",
    "debt_ratio",
    "net_debt",
    "interest_coverage",
    # ── Derived: efficiency / intensity ───────────────────────────────────
    "capex_to_revenue",
    # ── Derived: growth (same-quarter YoY) ───────────────────────────────
    "revenue_growth_yoy",
    "operating_income_growth_yoy",
    "net_income_growth_yoy",
]


def _process_ticker(
    ticker: str,
    cik_map: dict[str, str],
    start_year: int,
) -> Optional[pd.DataFrame]:
    """Run the full collection + merge pipeline for a single ticker."""

    # --- SEC EDGAR ---
    logger.info(f"[{ticker}] Fetching SEC EDGAR ...")
    sec_ticker = SEC_TICKER_MAP.get(ticker, ticker)
    cik = cik_map.get(sec_ticker)
    if cik is None:
        logger.warning(f"  CIK not found for {sec_ticker}; skipping SEC data")
        sec_df = None
    else:
        sec_df = _fetch_sec_fundamentals(cik, start_year)
        if sec_df is None:
            logger.warning(f"  No SEC data returned for {ticker}")
        time.sleep(SEC_RATE_SLEEP)

    # --- Yahoo Finance ---
    logger.info(f"[{ticker}] Fetching Yahoo Finance quarterly ...")
    yf_df = _fetch_yf_quarterly(ticker)

    # Require at least one source
    if sec_df is None and yf_df is None:
        logger.error(f"  No data from either source for {ticker}")
        return None

    # If SEC data is missing entirely, fall back to YF only
    if sec_df is None:
        logger.warning(f"  [{ticker}] Using Yahoo Finance only (no SEC data)")
        df = yf_df.copy()
        # Add placeholder columns that SEC normally provides
        for col in ["filed_date", "fiscal_year", "fiscal_period"]:
            if col not in df.columns:
                df[col] = pd.NaT if col == "filed_date" else None
    else:
        df = _merge_sources(sec_df, yf_df)

    df = _compute_ratios(df)
    df = _compute_yoy_growth(df)
    df.insert(0, "ticker", ticker)

    # Reorder columns: canonical first, any extras appended
    present = [c for c in _OUTPUT_COLS if c in df.columns]
    extras  = [c for c in df.columns  if c not in present]
    df = df[present + extras]

    logger.info(
        f"[{ticker}] Done: {len(df)} quarters, "
        f"{df['period_end'].min().date()} → {df['period_end'].max().date()}"
    )
    return df


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(
    tickers: list[str] = TICKERS,
    end: str = SAMPLE_END,
    output_dir: str = FUNDAMENTALS_DIR,
    history_years: int = FUNDAMENTAL_HISTORY_YEARS,
) -> pd.DataFrame:
    """
    Collect integrated quarterly fundamentals for *tickers* and save to
    ``quarterly_fundamentals.parquet``.

    Parameters
    ----------
    tickers       : canonical ticker symbols (e.g. ["AAPL", "GOOGL"])
    end           : YYYY-MM-DD upper bound of the backtest window
                    (used only to compute start_year for SEC EDGAR)
    output_dir    : directory to write the output parquet file
    history_years : number of years of quarterly history to collect

    Returns
    -------
    Combined DataFrame (also persisted to parquet).
    """
    os.makedirs(output_dir, exist_ok=True)

    end_year   = pd.to_datetime(end).year
    start_year = end_year - history_years

    logger.info("[FundamentalCollector] Starting integrated collection")
    logger.info(f"  Tickers      : {tickers}")
    logger.info(f"  Fiscal history: {start_year} → {end_year}  ({history_years} yrs)")
    logger.info(f"  Output       : {output_dir}/quarterly_fundamentals.parquet")

    logger.info("  Fetching SEC CIK map ...")
    cik_map = _get_cik_map()

    all_dfs: list[pd.DataFrame] = []
    for ticker in tickers:
        try:
            df = _process_ticker(ticker, cik_map, start_year)
            if df is not None:
                all_dfs.append(df)
        except Exception as exc:
            logger.error(f"  [{ticker}] Unexpected error: {exc}", exc_info=True)

    if not all_dfs:
        logger.error("No fundamental data collected for any ticker.")
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)

    # Ensure correct dtypes for parquet serialisation
    combined["period_end"]  = pd.to_datetime(combined["period_end"]).dt.tz_localize(None)
    combined["filed_date"]  = pd.to_datetime(combined["filed_date"]).dt.tz_localize(None)
    if "fiscal_year" in combined.columns:
        combined["fiscal_year"] = combined["fiscal_year"].astype("Int64")

    out_path = os.path.join(output_dir, "quarterly_fundamentals.parquet")
    combined.to_parquet(out_path, index=False, engine="pyarrow")
    logger.info(
        f"[FundamentalCollector] Saved → {out_path}  "
        f"({len(combined)} rows, {combined['ticker'].nunique()} tickers)"
    )
    return combined


if __name__ == "__main__":
    load_dotenv()
    run()
