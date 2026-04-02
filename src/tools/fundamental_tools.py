from src.features.fundamental_features import compute_fundamental_features

def get_fundamental_snapshot(ticker: str, analysis_date: str) -> dict:
    features = compute_fundamental_features(ticker=ticker, analysis_date=analysis_date)

    return {
        "ticker": ticker,
        "analysis_date": analysis_date,
        "revenue_growth_yoy": features["revenue_growth_yoy"],
        "earnings_growth_yoy": features["earnings_growth_yoy"],
        "gross_margin": features["gross_margin"],
        "operating_margin": features["operating_margin"],
        "net_margin": features["net_margin"],
        "roe": features["roe"],
        "roa": features["roa"],
        "debt_to_equity": features["debt_to_equity"],
        "current_ratio": features["current_ratio"],
        "free_cash_flow": features["free_cash_flow"],
        "operating_cash_flow": features["operating_cash_flow"],
        "forward_pe": features.get("forward_pe"),
        "trailing_pe": features.get("trailing_pe"),
    }