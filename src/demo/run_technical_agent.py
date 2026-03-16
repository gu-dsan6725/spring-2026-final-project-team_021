"""
Run Technical Analyst Demo

Summary
-------
This script runs a demo of the Technical Analyst agent using sample parquet data.

Pipeline
--------
1. Load historical price data
2. Build a technical feature snapshot for one ticker
3. Run the Technical Analyst agent
4. Print the structured JSON output

Usage
-----
uv run python src/demo/run_technical_agent.py
"""

from src.features.technical_features import build_technical_snapshot
from src.agents.technical_analyst import TechnicalAnalyst

PARQUET_PATH = "data/sample/price/price_ohlcv.parquet"


def main():
    ticker = "AAPL"

    snapshot = build_technical_snapshot(
        parquet_path=PARQUET_PATH,
        ticker=ticker,
    )

    agent = TechnicalAnalyst()
    result = agent.analyze(snapshot)

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()