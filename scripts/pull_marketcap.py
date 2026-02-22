#!/usr/bin/env python3
"""
AI Hyperscalers Market Cap Pull

Goal:
- Produce a tidy monthly (end-of-month) market cap dataset for the D3 bar chart race.

Strategy:
1) Prefer "true" historical market cap from Financial Modeling Prep (FMP) when available.
2) If FMP returns 402 (paywalled) for a ticker, compute an approximation:
   - market cap ≈ (monthly EOM close price from Stooq) × (shares outstanding from SEC XBRL companyfacts)
3) If SEC shares cannot be obtained for a ticker, SKIP that ticker (do not fail the pipeline).

Output:
- data/processed/marketcap_monthly.csv
  Columns: date,name,value,category
  value is in $B (billions USD)

Requirements:
- pandas
- requests
- pandas-datareader

Notes:
- SEC requires a descriptive User-Agent header. Set SEC_USER_AGENT env var or edit default below.
"""

import os
import json
import time
from pathlib import Path

import requests
import pandas as pd
from pandas_datareader import data as pdr


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "tickers.json"
OUT_PATH = ROOT / "data" / "processed" / "marketcap_monthly.csv"

FMP_BASE = "https://financialmodelingprep.com"


# --- SEC requires a descriptive User-Agent. ---
DEFAULT_SEC_UA = "ai-hyperscalers-marketcap-race (contact: your-email@example.com)"
SEC_HEADERS = {
    "User-Agent": os.getenv("SEC_USER_AGENT", DEFAULT_SEC_UA),
    "Accept-Encoding": "gzip, deflate",
}


def to_monthly_eom(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    """Resample a time series to monthly end-of-month, using last available observation each month."""
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col)
    df = df.set_index(date_col)
    return df.resample("ME").last().dropna().reset_index()


# -------------------------
# FMP: True historical market cap (when available)
# -------------------------
def fetch_fmp_historical_marketcap(symbol: str, api_key: str) -> pd.DataFrame:
    """
    Try to fetch daily historical market cap from FMP.
    If paywalled for the symbol, FMP returns 402.
    """
    url = f"{FMP_BASE}/stable/historical-market-capitalization"
    r = requests.get(url, params={"symbol": symbol, "apikey": api_key}, timeout=60)
    if r.status_code == 402:
        raise PermissionError("FMP 402 Payment Required")
    r.raise_for_status()

    js = r.json()
    if not isinstance(js, list) or not js:
        raise RuntimeError(f"Unexpected FMP response for {symbol}: {str(js)[:200]}")

    df = pd.DataFrame(js)
    if "date" not in df.columns or "marketCap" not in df.columns:
        raise RuntimeError(f"FMP response missing fields for {symbol}: cols={list(df.columns)}")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["marketCap"] = pd.to_numeric(df["marketCap"], errors="coerce")
    df = df.dropna(subset=["date", "marketCap"]).sort_values("date")

    # Convert to monthly EOM and $B
    m = to_monthly_eom(df[["date", "marketCap"]], "date")
    m["value"] = m["marketCap"] / 1e9
    return m[["date", "value"]]


