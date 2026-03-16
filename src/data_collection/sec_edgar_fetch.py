import requests
import pandas as pd
import os
import time

HEADERS = {
    "User-Agent": "DebateTrader Research (lh1085@georgetown.edu)"
}

TICKERS = ["AAPL", "GOOGL", "LLY", "BRK.B", "AMZN", "XOM"]

SAVE_DIR = "data/sample/SEC_EDGAR_fundamentals"

START_YEAR = 2024


# create directory
def ensure_dir():

    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)


# normalize ticker
def normalize_ticker(ticker):

    mapping = {
        "BRK.B": "BRK-B"
    }

    return mapping.get(ticker, ticker)


# ticker -> cik
def ticker_to_cik():

    url = "https://www.sec.gov/files/company_tickers.json"

    r = requests.get(url, headers=HEADERS)

    data = r.json()

    cik_map = {}

    for item in data.values():

        ticker = item["ticker"]

        cik = str(item["cik_str"]).zfill(10)

        cik_map[ticker] = cik

    return cik_map


# extract metric
def extract_metric(companyfacts, metric):

    try:

        units = companyfacts["facts"]["us-gaap"][metric]["units"]

        if "USD" not in units:
            return None

        df = pd.DataFrame(units["USD"])

        df = df[["end", "val"]]

        df = df.rename(columns={"end": "Date", "val": metric})

        df["Date"] = pd.to_datetime(df["Date"])

        df = df[df["Date"].dt.year >= START_YEAR]

        df = df.sort_values("Date")

        return df

    except:

        return None


# revenue fallback
def extract_revenue(companyfacts):

    candidates = [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet"
    ]

    for metric in candidates:

        df = extract_metric(companyfacts, metric)

        if df is not None and not df.empty:

            df = df.rename(columns={metric: "Revenue"})

            return df

    return None


# operating income fallback
def extract_operating_income(companyfacts):

    candidates = [
        "OperatingIncomeLoss",
        "IncomeFromOperations",
        "OperatingIncome",
        "IncomeLossFromOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "OperatingIncomeLossIncludingPortionAttributableToNoncontrollingInterest"
    ]

    for metric in candidates:

        df = extract_metric(companyfacts, metric)

        if df is not None and not df.empty:

            df = df.rename(columns={metric: "OperatingIncome"})

            return df

    return None


# equity fallback
def extract_equity(companyfacts):

    candidates = [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    ]

    for metric in candidates:

        df = extract_metric(companyfacts, metric)

        if df is not None and not df.empty:

            df = df.rename(columns={metric: "Equity"})

            return df

    return None


# liabilities fallback
def extract_liabilities(companyfacts, assets_df=None, equity_df=None):

    total = extract_metric(companyfacts, "Liabilities")

    if total is not None and not total.empty:

        total = total.rename(columns={"Liabilities": "Liabilities"})

        return total

    current = extract_metric(companyfacts, "LiabilitiesCurrent")

    noncurrent = extract_metric(companyfacts, "LiabilitiesNoncurrent")

    if current is not None and noncurrent is not None:

        df = pd.merge(current, noncurrent, on="Date", how="outer")

        df["Liabilities"] = df["LiabilitiesCurrent"] + df["LiabilitiesNoncurrent"]

        df = df[["Date", "Liabilities"]]

        return df

    if assets_df is not None and equity_df is not None:

        df = pd.merge(assets_df, equity_df, on="Date", how="inner")

        df["Liabilities"] = df["Assets"] - df["Equity"]

        df = df[["Date", "Liabilities"]]

        return df

    return None


# compute financial ratios
def compute_financial_ratios(df):

    df = df.sort_values("Date")

    # Revenue Growth
    if "Revenue" in df.columns:
        df["RevenueGrowth"] = df["Revenue"].pct_change()
    else:
        df["RevenueGrowth"] = None

    # Operating Margin
    if "OperatingIncome" in df.columns and "Revenue" in df.columns:
        df["OperatingMargin"] = df["OperatingIncome"] / df["Revenue"]
    else:
        df["OperatingMargin"] = None

    # Debt Ratio
    if "Liabilities" in df.columns and "Assets" in df.columns:
        df["DebtRatio"] = df["Liabilities"] / df["Assets"]
    else:
        df["DebtRatio"] = None

    # ROE
    if "NetIncome" in df.columns and "Equity" in df.columns:
        df["ROE"] = df["NetIncome"] / df["Equity"]
    else:
        df["ROE"] = None

    return df


# fetch financial data
def fetch_financials(cik):

    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

    r = requests.get(url, headers=HEADERS)

    if r.status_code != 200:
        print("SEC error:", r.status_code)
        return None

    companyfacts = r.json()

    revenue = extract_revenue(companyfacts)

    net_income = extract_metric(companyfacts, "NetIncomeLoss")

    operating_income = extract_operating_income(companyfacts)

    assets = extract_metric(companyfacts, "Assets")

    equity = extract_equity(companyfacts)

    liabilities = extract_liabilities(companyfacts, assets, equity)

    dfs = []

    if revenue is not None:
        dfs.append(revenue)

    if net_income is not None:
        dfs.append(net_income.rename(columns={"NetIncomeLoss": "NetIncome"}))

    if operating_income is not None:
        dfs.append(operating_income)

    if assets is not None:
        dfs.append(assets.rename(columns={"Assets": "Assets"}))

    if liabilities is not None:
        dfs.append(liabilities)

    if equity is not None:
        dfs.append(equity)

    if len(dfs) == 0:
        return None

    df_final = dfs[0]

    for df in dfs[1:]:

        df_final = pd.merge(df_final, df, on="Date", how="outer")

    df_final = df_final.sort_values("Date")

    df_final = df_final.drop_duplicates(subset="Date")

    df_final = compute_financial_ratios(df_final)

    return df_final



# save csv
def save_data(ticker, df):

    filepath = os.path.join(SAVE_DIR, f"{ticker}_fundamentals.csv")

    df.to_csv(filepath, index=False)

    print("Saved:", filepath)


# pipeline
def run_pipeline():

    ensure_dir()

    cik_map = ticker_to_cik()

    for ticker in TICKERS:

        print("Processing:", ticker)

        ticker_lookup = normalize_ticker(ticker)

        cik = cik_map.get(ticker_lookup)

        if cik is None:

            print("CIK not found:", ticker_lookup)

            continue

        df = fetch_financials(cik)

        if df is None:

            print("No data:", ticker)

            continue

        save_data(ticker, df)

        time.sleep(0.2)


# run
if __name__ == "__main__":

    run_pipeline()