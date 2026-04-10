import os
import sys
import pandas as pd
from fredapi import Fred
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from src.data_collection.config import (SAMPLE_START, SAMPLE_END, MACRO_DIR)

# FRED API key
FRED_KEY = "3b3e95c3c710ec27689f1b341582c671"

# 35 Macro Indicators
INDICATORS = {

# Interest rates
"Fed_Funds_Rate": ("FEDFUNDS","monthly"),
"3M_Treasury": ("DGS3MO","daily"),
"2Y_Treasury": ("DGS2","daily"),
"5Y_Treasury": ("DGS5","daily"),
"10Y_Treasury": ("DGS10","daily"),
"30Y_Treasury": ("DGS30","daily"),
"Yield_Spread_10Y2Y": ("T10Y2Y","daily"),
"Yield_Spread_10Y3M": ("T10Y3M","daily"),

# Inflation
"CPI": ("CPIAUCSL","monthly"),
"Core_CPI": ("CPILFESL","monthly"),
"PCE": ("PCE","monthly"),
"Core_PCE": ("PCEPILFE","monthly"),
"PPI": ("PPIACO","monthly"),

# Economic activity
"GDP": ("GDP","quarterly"),
"GDP_Per_Capita": ("A939RX0Q048SBEA","quarterly"),
"IndustrialProduction": ("INDPRO","monthly"),
"CapacityUtilization": ("TCU","monthly"),

# Labor market
"Unemployment": ("UNRATE","monthly"),
"PayrollEmployment": ("PAYEMS","monthly"),
"LaborForceParticipation": ("CIVPART","monthly"),

# Consumption
"RetailSales": ("RSAFS","monthly"),
"RealRetailSales": ("RRSFS","monthly"),
"PersonalIncome": ("PI","monthly"),
"DisposableIncome": ("DSPIC96","monthly"),
"ConsumerSentiment": ("UMCSENT","monthly"),

# Housing
"HousingStarts": ("HOUST","monthly"),
"HousingPermits": ("PERMIT","monthly"),
"CaseShillerHomePrice": ("CSUSHPINSA","monthly"),

# Liquidity
"MoneySupply_M2": ("M2SL","monthly"),
"BankCredit": ("TOTBKCR","weekly"),

# Risk
"VIX": ("VIXCLS","daily"),
"CreditSpread": ("BAA10Y","daily"),
"FinancialStressIndex": ("STLFSI4","weekly"),

# Currency
"DollarIndex": ("DTWEXBGS","daily"),

# Commodity
"WTI_Oil": ("DCOILWTICO","daily")
}


# Create directories
def ensure_dir():
    os.makedirs(MACRO_DIR, exist_ok=True)


# Robust FRED fetch
def fetch_series(code: str, start: str, end: str, fred_client: Fred):
    for attempt in range(3):
        try:
            series = fred_client.get_series(
                code,
                observation_start=start,
                observation_end=end,
            )
            series.index = pd.to_datetime(series.index)
            series = series.replace(".", pd.NA)
            series = series.astype(float)
            return series
        except Exception as e:
            print(f"Retry {attempt+1} for {code} | Error:", e)
            time.sleep(2)
    print("Failed permanently:", code)
    return None


# Fetch macro data
def fetch_macro(start: str, end: str, fred_client: Fred):
    daily_data = {}
    weekly_data = {}
    monthly_data = {}
    quarterly_data = {}

    for name, (code, freq) in INDICATORS.items():
        print("Fetching:", name)
        series = fetch_series(code, start=start, end=end, fred_client=fred_client)
        if series is None:
            continue
        if freq == "daily":
            daily_data[name] = series
        elif freq == "weekly":
            weekly_data[name] = series
        elif freq == "monthly":
            monthly_data[name] = series
        elif freq == "quarterly":
            quarterly_data[name] = series
        time.sleep(0.25)  # avoid rate limit

    df_daily = pd.DataFrame(daily_data).sort_index()
    df_weekly = pd.DataFrame(weekly_data).sort_index()
    df_monthly = pd.DataFrame(monthly_data).sort_index()
    df_quarterly = pd.DataFrame(quarterly_data).sort_index()

    return df_daily, df_weekly, df_monthly, df_quarterly


# Build daily macro dataset
def build_daily_macro(df_daily, df_weekly, df_monthly, df_quarterly):

    df = df_daily.copy()

    if not df_weekly.empty:
        df = df.join(df_weekly.resample("D").ffill())

    if not df_monthly.empty:
        df = df.join(df_monthly.resample("D").ffill())

    if not df_quarterly.empty:
        df = df.join(df_quarterly.resample("D").ffill())

    df = df.sort_index()

    return df

# Save datasets
def save_data(df_daily, df_weekly, df_monthly, df_quarterly, df_all_daily):

    df_daily.index.name = "Date"
    df_weekly.index.name = "Date"
    df_monthly.index.name = "Date"
    df_quarterly.index.name = "Date"
    df_all_daily.index.name = "Date"

    df_daily.to_csv(os.path.join(MACRO_DIR, "macro_daily_raw.csv"))
    df_weekly.to_csv(os.path.join(MACRO_DIR, "macro_weekly_raw.csv"))
    df_monthly.to_csv(os.path.join(MACRO_DIR, "macro_monthly_raw.csv"))
    df_quarterly.to_csv(os.path.join(MACRO_DIR, "macro_quarterly_raw.csv"))

    df_all_daily.to_csv(os.path.join(MACRO_DIR, "macro_all_daily_ffill.csv"))

    print("\nSaved macro datasets.")


def run(
    start: str = SAMPLE_START,
    end: str = SAMPLE_END,
    macro_dir: str = MACRO_DIR,
) -> None:
    """Collect all FRED macro indicators over [start, end] and save to *macro_dir*."""
    os.makedirs(macro_dir, exist_ok=True)
    fred_client = Fred(api_key=FRED_KEY)
    df_daily, df_weekly, df_monthly, df_quarterly = fetch_macro(
        start=start, end=end, fred_client=fred_client
    )
    df_all_daily = build_daily_macro(df_daily, df_weekly, df_monthly, df_quarterly)
    save_data(df_daily, df_weekly, df_monthly, df_quarterly, df_all_daily)
    print("\nPreview:\n")
    print(df_all_daily.head())
    print("\nShape:", df_all_daily.shape)
    print("\nDone.")


# backward-compatible entry point
def run_pipeline():
    run()


# Run the pipeline
if __name__ == "__main__":
    run_pipeline()