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

# ---------------------------------------------------------------------------
# Output directories  (relative to project root)
# ---------------------------------------------------------------------------
DATA_DIR         = "data/sample"
PRICE_DIR        = os.path.join(DATA_DIR, "price")
FUNDAMENTALS_DIR = os.path.join(DATA_DIR, "fundamentals")
SENTIMENT_DIR    = os.path.join(DATA_DIR, "sentiment")

# ---------------------------------------------------------------------------
# Alpha Vantage  (3 keys for rotation; free tier: 25 req/day each)
# ---------------------------------------------------------------------------
AV_BASE_URL         = "https://www.alphavantage.co/query"
AV_RATE_LIMIT_SLEEP = 15    # seconds between requests  (free tier: 5 req/min)
AV_REQUEST_TIMEOUT  = 30    # seconds
# Keys are read from env: ALPHA_VANTAGE_API_KEY_1 / _2 / _3

# ---------------------------------------------------------------------------
# Google Trends  (retail attention proxy for Sentiment Analyst)
# ---------------------------------------------------------------------------
GT_GEO              = "US"  # focus on US retail investors
GT_RATE_LIMIT_SLEEP = 5.0   # seconds between batch requests (pytrends throttle)

# ---------------------------------------------------------------------------
# Price cross-validation
# ---------------------------------------------------------------------------
PRICE_DISCREPANCY_THRESHOLD_PCT = 0.5   # flag if |yf - av| / av > 0.5 %
