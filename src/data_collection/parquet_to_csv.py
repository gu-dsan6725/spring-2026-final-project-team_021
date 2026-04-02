"""
Convert all sample parquet files to CSV for inspection.
Original parquet files are NOT modified.

Usage:
    uv run python src/data_collection/parquet_to_csv.py
"""
import pandas as pd
from pathlib import Path

PARQUET_FILES = [
    "data/sample/price/price_ohlcv.parquet",
    "data/sample/fundamentals/quarterly_fundamentals.parquet",
    "data/sample/sentiment/google_trends_daily.parquet",
]

for parquet_path in PARQUET_FILES:
    p = Path(parquet_path)
    if not p.exists():
        print(f"[SKIP] Not found: {p}")
        continue
    df = pd.read_parquet(p)
    csv_path = p.with_suffix(".csv")
    df.to_csv(csv_path, index=False)
    print(f"[OK] {p.name}  →  {csv_path}  ({len(df):,} rows, {len(df.columns)} cols)")
