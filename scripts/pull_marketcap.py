import os
import json
import time
import requests
import pandas as pd
from pathlib import Path
from pandas_datareader import data as pdr

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "tickers.json"
OUT_PATH = ROOT / "data" / "processed" / "marketcap_monthly.csv"

FMP_BASE = "https://financialmodelingprep.com"

def fetch_fmp_historical_marketcap(symbol: str, api_key: str) -> pd.DataFrame:
    """Try FMP historical market cap. May return 402 for free plans."""
    url = f"{FMP_BASE}/stable/historical-market-capitalization"
    r = requests.get(url, params={"symbol": symbol, "apikey": api_key}, timeout=60)
    if r.status_code == 402:
        raise PermissionError("FMP 402 Payment Required")
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    df["value"] = df["marketCap"] / 1e9  # $B
    return df[["date", "value"]]

def fetch_fmp_shares_outstanding(symbol: str, api_key: str) -> float:
    """
    Get *current* shares outstanding from a free-ish endpoint.
    Even if historical market cap is paywalled, quote/profile endpoints often work.
    """
    url = f"{FMP_BASE}/api/v3/profile/{symbol}"
    r = requests.get(url, params={"apikey": api_key}, timeout=60)
    r.raise_for_status()
    js = r.json()
    if not js:
        raise RuntimeError(f"No profile data for {symbol}")
    shares = js[0].get("sharesOutstanding")
    if shares is None:
        raise RuntimeError(f"Missing sharesOutstanding for {symbol}")
    return float(shares)

def fetch_stooq_prices(symbol: str) -> pd.DataFrame:
    """
    Stooq tickers are typically lowercase with .us suffix for US equities, e.g. msft.us
    Returns a DataFrame indexed by date with an 'Adj Close' column.
    """
    stooq = f"{symbol.lower()}.us"
    df = pdr.DataReader(stooq, "stooq")  # columns: Open, High, Low, Close, Volume
    df = df.sort_index()
    # Stooq does not always provide adjusted close; use Close for simplicity
    df = df.reset_index().rename(columns={"Date": "date", "Close": "close"})
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "close"]]

def to_monthly_eom(df: pd.DataFrame, date_col="date") -> pd.DataFrame:
    df = df.copy()
    df = df.set_index(date_col).sort_index()
    return df.resample("ME").last().dropna().reset_index()

def main():
    api_key = os.getenv("FMP_API_KEY", "").strip()

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    rows = []

    for t in cfg["tickers"]:
        symbol = t["ticker"]
        name = t.get("name", symbol)
        category = t.get("category", "Unknown")

        # --- Try FMP historical market cap first ---
        used = "FMP-historical-marketcap"
        try:
            if not api_key:
                raise PermissionError("No FMP_API_KEY set")
            df = fetch_fmp_historical_marketcap(symbol, api_key)

        except PermissionError:
            # --- Fallback: Stooq prices * current shares outstanding ---
            used = "Stooq-price × current shares (approx)"
            if not api_key:
                raise RuntimeError(
                    "FMP_API_KEY is required for the fallback too (to fetch sharesOutstanding). "
                    "Set the secret FMP_API_KEY in GitHub."
                )

            shares = fetch_fmp_shares_outstanding(symbol, api_key)
            prices = fetch_stooq_prices(symbol)
            m = to_monthly_eom(prices)
            m["value"] = (m["close"] * shares) / 1e9  # $B
            df = m[["date", "value"]]

        df["name"] = name
        df["category"] = category
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")

        rows.append(df[["date", "name", "value", "category"]])

        # be polite to APIs
        time.sleep(0.25)

        print(f"{symbol}: OK ({used}) rows={len(df)}")

    out = pd.concat(rows, ignore_index=True)
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["date", "name", "value"]).sort_values(["date", "value"], ascending=[True, False])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_PATH, index=False)
    print("Wrote:", OUT_PATH)

if __name__ == "__main__":
    main()
