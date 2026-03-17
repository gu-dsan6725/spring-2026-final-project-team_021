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

LM_LEXICON_PATH = Path("data/reference/lm_lexicon.json")

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

    macro_date = pd.Timestamp(macro_row["Date"]).normalize()
    macro_data_lag_days = int((cutoff.normalize() - macro_date).days)

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
            "macro_features": {
                "macro_date": str(macro_date.date()),
                "macro_data_lag_days": macro_data_lag_days,
                "fed_funds_rate": to_python_scalar(macro_row.get("Fed_Funds_Rate")),
                "inflation_rate": to_python_scalar(macro_row.get("InflationRate")),
                "unemployment": to_python_scalar(macro_row.get("Unemployment")),
                "ten_year_treasury": to_python_scalar(macro_row.get("10Y_Treasury")),
                "yield_curve_proxy": to_python_scalar(macro_row.get("YieldCurveProxy")),
                "gdp_growth": to_python_scalar(macro_row.get("GDPGrowth")),
                "industrial_production_growth": to_python_scalar(
                    macro_row.get("IndustrialProductionGrowth")
                ),
            },
            "recent_news_items": kept_items,
        },
    }
