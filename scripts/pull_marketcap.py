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

# ---- IMPORTANT: SEC requires a descriptive User-Agent ----
# Put something that identifies you + a contact (email is ideal).
SEC_HEADERS = {
    "User-Agent": "mjmonnot ai-hyperscalers-marketcap-race (contact: your-email@example.com)",
    "Accept-Encoding": "gzip, deflate",
}

def fetch_fmp_historical_marketcap(symbol: str, api_key: str) -> pd.DataFrame:
    """Try FMP historical market cap (may be paywalled for some symbols)."""
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

def fetch_stooq_prices(symbol: str) -> pd.DataFrame:
    """
    Stooq tickers are typically lowercase with .us for US equities, e.g. msft.us.
    For ADRs (TSM.us) this usually works fine too.
    """
    stooq = f"{symbol.lower()}.us"
    df = pdr.DataReader(stooq, "stooq")  # Open/High/Low/Close/Volume
    df = df.sort_index()
    df = df.reset_index().rename(columns={"Date": "date", "Close": "close"})
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "close"]]

def to_monthly_eom(df: pd.DataFrame, date_col="date") -> pd.DataFrame:
    df = df.copy()
    df = df.set_index(date_col).sort_index()
    return df.resample("ME").last().dropna().reset_index()

# ---------------- SEC HELPERS ----------------

def get_cik_for_ticker(ticker: str) -> str:
    """
    Map ticker -> CIK using SEC company_tickers.json.
    Returns CIK as zero-padded 10-digit string.
    """
    url = "https://www.sec.gov/files/company_tickers.json"
    r = requests.get(url, headers=SEC_HEADERS, timeout=60)
    r.raise_for_status()
    data = r.json()  # dict keyed by numeric strings: {"0": {...}, "1": {...}}
    ticker_up = ticker.upper()

    for _, row in data.items():
        if row.get("ticker", "").upper() == ticker_up:
            cik_int = int(row["cik_str"])
            return f"{cik_int:010d}"

    raise RuntimeError(f"Could not find CIK for ticker {ticker} via SEC mapping")

def fetch_sec_shares_timeseries(cik10: str) -> pd.DataFrame:
    """
    Fetch shares outstanding series from SEC companyfacts.
    We look for common share tags that appear across filers.
    Returns a dataframe with columns: date, shares
    """
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
    r = requests.get(url, headers=SEC_HEADERS, timeout=60)
    r.raise_for_status()
    js = r.json()

    facts = js.get("facts", {}).get("dei", {})
    # Common tags seen in filings:
    candidate_tags = [
        "EntityCommonStockSharesOutstanding",
        "CommonStockSharesOutstanding",
    ]

    series = None
    for tag in candidate_tags:
        node = facts.get(tag)
        if node and "units" in node:
            # Prefer shares ("shares") unit if present
            units = node["units"]
            if "shares" in units:
                series = units["shares"]
                break

    if series is None:
        raise RuntimeError(f"No SEC shares series found for CIK{cik10} in candidate tags")

    df = pd.DataFrame(series)
    # SEC items typically include: end, val, fy, fp, form, filed, frame (optional)
    df = df.rename(columns={"end": "date", "val": "shares"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["shares"] = pd.to_numeric(df["shares"], errors="coerce")
    df = df.dropna(subset=["date", "shares"]).sort_values("date")

    # Keep the last observation per date
    df = df.groupby("date", as_index=False)["shares"].last()
    return df

def monthly_marketcap_from_price_and_shares(prices_daily: pd.DataFrame, shares_ts: pd.DataFrame) -> pd.DataFrame:
    """
    Create monthly EOM market cap from:
      - daily close prices
      - irregular shares observations (quarterly-ish)

    Approach:
      1) convert prices to monthly EOM close
      2) merge shares onto monthly dates
      3) forward-fill shares
      4) market cap = close * shares
    """
    m = to_monthly_eom(prices_daily)  # date, close

    # Merge shares on date and forward-fill
    shares_ts = shares_ts.copy()
    shares_ts = shares_ts.sort_values("date")

    # Left-merge and forward fill
    merged = m.merge(shares_ts, on="date", how="left").sort_values("date")
    merged["shares"] = merged["shares"].ffill()

    # If shares are still missing at the beginning, backfill once
    merged["shares"] = merged["shares"].bfill()

    if merged["shares"].isna().any():
        raise RuntimeError("Shares still missing after fill; cannot compute market cap")

    merged["value"] = (merged["close"] * merged["shares"]) / 1e9  # $B
    return merged[["date", "value"]]

# ---------------- MAIN ----------------

def main():
    api_key = os.getenv("FMP_API_KEY", "").strip()

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    rows = []

    for t in cfg["tickers"]:
        symbol = t["ticker"]
        name = t.get("name", symbol)
        category = t.get("category", "Unknown")

        used = None

        # 1) Try true historical market cap from FMP (best quality)
        try:
            if not api_key:
                raise PermissionError("No FMP_API_KEY set")
            df = fetch_fmp_historical_marketcap(symbol, api_key)
            used = "FMP-historical-marketcap"

        except PermissionError:
            # 2) Fallback: approximate market cap using Stooq monthly close * SEC shares series
            used = "Stooq close × SEC shares (approx)"

            prices = fetch_stooq_prices(symbol)

            # SEC shares
            cik10 = get_cik_for_ticker(symbol)
            shares_ts = fetch_sec_shares_timeseries(cik10)

            df = monthly_marketcap_from_price_and_shares(prices, shares_ts)

        # Decorate and store
        df["name"] = name
        df["category"] = category
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

        rows.append(df[["date", "name", "value", "category"]])

        print(f"{symbol}: OK ({used}) rows={len(df)}")

        # Be polite to public endpoints
        time.sleep(0.25)

    out = pd.concat(rows, ignore_index=True)
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["date", "name", "value"]).sort_values(["date", "value"], ascending=[True, False])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_PATH, index=False)
    print("Wrote:", OUT_PATH)

if __name__ == "__main__":
    main()
