"""
Yahoo Finance data collector for DebateTrader.

Collects:
  - Daily OHLCV price data          → data/sample/price/yfinance_ohlcv.parquet
  - Fundamental snapshot (ratios)   → data/sample/fundamentals/yfinance_fundamentals_snapshot.parquet
  - Quarterly income statement      → data/sample/fundamentals/quarterly_income_stmt.parquet
  - Quarterly balance sheet         → data/sample/fundamentals/quarterly_balance_sheet.parquet
  - Quarterly cash flow             → data/sample/fundamentals/quarterly_cashflow.parquet

Downstream consumers:
  - Technical Analyst agent  (OHLCV)
  - Fundamental Analyst agent (fundamentals + quarterly financials)
"""
from __future__ import annotations

import sys
import os
import logging
from datetime import datetime

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from src.data_collection.config import (
    TICKERS, YFINANCE_TICKER_MAP,
    SAMPLE_START, SAMPLE_END,
    PRICE_DIR, FUNDAMENTALS_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fundamental fields pulled from yf.Ticker.info
# ---------------------------------------------------------------------------
FUNDAMENTAL_FIELDS: dict[str, str] = {
    # Valuation
    "trailingPE":          "pe_ratio_ttm",
    "forwardPE":           "pe_ratio_forward",
    "priceToBook":         "price_to_book",
    "enterpriseToRevenue": "ev_to_revenue",
    "enterpriseToEbitda":  "ev_to_ebitda",
    # Per-share
    "trailingEps":         "eps_ttm",
    "forwardEps":          "eps_forward",
    "bookValue":           "book_value_per_share",
    # Growth
    "revenueGrowth":       "revenue_growth_yoy",
    "earningsGrowth":      "earnings_growth_yoy",
    # Margins
    "grossMargins":        "gross_margin",
    "operatingMargins":    "operating_margin",
    "profitMargins":       "net_margin",
    # Leverage & liquidity
    "debtToEquity":        "debt_to_equity",
    "currentRatio":        "current_ratio",
    "quickRatio":          "quick_ratio",
    # Returns
    "returnOnEquity":      "roe",
    "returnOnAssets":      "roa",
    # Scale
    "marketCap":           "market_cap",
    "enterpriseValue":     "enterprise_value",
    "totalRevenue":        "total_revenue",
    "totalDebt":           "total_debt",
    "totalCash":           "total_cash",
    "freeCashflow":        "free_cash_flow",
    "operatingCashflow":   "operating_cash_flow",
    "sharesOutstanding":   "shares_outstanding",
    # Risk / price context
    "beta":                "beta",
    "fiftyTwoWeekHigh":    "52w_high",
    "fiftyTwoWeekLow":     "52w_low",
    # Dividends
    "dividendYield":       "dividend_yield",
    "payoutRatio":         "payout_ratio",
}


# ---------------------------------------------------------------------------
# OHLCV
# ---------------------------------------------------------------------------

def collect_ohlcv(
    tickers: list[str] = TICKERS,
    start: str = SAMPLE_START,
    end: str = SAMPLE_END,
    output_dir: str = PRICE_DIR,
) -> pd.DataFrame:
    """Download daily OHLCV from Yahoo Finance for all tickers."""
    logger.info(f"[yfinance] Collecting OHLCV  {start} → {end}  tickers={tickers}")
    os.makedirs(output_dir, exist_ok=True)

    records = []
    for canonical in tickers:
        yf_sym = YFINANCE_TICKER_MAP.get(canonical, canonical)
        logger.info(f"  {canonical} (yf={yf_sym}) ...")
        try:
            df = yf.Ticker(yf_sym).history(start=start, end=end, auto_adjust=False)

            if df.empty:
                logger.warning(f"  No data returned for {canonical}")
                continue

            df = df.reset_index()
            col_map = {
                "Date":         "date",
                "Open":         "open",
                "High":         "high",
                "Low":          "low",
                "Close":        "close",
                "Adj Close":    "adj_close",
                "Volume":       "volume",
                "Dividends":    "dividends",
                "Stock Splits": "stock_splits",
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

            # Ensure datetime64 (parquet requires it, not Python date objects)
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)

            if "adj_close" not in df.columns:
                df["adj_close"] = df["close"]

            df["ticker"] = canonical
            keep = ["date", "ticker", "open", "high", "low", "close", "adj_close",
                    "volume", "dividends", "stock_splits"]
            records.append(df[[c for c in keep if c in df.columns]])
            logger.info(f"    {len(df)} rows")

        except Exception as exc:
            logger.error(f"  Error fetching OHLCV for {canonical}: {exc}")

    if not records:
        logger.error("No OHLCV data collected.")
        return pd.DataFrame()

    combined = pd.concat(records, ignore_index=True)
    out_path = os.path.join(output_dir, "yfinance_ohlcv.parquet")
    combined.to_parquet(out_path, index=False, engine="pyarrow")
    logger.info(f"[yfinance] OHLCV saved → {out_path}  ({len(combined)} rows)")
    return combined


# ---------------------------------------------------------------------------
# Fundamental snapshot
# ---------------------------------------------------------------------------

def collect_fundamentals(
    tickers: list[str] = TICKERS,
    output_dir: str = FUNDAMENTALS_DIR,
) -> pd.DataFrame:
    """Collect current fundamental ratios from yf.Ticker.info (point-in-time snapshot)."""
    logger.info("[yfinance] Collecting fundamental snapshot ...")
    os.makedirs(output_dir, exist_ok=True)

    rows = []
    for canonical in tickers:
        yf_sym = YFINANCE_TICKER_MAP.get(canonical, canonical)
        logger.info(f"  {canonical} ...")
        try:
            info = yf.Ticker(yf_sym).info
            row: dict = {
                "ticker":        canonical,
                "snapshot_date": pd.Timestamp(datetime.now().date()),
                "company_name":  info.get("longName", canonical),
                "sector":        info.get("sector"),
                "industry":      info.get("industry"),
            }
            for yf_field, our_field in FUNDAMENTAL_FIELDS.items():
                row[our_field] = info.get(yf_field)
            rows.append(row)
            non_null = sum(v is not None for v in row.values())
            logger.info(f"    {non_null} non-null fields")
        except Exception as exc:
            logger.error(f"  Error fetching fundamentals for {canonical}: {exc}")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    out_path = os.path.join(output_dir, "yfinance_fundamentals_snapshot.parquet")
    df.to_parquet(out_path, index=False, engine="pyarrow")
    logger.info(f"[yfinance] Fundamentals snapshot saved → {out_path}")
    return df


# ---------------------------------------------------------------------------
# Quarterly financial statements
# ---------------------------------------------------------------------------

def _save_quarterly(records: list[pd.DataFrame], name: str, output_dir: str) -> None:
    if not records:
        logger.warning(f"  No data collected for {name}")
        return
    df = pd.concat(records, ignore_index=True)
    df.columns = [str(c).strip() for c in df.columns]
    # Convert period_end to datetime for parquet
    if "period_end" in df.columns:
        df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
    out_path = os.path.join(output_dir, f"{name}.parquet")
    df.to_parquet(out_path, index=False, engine="pyarrow")
    logger.info(f"  Saved {name} → {out_path}  ({len(df)} rows)")


def collect_quarterly_financials(
    tickers: list[str] = TICKERS,
    output_dir: str = FUNDAMENTALS_DIR,
) -> None:
    """Collect quarterly income statement, balance sheet, and cash flow (all available history)."""
    logger.info("[yfinance] Collecting quarterly financial statements ...")
    os.makedirs(output_dir, exist_ok=True)

    income_recs, balance_recs, cashflow_recs = [], [], []

    for canonical in tickers:
        yf_sym = YFINANCE_TICKER_MAP.get(canonical, canonical)
        logger.info(f"  {canonical} ...")
        try:
            t = yf.Ticker(yf_sym)

            def _transpose(stmt):
                if stmt is None or stmt.empty:
                    return None
                df = stmt.T.reset_index()
                df.insert(0, "ticker", canonical)
                df = df.rename(columns={"index": "period_end"})
                return df

            inc = _transpose(t.quarterly_income_stmt)
            bal = _transpose(t.quarterly_balance_sheet)
            cf  = _transpose(t.quarterly_cashflow)

            if inc is not None: income_recs.append(inc)
            if bal is not None: balance_recs.append(bal)
            if cf  is not None: cashflow_recs.append(cf)

        except Exception as exc:
            logger.error(f"  Error for {canonical}: {exc}")

    _save_quarterly(income_recs,  "quarterly_income_stmt",  output_dir)
    _save_quarterly(balance_recs, "quarterly_balance_sheet", output_dir)
    _save_quarterly(cashflow_recs,"quarterly_cashflow",      output_dir)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(tickers=TICKERS, start=SAMPLE_START, end=SAMPLE_END):
    collect_ohlcv(tickers, start, end)
    collect_fundamentals(tickers)
    collect_quarterly_financials(tickers)
    logger.info("[yfinance] All data collection complete.")


if __name__ == "__main__":
    load_dotenv()
    run()