# -------------------------
# Stooq: Price history
# -------------------------
def fetch_stooq_prices(symbol: str) -> pd.DataFrame:
    """
    Fetch daily close from Stooq via pandas-datareader.

    Stooq US symbols commonly use: <ticker>.us in lowercase.
    Example: msft.us, amzn.us
    """
    stooq_symbol = f"{symbol.lower()}.us"
    df = pdr.DataReader(stooq_symbol, "stooq")  # Open/High/Low/Close/Volume
    df = df.sort_index().reset_index().rename(columns={"Date": "date", "Close": "close"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"])
    return df[["date", "close"]]


# -------------------------
# SEC: Ticker -> CIK mapping
# -------------------------
def get_cik_for_ticker(ticker: str) -> str:
    """
    Map ticker -> CIK using SEC's company_tickers.json.

    This file is a dict keyed by integers-as-strings, e.g.:
      {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "APPLE INC"}, ...}

    Returns a zero-padded 10-digit CIK string.
    """
    url = "https://www.sec.gov/files/company_tickers.json"
    r = requests.get(url, headers=SEC_HEADERS, timeout=60)
    r.raise_for_status()
    js = r.json()

    t = ticker.upper()

    # js is dict-of-dicts
    for _, row in js.items():
        if str(row.get("ticker", "")).upper() == t:
            cik_int = int(row["cik_str"])
            return f"{cik_int:010d}"

    raise RuntimeError(f"Could not find CIK for ticker {ticker} via SEC mapping")

# -------------------------
# SEC: Shares outstanding series
# -------------------------
def fetch_sec_shares_timeseries(cik10: str) -> pd.DataFrame:
    """
    Fetch shares outstanding time series from SEC companyfacts.

    We try multiple tags/taxonomies because filers vary:
      - facts.dei.EntityCommonStockSharesOutstanding
      - facts.dei.CommonStockSharesOutstanding
      - facts.us-gaap.CommonStockSharesOutstanding
      - facts.us-gaap.EntityCommonStockSharesOutstanding
    """
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
    r = requests.get(url, headers=SEC_HEADERS, timeout=60)
    r.raise_for_status()
    js = r.json()

    candidates = [
        ("dei", "EntityCommonStockSharesOutstanding"),
        ("dei", "CommonStockSharesOutstanding"),
        ("us-gaap", "CommonStockSharesOutstanding"),
        ("us-gaap", "EntityCommonStockSharesOutstanding"),
    ]

    series = None
    for taxonomy, tag in candidates:
        node = js.get("facts", {}).get(taxonomy, {}).get(tag)
        if node and "units" in node:
            units = node["units"]
            if "shares" in units and units["shares"]:
                series = units["shares"]
                break

    if series is None:
        return pd.DataFrame(columns=["date", "shares"])

    df = pd.DataFrame(series).rename(columns={"end": "date", "val": "shares"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["shares"] = pd.to_numeric(df["shares"], errors="coerce")
    df = df.dropna(subset=["date", "shares"]).sort_values("date")

    # Keep last observation per date
    df = df.groupby("date", as_index=False)["shares"].last()
    return df


def compute_marketcap_from_stooq_and_sec(symbol: str) -> pd.DataFrame:
    """
    Approximate market cap using:
      monthly EOM close price × (shares outstanding from SEC, forward-filled)
    """
    prices = fetch_stooq_prices(symbol)
    prices_m = to_monthly_eom(prices, "date")  # date, close

    cik10 = get_cik_for_ticker(symbol)
    shares_ts = fetch_sec_shares_timeseries(cik10)
    if shares_ts.empty:
        return pd.DataFrame(columns=["date", "value"])

    # Merge shares onto monthly dates and fill forward/back
    merged = prices_m.merge(shares_ts, on="date", how="left").sort_values("date")
    merged["shares"] = merged["shares"].ffill().bfill()

    if merged["shares"].isna().any():
        return pd.DataFrame(columns=["date", "value"])

    merged["value"] = (merged["close"] * merged["shares"]) / 1e9  # $B
    return merged[["date", "value"]]


def main() -> None:
    api_key = os.getenv("FMP_API_KEY", "").strip()

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    tickers = cfg.get("tickers", [])
    if not tickers:
        raise RuntimeError("No tickers found in config/tickers.json")

    rows = []
    skipped = []

    for t in tickers:
        symbol = t["ticker"]
        name = t.get("name", symbol)
        category = t.get("category", "Unknown")

        # 1) Try FMP true market cap
        used = None
        df = None

        if api_key:
            try:
                df = fetch_fmp_historical_marketcap(symbol, api_key)
                used = "FMP-historical-marketcap"
            except PermissionError:
                df = None
            except Exception as e:
                # Any other FMP error -> fallback instead of hard fail
                print(f"{symbol}: FMP error ({type(e).__name__}): {e}")
                df = None

        # 2) Fallback if needed
        if df is None or df.empty:
            df = compute_marketcap_from_stooq_and_sec(symbol)
            used = "Stooq close × SEC shares (approx)"

        # 3) If still empty, skip ticker
        if df is None or df.empty:
            print(f"{symbol}: SKIP (no usable market cap series)")
            skipped.append(symbol)
            continue

        df = df.copy()
        df["name"] = name
        df["category"] = category
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

        rows.append(df[["date", "name", "value", "category"]])
        print(f"{symbol}: OK ({used}) rows={len(df)}")

        time.sleep(0.25)

    if not rows:
        raise RuntimeError(f"All tickers failed. Skipped={skipped}")

    out = pd.concat(rows, ignore_index=True)
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["date", "name", "value"])
    out = out.sort_values(["date", "value"], ascending=[True, False])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_PATH, index=False)

    print(f"\nWrote: {OUT_PATH} (rows={len(out):,})")
    if skipped:
        print(f"Skipped tickers: {', '.join(skipped)}")


if __name__ == "__main__":
    main()
