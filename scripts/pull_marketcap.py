#!/usr/bin/env python3
"""
Market Cap (Approx) Pipeline — robust + consistent

Method:
- Pull long historical DAILY close prices from Stooq.
- Resample to MONTHLY end-of-month (EOM) closes.
- Pull CURRENT price + CURRENT marketCap from Financial Modeling Prep (FMP) stable profile endpoint.
- Derive constant shares:
    shares ≈ marketCap_now / price_now
- Approximate market cap history:
    marketCap(t) ≈ shares * close(t)

Output:
- data/processed/marketcap_monthly.csv
  Columns: date,name,value,category
  value is market cap in $B (billions USD).

Caveat:
- This assumes constant shares outstanding derived from a single snapshot.
  It’s an approximation, but stable and reproducible for visualization.
"""

import os
import json
import time
from pathlib import Path

import pandas as pd
import requests
from pandas_datareader import data as pdr


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "tickers.json"
OUT_PATH = ROOT / "data" / "processed" / "marketcap_monthly.csv"

FMP_STABLE_BASE = "https://financialmodelingprep.com/stable"


def to_monthly_eom(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    """Resample a daily time series to monthly end-of-month using last observation each month."""
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col).set_index(date_col)
    return df.resample("ME").last().dropna().reset_index()


def fetch_stooq_daily_close(symbol: str) -> pd.DataFrame:
    """
    Fetch daily close prices from Stooq via pandas-datareader.

    Stooq uses lowercase tickers with suffix .us for US stocks, e.g. msft.us
    """
    stooq_symbol = f"{symbol.lower()}.us"
    df = pdr.DataReader(stooq_symbol, "stooq")  # Open/High/Low/Close/Volume
    df = df.sort_index().reset_index().rename(columns={"Date": "date", "Close": "close"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"])
    return df[["date", "close"]]


def fetch_fmp_price_and_marketcap(symbol: str, api_key: str) -> tuple[float, float]:
    """
    Fetch CURRENT price and CURRENT marketCap from FMP stable profile endpoint.

    Returns: (price_now, marketcap_now)
    """
    url = f"{FMP_STABLE_BASE}/profile"
    headers = {
        "User-Agent": "ai-hyperscalers-marketcap-race (github actions)",
        "Accept": "application/json",
    }
    r = requests.get(url, params={"symbol": symbol, "apikey": api_key}, headers=headers, timeout=60)
    r.raise_for_status()

    js = r.json()
    if not isinstance(js, list) or not js:
        raise RuntimeError(f"Empty profile response for {symbol}: {str(js)[:200]}")

    obj = js[0]
    price = obj.get("price")
    mcap = obj.get("marketCap")

    if price is None or mcap is None:
        raise RuntimeError(
            f"Missing price/marketCap for {symbol}. keys={list(obj.keys())[:25]}"
        )

    price = float(price)
    mcap = float(mcap)

    if price <= 0 or mcap <= 0:
        raise RuntimeError(f"Non-positive price/marketCap for {symbol}: price={price}, marketCap={mcap}")

    return price, mcap


def main() -> None:
    api_key = os.getenv("FMP_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("FMP_API_KEY is not set. Add it as a GitHub Actions secret and/or env var.")

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

        try:
            # 1) long price history (daily)
            prices_daily = fetch_stooq_daily_close(symbol)

            # 2) monthly EOM closes
            prices_m = to_monthly_eom(prices_daily, "date")  # date, close

            # 3) current price + market cap snapshot
            price_now, mcap_now = fetch_fmp_price_and_marketcap(symbol, api_key)

            # 4) derive constant shares
            shares = mcap_now / price_now

            # 5) compute approximate market cap history (in $B)
            prices_m["value"] = (prices_m["close"] * shares) / 1e9
            prices_m["name"] = name
            prices_m["category"] = category
            prices_m["date"] = prices_m["date"].dt.strftime("%Y-%m-%d")

            rows.append(prices_m[["date", "name", "value", "category"]])
            print(f"{symbol}: OK (Stooq close × derived shares) rows={len(prices_m)}")

        except Exception as e:
            print(f"{symbol}: SKIP ({type(e).__name__}): {e}")
            skipped.append(symbol)

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
