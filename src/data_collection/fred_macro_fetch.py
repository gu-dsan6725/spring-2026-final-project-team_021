import os
import pandas as pd
from fredapi import Fred


# FRED API key
FRED_KEY = "3b3e95c3c710ec27689f1b341582c671"

fred = Fred(api_key=FRED_KEY)

# date range
START_DATE = "2025-07-01"
END_DATE = "2025-12-31"


# save directory
BASE_DIR = "data"
MACRO_DIR = os.path.join(BASE_DIR, "macro")


# macro indicators
INDICATORS = {

    "Fed_Funds_Rate": "FEDFUNDS",
    "CPI": "CPIAUCSL",
    "Unemployment": "UNRATE",
    "10Y_Treasury": "DGS10",
    "GDP": "GDP",
    "IndustrialProduction": "INDPRO"
}


# create directories
def ensure_dir():

    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)

    if not os.path.exists(MACRO_DIR):
        os.makedirs(MACRO_DIR)


# fetch macro data
def fetch_macro():

    macro_data = {}

    for name, code in INDICATORS.items():

        print("Fetching:", name)

        series = fred.get_series(
            code,
            observation_start=START_DATE,
            observation_end=END_DATE
        )

        macro_data[name] = series

    df = pd.DataFrame(macro_data)

    df.index = pd.to_datetime(df.index)

    df = df.sort_index()

    # forward fill lower frequency data
    df = df.fillna(method="ffill")

    # convert to monthly frequency
    df = df.resample("M").last()

    return df


# compute macro features
def compute_macro_features(df):

    if "CPI" in df.columns:
        df["InflationRate"] = df["CPI"].pct_change()

    if "10Y_Treasury" in df.columns and "Fed_Funds_Rate" in df.columns:
        df["YieldCurveProxy"] = df["10Y_Treasury"] - df["Fed_Funds_Rate"]

    if "GDP" in df.columns:
        df["GDPGrowth"] = df["GDP"].pct_change()

    if "IndustrialProduction" in df.columns:
        df["IndustrialProductionGrowth"] = df["IndustrialProduction"].pct_change()

    return df


# save csv
def save_data(df):

    filepath = os.path.join(MACRO_DIR, "macro_data.csv")

    df = df.reset_index()

    df = df.rename(columns={"index": "Date"})

    df.to_csv(filepath, index=False)

    print("Saved:", filepath)


# pipeline
def run_pipeline():

    ensure_dir()

    macro = fetch_macro()

    macro = compute_macro_features(macro)

    save_data(macro)

    print("\nMacro Data Preview:\n")
    print(macro.tail())


# run
if __name__ == "__main__":

    run_pipeline()