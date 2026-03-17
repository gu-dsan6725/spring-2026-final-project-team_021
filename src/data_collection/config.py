"""
Central configuration for DebateTrader data collection pipeline.
"""
from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Stock universe (6-stock sample for Milestone 2)
# ---------------------------------------------------------------------------
TICKERS = ["AAPL", "GOOGL", "LLY", "BRK.B", "AMZN", "XOM"]

# yfinance requires "BRK-B" instead of "BRK.B"
YFINANCE_TICKER_MAP     = {t: t.replace(".", "-") for t in TICKERS}
YFINANCE_TICKER_REVERSE = {v: k for k, v in YFINANCE_TICKER_MAP.items()}

# ---------------------------------------------------------------------------
# Date range for sample data
# ---------------------------------------------------------------------------
SAMPLE_START = "2025-07-01"
SAMPLE_END   = "2025-12-31"

# Fundamental data needs more history than the price window for YoY comparisons
# and to give agents multi-quarter trend context during backtesting.
FUNDAMENTAL_HISTORY_YEARS = 6  # years of quarterly history to pull from SEC EDGAR / YF

# ---------------------------------------------------------------------------
# Output directories  (relative to project root)
# ---------------------------------------------------------------------------
DATA_DIR         = "data/sample"
PRICE_DIR        = os.path.join(DATA_DIR, "price")
FUNDAMENTALS_DIR = os.path.join(DATA_DIR, "fundamentals")
SENTIMENT_DIR    = os.path.join(DATA_DIR, "sentiment")

# ---------------------------------------------------------------------------
# Google Trends  (retail attention proxy for Sentiment Analyst)
# ---------------------------------------------------------------------------
GT_GEO              = "US"  # focus on US retail investors
GT_RATE_LIMIT_SLEEP = 5.0   # seconds between batch requests (pytrends throttle)

