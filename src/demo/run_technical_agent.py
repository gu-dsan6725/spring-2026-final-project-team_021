from src.features.technical_features import build_technical_snapshot
from src.agents.technical_analyst import TechnicalAnalyst

PARQUET_PATH = "data/sample/price/yfinance_ohlcv.parquet"


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