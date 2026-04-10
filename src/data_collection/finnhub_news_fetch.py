import os
import sys
import finnhub
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from src.data_collection.config import (TICKERS, SAMPLE_START, SAMPLE_END, NEWS_DIR)

# API KEY
API_KEY = "d6qooa9r01qgdhqbpgm0d6qooa9r01qgdhqbpgmg"


# create directories
def ensure_dir():
    os.makedirs(NEWS_DIR, exist_ok=True)


# convert timestamp
def convert_timestamp(df):
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], unit="s")
    return df


# generate monthly ranges
def generate_month_ranges(start, end):
    months = pd.date_range(start, end, freq="MS")
    ranges = []
    for m in months:
        start_date = m.strftime("%Y-%m-%d")
        end_date = (m + pd.offsets.MonthEnd(1)).strftime("%Y-%m-%d")
        ranges.append((start_date, end_date))
    return ranges


# fetch news
def fetch_news(tickers: list[str], start: str, end: str, client: finnhub.Client) -> dict:
    all_news = {}
    ranges = generate_month_ranges(start, end)

    for ticker in tickers:
        print("\nFetching news for:", ticker)
        frames = []
        for rng_start, rng_end in ranges:
            print("   range:", rng_start, "->", rng_end)
            news = client.company_news(ticker, _from=rng_start, to=rng_end)
            df = pd.DataFrame(news)
            if not df.empty:
                df = df[["headline", "summary", "datetime", "source", "url"]]
                df = convert_timestamp(df)
                df["ticker"] = ticker
                frames.append(df)

        if frames:
            combined = pd.concat(frames)
            combined = combined.drop_duplicates(subset=["headline", "datetime"])
            combined = combined.sort_values("datetime")
            all_news[ticker] = combined
        else:
            all_news[ticker] = pd.DataFrame()

    return all_news


# save news
def save_news(news_dict: dict, news_dir: str = NEWS_DIR) -> None:
    for ticker, df in news_dict.items():
        if df.empty:
            print("No news for:", ticker)
            continue
        filepath = os.path.join(news_dir, f"{ticker}_news.csv")
        df.to_csv(filepath, index=False)
        print("Saved:", filepath)


# combine dataset
def combine_news(news_dict: dict) -> pd.DataFrame | None:
    frames = [df for df in news_dict.values() if not df.empty]
    if not frames:
        return None
    combined = pd.concat(frames)
    combined = combined.sort_values("datetime")
    combined = combined.drop_duplicates(subset=["headline", "datetime"])
    return combined


def run(
    tickers: list[str] = TICKERS,
    start: str = SAMPLE_START,
    end: str = SAMPLE_END,
    news_dir: str = NEWS_DIR,
) -> None:
    """Collect Finnhub news for *tickers* over [start, end] and save to *news_dir*."""
    os.makedirs(news_dir, exist_ok=True)
    client = finnhub.Client(api_key=API_KEY)
    news = fetch_news(tickers=tickers, start=start, end=end, client=client)
    save_news(news, news_dir=news_dir)
    combined = combine_news(news)
    if combined is not None:
        combined_path = os.path.join(news_dir, "all_news.csv")
        combined.to_csv(combined_path, index=False)
        print("\nSaved combined news:", combined_path)
        print("\nNews preview:\n")
        print(combined.head())


# backward-compatible entry point
def run_pipeline():
    run()


if __name__ == "__main__":
    run_pipeline()