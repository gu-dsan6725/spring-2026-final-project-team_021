# Data Collection

Collects raw data from external sources and saves it to `data/sample/` as Parquet / CSV files for downstream analyst agents.

## File Overview

```
src/data_collection/
├── config.py                  # Central config: tickers, date range, output dirs
├── run_pipeline.py            # Main entry point (all 5 steps)
├── price_collector.py         # Daily OHLCV (Yahoo Finance)
├── fundamental_collector.py   # Quarterly fundamentals (SEC EDGAR primary + Yahoo Finance supplementary)
├── google_trends_collector.py # Retail investor attention proxy (pytrends)
├── finnhub_news_fetch.py      # Company news headlines (Finnhub)
├── fred_macro_fetch.py        # 35 macro indicators (FRED)
└── parquet_to_csv.py          # Utility: export Parquet files to CSV for inspection
```

## Data Sources and Outputs

| Script                       | Source                                                   | Output                                                                                                                                           | Format                                                                                                                                                                             |
| ---------------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `price_collector.py`         | Yahoo Finance (`yfinance`)                               | `data/sample/price/price_ohlcv.parquet`                                                                                                          | Long table: 1 row = 1 ticker × 1 day                                                                                                                                               |
| `fundamental_collector.py`   | SEC EDGAR XBRL (primary) + Yahoo Finance (supplementary) | `data/sample/fundamentals/quarterly_fundamentals.parquet`                                                                                        | Long table: 1 row = 1 ticker × 1 quarter, includes `period_end` and `filed_date`                                                                                                   |
| `google_trends_collector.py` | pytrends + Groq (search term generation)                 | `data/sample/sentiment/google_trends_daily.parquet`                                                                                              | Long table: 1 row = 1 ticker × 1 day, `search_interest` 0–100                                                                                                                      |
| `finnhub_news_fetch.py`      | Finnhub News API                                         | `data/sample/news/{TICKER}_news.csv` + `all_news.csv`                                                                                            | One CSV per ticker                                                                                                                                                                 |
| `fred_macro_fetch.py`        | FRED (`fredapi`)                                         | `data/sample/macro/macro_daily_raw.csv`, `macro_weekly_raw.csv`, `macro_monthly_raw.csv`, `macro_quarterly_raw.csv`, `macro_all_daily_ffill.csv` | Raw files by frequency + one combined daily file (lower-frequency series forward-filled to daily). Trailing NaNs are expected where FRED has not yet published the latest release. |

## Usage

**Run the full pipeline** (all 5 steps):

```bash
# From the project root
python src/data_collection/run_pipeline.py
```

**Custom date range and tickers:**

```bash
python src/data_collection/run_pipeline.py \
    --start-date 2025-07-01 \
    --end-date 2025-12-31 \
    --tickers AAPL GOOGL AMZN
```

**CLI arguments:**

| Argument               | Default               | Description                            |
| ---------------------- | --------------------- | -------------------------------------- |
| `--start-date`         | `2025-07-01`          | Collection start date (YYYY-MM-DD)     |
| `--end-date`           | Yesterday             | Collection end date (YYYY-MM-DD)       |
| `--tickers`            | All 6 default tickers | Space-separated list of ticker symbols |
| `--skip-price`         | —                     | Skip Step 1: price collection          |
| `--skip-fundamentals`  | —                     | Skip Step 2: fundamentals collection   |
| `--skip-google-trends` | —                     | Skip Step 3: Google Trends collection  |
| `--skip-news`          | —                     | Skip Step 4: Finnhub news collection   |
| `--skip-macro`         | —                     | Skip Step 5: FRED macro collection     |

**Export Parquet files to CSV** for manual inspection:

```bash
python src/data_collection/parquet_to_csv.py
```

## Configuration (`config.py`)

| Parameter                   | Default                                            | Description                                                                                                                       |
| --------------------------- | -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `TICKERS`                   | `["AAPL", "GOOGL", "LLY", "BRK.B", "AMZN", "XOM"]` | Stock universe                                                                                                                    |
| `SAMPLE_START`              | `"2025-07-01"`                                     | Default collection start date (used by all collectors and as `--start-date` default in `run_pipeline.py`)                         |
| `SAMPLE_END`                | `"2025-12-31"`                                     | Default collection end date for individual collectors run standalone. `run_pipeline.py` overrides this with yesterday at runtime. |
| `FUNDAMENTAL_HISTORY_YEARS` | `6`                                                | Years of quarterly history pulled from SEC EDGAR / YF                                                                             |
| `GT_GEO`                    | `"US"`                                             | Google Trends geography                                                                                                           |
| `GT_RATE_LIMIT_SLEEP`       | `5.0s`                                             | Sleep between pytrends batch requests to avoid throttling                                                                         |

## Notes

**Fundamental data look-ahead prevention**

`quarterly_fundamentals.parquet` includes two date fields per row:
- `period_end`: when the fiscal quarter ended
- `filed_date`: when the 10-Q / 10-K was publicly filed with the SEC

Downstream consumers **must** filter by `filed_date <= analysis_date`, not `period_end`. Using `period_end` as the filter leaks future information into the model.

**Google Trends search term cache**

Search terms are generated by Groq and cached in `data/cache/search_terms_cache.json`. If `GROQ_API_KEY` is not set, the collector falls back to `"{ticker} stock"`. The cache file should be committed to git to avoid redundant Groq calls.

**yfinance ticker mapping**

`BRK.B` must be passed to yfinance as `BRK-B`. `config.py` provides `YFINANCE_TICKER_MAP` and `YFINANCE_TICKER_REVERSE` for this conversion; downstream code should use these mappings rather than hardcoding the transformation.
