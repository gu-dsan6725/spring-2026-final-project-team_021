import os
import finnhub
import pandas as pd
from datetime import datetime


# API KEY
API_KEY = "d6qooa9r01qgdhqbpgm0d6qooa9r01qgdhqbpgmg"

client = finnhub.Client(api_key=API_KEY)


# stock universe
TICKERS = ["AAPL", "GOOGL", "LLY", "BRK.B", "AMZN", "XOM"]


# date range
START_DATE = "2025-07-01"
END_DATE = "2025-12-31"


# save directory
BASE_DIR = "data/sample"
NEWS_DIR = os.path.join(BASE_DIR, "news")

# create directories
def ensure_dir():

    os.makedirs(BASE_DIR, exist_ok=True)
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
def fetch_news():

    all_news = {}

    ranges = generate_month_ranges(START_DATE, END_DATE)

    for ticker in TICKERS:

        print("\nFetching news for:", ticker)

        frames = []

        for start, end in ranges:

            print("   range:", start, "->", end)

            news = client.company_news(
                ticker,
                _from=start,
                to=end
            )

            df = pd.DataFrame(news)

            if not df.empty:

                df = df[[
                    "headline",
                    "summary",
                    "datetime",
                    "source",
                    "url"
                ]]

                df = convert_timestamp(df)

                df["ticker"] = ticker

                frames.append(df)

        if len(frames) > 0:

            combined = pd.concat(frames)

            # remove duplicates
            combined = combined.drop_duplicates(subset=["headline", "datetime"])

            combined = combined.sort_values("datetime")

            all_news[ticker] = combined

        else:

            all_news[ticker] = pd.DataFrame()

    return all_news


# save news
def save_news(news_dict):

    for ticker, df in news_dict.items():

        if df.empty:
            print("No news for:", ticker)
            continue

        filepath = os.path.join(
            NEWS_DIR,
            f"{ticker}_news.csv"
        )

        df.to_csv(filepath, index=False)

        print("Saved:", filepath)


# combine dataset
def combine_news(news_dict):

    frames = []

    for df in news_dict.values():

        if not df.empty:
            frames.append(df)

    if len(frames) == 0:
        return None

    combined = pd.concat(frames)

    combined = combined.sort_values("datetime")

    combined = combined.drop_duplicates(subset=["headline", "datetime"])

    return combined


# pipeline
def run_pipeline():

    ensure_dir()

    news = fetch_news()

    save_news(news)

    combined = combine_news(news)

    if combined is not None:

        combined_path = os.path.join(
            NEWS_DIR,
            "all_news.csv"
        )

        combined.to_csv(combined_path, index=False)

        print("\nSaved combined news:", combined_path)

        print("\nNews preview:\n")

        print(combined.head())


# run
if __name__ == "__main__":

    run_pipeline()