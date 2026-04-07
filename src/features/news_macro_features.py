"""
News and Macro Feature Builder

Summary
-------
This module reads company news CSV data and macroeconomic CSV data and
builds a cleaned snapshot for the News & Macro Analyst.

Responsibilities
----------------
- Load company news and macro data
- Filter data for a target ticker and analysis date
- Compute simple news sentiment and relevance metadata
- Return JSON-safe aggregate features plus recent article records
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LM_LEXICON_PATH = PROJECT_ROOT / "data" / "reference" / "lm_lexicon.json"

COMMON_COMPANY_WORDS = {
    "inc",
    "inc.",
    "corp",
    "corp.",
    "corporation",
    "company",
    "co",
    "co.",
    "holdings",
    "group",
    "plc",
    "ltd",
    "class",
}

def to_python_scalar(value: Any) -> Any:
    """
    Convert pandas/numpy scalar values into JSON-safe native Python types.
    """
    if pd.isna(value):
        return None

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        return float(value)

    if isinstance(value, np.bool_):
        return bool(value)

    return value


def _normalize_text(value: str | None) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


@lru_cache(maxsize=1)
def load_lm_lexicon() -> dict[str, set[str]]:
    """Load the compact LM lexicon extracted from the official master file."""
    with LM_LEXICON_PATH.open(encoding="utf-8") as f:
        raw = json.load(f)
    return {key: set(values) for key, values in raw.items()}


def build_company_aliases(ticker: str, company_name: str | None = None) -> set[str]:
    """Build a small alias set for lightweight relevance heuristics."""
    aliases = {
        ticker.lower(),
        ticker.lower().replace(".", ""),
        ticker.lower().replace(".", "-"),
    }

    if company_name:
        normalized_name = company_name.lower().replace("&", " and ")
        aliases.add(normalized_name)
        for token in _tokenize(normalized_name):
            if token not in COMMON_COMPANY_WORDS and len(token) >= 3:
                aliases.add(token)

    return {alias for alias in aliases if alias}


def _latest_available_value(row, *candidates: str):
    """Return the first non-null candidate column from a macro row."""
    for candidate in candidates:
        if candidate in row.index:
            value = to_python_scalar(row.get(candidate))
            if value is not None:
                return value
    return None


def _pct_change_from_last_distinct(series: pd.Series) -> float | None:
    """Compute pct change between the last two distinct non-null values."""
    cleaned = pd.to_numeric(series, errors="coerce").dropna()
    if cleaned.empty:
        return None
    distinct = cleaned.loc[cleaned.shift() != cleaned]
    if len(distinct) < 2:
        return None
    previous = float(distinct.iloc[-2])
    current = float(distinct.iloc[-1])
    if previous == 0:
        return None
    return (current - previous) / previous


def _growth_from_column(df: pd.DataFrame, column: str) -> float | None:
    """Safely compute growth from the latest two distinct observations."""
    if column not in df.columns:
        return None
    return _pct_change_from_last_distinct(df[column])


def estimate_relevance_score(text: str, aliases: set[str]) -> int:
    """Estimate how likely a news item is to be company-specific."""
    lowered = text.lower()
    return sum(1 for alias in aliases if alias in lowered)


def classify_article_sentiment(text: str) -> dict[str, int | str]:
    """Classify article text with the Loughran-McDonald financial lexicon."""
    tokens = _tokenize(text)
    lm = load_lm_lexicon()
    positive_hits = sum(token in lm["positive"] for token in tokens)
    negative_hits = sum(token in lm["negative"] for token in tokens)
    uncertainty_hits = sum(token in lm["uncertainty"] for token in tokens)
    litigious_hits = sum(token in lm["litigious"] for token in tokens)
    score = positive_hits - negative_hits

    if score > 0:
        label = "positive"
    elif score < 0:
        label = "negative"
    else:
        label = "neutral"

    return {
        "sentiment_score": score,
        "sentiment_label": label,
        "positive_hits": positive_hits,
        "negative_hits": negative_hits,
        "uncertainty_hits": uncertainty_hits,
        "litigious_hits": litigious_hits,
    }


def build_news_macro_snapshot(
    news_csv_path: str,
    macro_csv_path: str,
    ticker: str,
    as_of_date: str | None = None,
    google_trends_csv_path: str | None = None,
    company_name: str | None = None,
    relevance_threshold: int = 1,
    lookback_days: int = 7,
) -> dict:
    """
    Build a standardized news and macro snapshot for a ticker.

    Parameters
    ----------
    news_csv_path : str
        Path to company news CSV data.
    macro_csv_path : str
        Path to macroeconomic CSV data.
    ticker : str
        Stock ticker.
    as_of_date : str | None
        Optional date cutoff in YYYY-MM-DD format.
    company_name : str | None
        Optional company name to improve relevance estimation.
    relevance_threshold : int
        Minimum relevance score used for relevance metadata summaries.
    lookback_days : int
        Number of trailing days of news to include.
    """
    ticker = ticker.upper()

    news_df = pd.read_csv(news_csv_path)
    news_df["ticker"] = news_df["ticker"].astype(str).str.upper()
    news_df = news_df[news_df["ticker"] == ticker].copy()
    news_df["datetime"] = pd.to_datetime(news_df["datetime"], errors="coerce")
    news_df = news_df.dropna(subset=["datetime"]).sort_values("datetime")

    macro_df = pd.read_csv(macro_csv_path)
    macro_df["Date"] = pd.to_datetime(macro_df["Date"], errors="coerce")
    macro_df = macro_df.dropna(subset=["Date"]).sort_values("Date")

    trends_df = None
    if google_trends_csv_path:
        trends_df = pd.read_csv(google_trends_csv_path)
        trends_df["ticker"] = trends_df["ticker"].astype(str).str.upper()
        trends_df = trends_df[trends_df["ticker"] == ticker].copy()
        trends_df["date"] = pd.to_datetime(trends_df["date"], errors="coerce")
        trends_df["search_interest"] = pd.to_numeric(
            trends_df["search_interest"],
            errors="coerce",
        )
        trends_df = trends_df.dropna(subset=["date", "search_interest"]).sort_values("date")

    if macro_df.empty:
        raise ValueError(f"No macro data found in {macro_csv_path}")

    if as_of_date is not None:
        cutoff = pd.Timestamp(as_of_date)
    elif not news_df.empty:
        cutoff = news_df["datetime"].max().normalize()
    else:
        cutoff = macro_df["Date"].max().normalize()

    if not news_df.empty:
        lookback_start = cutoff - pd.Timedelta(days=lookback_days)
        news_df = news_df[
            (news_df["datetime"] <= cutoff + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
            & (news_df["datetime"] >= lookback_start)
        ].copy()

    aliases = build_company_aliases(ticker=ticker, company_name=company_name)

    processed_items: list[dict[str, Any]] = []
    for row in news_df.itertuples(index=False):
        headline = _normalize_text(getattr(row, "headline", ""))
        summary = _normalize_text(getattr(row, "summary", ""))
        combined_text = f"{headline} {summary}".strip()
        relevance_score = estimate_relevance_score(combined_text, aliases)
        sentiment = classify_article_sentiment(combined_text)
        processed_items.append(
            {
                "headline": headline,
                "summary": summary,
                "datetime": str(pd.Timestamp(row.datetime)),
                "source": _normalize_text(getattr(row, "source", "")) or None,
                "url": _normalize_text(getattr(row, "url", "")) or None,
                "relevance_score": relevance_score,
                "estimated_relevance": "high" if relevance_score >= 2 else "low",
                "sentiment_score": sentiment["sentiment_score"],
                "sentiment_label": sentiment["sentiment_label"],
                "lm_positive_hits": sentiment["positive_hits"],
                "lm_negative_hits": sentiment["negative_hits"],
                "lm_uncertainty_hits": sentiment["uncertainty_hits"],
                "lm_litigious_hits": sentiment["litigious_hits"],
            }
        )

    kept_items = processed_items
    relevant_items = [
        item for item in processed_items if item["relevance_score"] >= relevance_threshold
    ]

    macro_cut = macro_df[macro_df["Date"] <= cutoff].copy()
    if macro_cut.empty:
        macro_row = macro_df.iloc[0]
    else:
        macro_row = macro_cut.iloc[-1]

    article_count = len(kept_items)
    positive_articles = sum(item["sentiment_label"] == "positive" for item in kept_items)
    negative_articles = sum(item["sentiment_label"] == "negative" for item in kept_items)
    neutral_articles = sum(item["sentiment_label"] == "neutral" for item in kept_items)
    uncertainty_articles = sum(item["lm_uncertainty_hits"] > 0 for item in kept_items)
    litigious_articles = sum(item["lm_litigious_hits"] > 0 for item in kept_items)
    relevance_ratio = (
        len(relevant_items) / len(processed_items) if processed_items else None
    )
    avg_sentiment_score = (
        float(np.mean([item["sentiment_score"] for item in kept_items]))
        if kept_items
        else None
    )
    avg_uncertainty_hits = (
        float(np.mean([item["lm_uncertainty_hits"] for item in kept_items]))
        if kept_items
        else None
    )
    latest_news_datetime = kept_items[-1]["datetime"] if kept_items else None

    trends_summary = {
        "has_trends_data": False,
        "current_week_avg": None,
        "previous_week_avg": None,
        "wow_change": None,
        "latest_search_interest": None,
        "current_week_peak": None,
    }
    if trends_df is not None and not trends_df.empty:
        current_week_start = cutoff.normalize() - pd.Timedelta(days=6)
        previous_week_start = current_week_start - pd.Timedelta(days=7)
        previous_week_end = current_week_start - pd.Timedelta(days=1)

        current_week_df = trends_df[
            (trends_df["date"] >= current_week_start)
            & (trends_df["date"] <= cutoff.normalize())
        ].copy()
        previous_week_df = trends_df[
            (trends_df["date"] >= previous_week_start)
            & (trends_df["date"] <= previous_week_end)
        ].copy()

        current_week_avg = (
            float(current_week_df["search_interest"].mean())
            if not current_week_df.empty
            else None
        )
        previous_week_avg = (
            float(previous_week_df["search_interest"].mean())
            if not previous_week_df.empty
            else None
        )
        wow_change = None
        if (
            current_week_avg is not None
            and previous_week_avg is not None
            and previous_week_avg != 0
        ):
            wow_change = (current_week_avg - previous_week_avg) / previous_week_avg

        latest_search_interest = (
            float(current_week_df["search_interest"].iloc[-1])
            if not current_week_df.empty
            else None
        )
        current_week_peak = (
            float(current_week_df["search_interest"].max())
            if not current_week_df.empty
            else None
        )
        trends_summary = {
            "has_trends_data": bool(not current_week_df.empty or not previous_week_df.empty),
            "current_week_avg": current_week_avg,
            "previous_week_avg": previous_week_avg,
            "wow_change": wow_change,
            "latest_search_interest": latest_search_interest,
            "current_week_peak": current_week_peak,
        }

    macro_date = pd.Timestamp(macro_row["Date"]).normalize()
    macro_data_lag_days = int((cutoff.normalize() - macro_date).days)
    inflation_rate = _latest_available_value(macro_row, "InflationRate")
    if inflation_rate is None and "CPI" in macro_cut.columns:
        inflation_rate = _pct_change_from_last_distinct(macro_cut["CPI"])

    yield_curve_proxy = _latest_available_value(macro_row, "YieldCurveProxy", "Yield_Spread_10Y2Y")
    if yield_curve_proxy is None:
        ten_year = _latest_available_value(macro_row, "10Y_Treasury")
        two_year = _latest_available_value(macro_row, "2Y_Treasury")
        if ten_year is not None and two_year is not None:
            yield_curve_proxy = float(ten_year) - float(two_year)

    gdp_growth = _latest_available_value(macro_row, "GDPGrowth")
    if gdp_growth is None and "GDP" in macro_cut.columns:
        gdp_growth = _pct_change_from_last_distinct(macro_cut["GDP"])

    industrial_production_growth = _latest_available_value(
        macro_row,
        "IndustrialProductionGrowth",
    )
    if industrial_production_growth is None and "IndustrialProduction" in macro_cut.columns:
        industrial_production_growth = _pct_change_from_last_distinct(
            macro_cut["IndustrialProduction"]
        )
    retail_sales_growth = _growth_from_column(macro_cut, "RetailSales")
    real_retail_sales_growth = _growth_from_column(macro_cut, "RealRetailSales")
    personal_income_growth = _growth_from_column(macro_cut, "PersonalIncome")
    disposable_income_growth = _growth_from_column(macro_cut, "DisposableIncome")
    payroll_employment_growth = _growth_from_column(macro_cut, "PayrollEmployment")
    housing_starts_growth = _growth_from_column(macro_cut, "HousingStarts")
    housing_permits_growth = _growth_from_column(macro_cut, "HousingPermits")
    money_supply_m2_growth = _growth_from_column(macro_cut, "MoneySupply_M2")
    dollar_index_growth = _growth_from_column(macro_cut, "DollarIndex")
    wti_oil_growth = _growth_from_column(macro_cut, "WTI_Oil")
    bank_credit_growth = _growth_from_column(macro_cut, "BankCredit")

    return {
        "ticker": ticker,
        "analysis_date": str(cutoff.date()),
        "company_info": {
            "company_name": company_name,
        },
        "news_macro_features": {
            "news_policy": {
                "relevance_mode": "keep_all",
                "relevance_threshold": relevance_threshold,
                "lookback_days": lookback_days,
            },
            "news_summary": {
                "article_count": article_count,
                "raw_article_count": len(processed_items),
                "relevant_article_count": len(relevant_items),
                "relevance_ratio": relevance_ratio,
                "positive_articles": positive_articles,
                "negative_articles": negative_articles,
                "neutral_articles": neutral_articles,
                "avg_sentiment_score": avg_sentiment_score,
                "uncertainty_articles": uncertainty_articles,
                "litigious_articles": litigious_articles,
                "avg_uncertainty_hits": avg_uncertainty_hits,
                "latest_news_datetime": latest_news_datetime,
            },
            "trends_summary": trends_summary,
            "macro_features": {
                "macro_date": str(macro_date.date()),
                "macro_data_lag_days": macro_data_lag_days,
                "three_month_treasury": _latest_available_value(macro_row, "3M_Treasury"),
                "two_year_treasury": _latest_available_value(macro_row, "2Y_Treasury"),
                "five_year_treasury": _latest_available_value(macro_row, "5Y_Treasury"),
                "fed_funds_rate": _latest_available_value(macro_row, "Fed_Funds_Rate"),
                "ten_year_treasury": _latest_available_value(macro_row, "10Y_Treasury"),
                "thirty_year_treasury": _latest_available_value(macro_row, "30Y_Treasury"),
                "yield_spread_10y2y": _latest_available_value(
                    macro_row, "Yield_Spread_10Y2Y"
                ),
                "yield_spread_10y3m": _latest_available_value(
                    macro_row, "Yield_Spread_10Y3M"
                ),
                "vix": _latest_available_value(macro_row, "VIX"),
                "credit_spread": _latest_available_value(macro_row, "CreditSpread"),
                "dollar_index": _latest_available_value(macro_row, "DollarIndex"),
                "dollar_index_growth": dollar_index_growth,
                "wti_oil": _latest_available_value(macro_row, "WTI_Oil"),
                "wti_oil_growth": wti_oil_growth,
                "bank_credit": _latest_available_value(macro_row, "BankCredit"),
                "bank_credit_growth": bank_credit_growth,
                "financial_stress_index": _latest_available_value(
                    macro_row, "FinancialStressIndex"
                ),
                "cpi": _latest_available_value(macro_row, "CPI"),
                "core_cpi": _latest_available_value(macro_row, "Core_CPI"),
                "pce": _latest_available_value(macro_row, "PCE"),
                "core_pce": _latest_available_value(macro_row, "Core_PCE"),
                "ppi": _latest_available_value(macro_row, "PPI"),
                "inflation_rate": inflation_rate,
                "unemployment": _latest_available_value(macro_row, "Unemployment"),
                "payroll_employment": _latest_available_value(
                    macro_row, "PayrollEmployment"
                ),
                "payroll_employment_growth": payroll_employment_growth,
                "labor_force_participation": _latest_available_value(
                    macro_row, "LaborForceParticipation"
                ),
                "yield_curve_proxy": yield_curve_proxy,
                "industrial_production": _latest_available_value(
                    macro_row, "IndustrialProduction"
                ),
                "gdp_growth": gdp_growth,
                "industrial_production_growth": industrial_production_growth,
                "capacity_utilization": _latest_available_value(
                    macro_row, "CapacityUtilization"
                ),
                "retail_sales": _latest_available_value(macro_row, "RetailSales"),
                "retail_sales_growth": retail_sales_growth,
                "real_retail_sales": _latest_available_value(
                    macro_row, "RealRetailSales"
                ),
                "real_retail_sales_growth": real_retail_sales_growth,
                "personal_income": _latest_available_value(
                    macro_row, "PersonalIncome"
                ),
                "personal_income_growth": personal_income_growth,
                "disposable_income": _latest_available_value(
                    macro_row, "DisposableIncome"
                ),
                "disposable_income_growth": disposable_income_growth,
                "consumer_sentiment": _latest_available_value(
                    macro_row, "ConsumerSentiment"
                ),
                "housing_starts": _latest_available_value(macro_row, "HousingStarts"),
                "housing_starts_growth": housing_starts_growth,
                "housing_permits": _latest_available_value(macro_row, "HousingPermits"),
                "housing_permits_growth": housing_permits_growth,
                "case_shiller_home_price": _latest_available_value(
                    macro_row, "CaseShillerHomePrice"
                ),
                "money_supply_m2": _latest_available_value(macro_row, "MoneySupply_M2"),
                "money_supply_m2_growth": money_supply_m2_growth,
                "gdp": _latest_available_value(macro_row, "GDP"),
                "gdp_per_capita": _latest_available_value(macro_row, "GDP_Per_Capita"),
            },
            "recent_news_items": kept_items,
        },
    }
