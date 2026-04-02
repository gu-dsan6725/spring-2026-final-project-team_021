from src.features.technical_features import compute_technical_features

def get_technical_snapshot(ticker: str, analysis_date: str) -> dict:
    features = compute_technical_features(ticker=ticker, analysis_date=analysis_date)

    return {
        "ticker": ticker,
        "analysis_date": analysis_date,
        "price": features["close"],
        "sma_20": features["sma_20"],
        "sma_50": features["sma_50"],
        "rsi_14": features["rsi_14"],
        "macd": features["macd"],
        "macd_signal": features["macd_signal"],
        "momentum_20d": features["momentum_20d"],
        "volatility_20d": features["volatility_20d"],
    }