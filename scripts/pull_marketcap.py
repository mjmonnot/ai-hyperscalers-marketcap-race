#!/usr/bin/env python3
"""
VERSION: fmp-only-price-eod-v1

Creates:
data/processed/marketcap_monthly.csv

Method:
- Pull historical end-of-day prices from FMP stable historical-price-eod/light.
- Pull current price + current marketCap from FMP stable profile.
- Derive shares = marketCap_now / price_now.
- Approximate historical market cap = monthly close * derived shares.
"""

import os
import json
import time
from pathlib import Path

import pandas as pd
import requests

print("RUNNING pull_marketcap.py VERSION: fmp-only-price-eod-v1")

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "tickers.json"
OUT_PATH = ROOT / "data" / "processed" / "marketcap_monthly.csv"

FMP_STABLE_BASE = "https://financialmodelingprep.com/stable"


def to_monthly_eom(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col).set_index(date_col)
    return df.resample("ME").last().dropna().reset_index()


def fetch_fmp_historical_close(symbol: str, api_key: str) -> pd.DataFrame:
    url = f"{FMP_STABLE_BASE}/historical-price-eod/light"

    headers = {
        "User-Agent": "Mozilla/5.0 ai-hyperscalers-marketcap-race",
        "Accept": "application/json",
    }

    r = requests.get(
        url,
        params={"symbol": symbol, "apikey": api_key},
        headers=headers,
        timeout=60,
    )
    r.raise_for_status()

    js = r.json()

    if not isinstance(js, list) or not js:
        raise RuntimeError(f"Empty FMP historical price response for {symbol}: {str(js)[:300]}")

    df = pd.DataFrame(js)

    if "date" not in df.columns:
        raise RuntimeError(f"FMP historical response missing date for {symbol}: cols={list(df.columns)}")

    # FMP light endpoint may return price, close, or adjClose depending on endpoint/plan.
    price_col = None
    for candidate in ["price", "close", "adjClose", "adj_close"]:
        if candidate in df.columns:
            price_col = candidate
            break

    if price_col is None:
        raise RuntimeError(f"FMP historical response missing price/close for {symbol}: cols={list(df.columns)}")

    df = df.rename(columns={price_col: "close"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"])

    if df.empty:
        raise RuntimeError(f"No valid FMP historical rows for {symbol}")

    return df[["date", "close"]]


def fetch_fmp_price_and_marketcap(symbol: str, api_key: str) -> tuple[float, float]:
    url = f"{FMP_STABLE_BASE}/profile"

    headers = {
        "User-Agent": "Mozilla/5.0 ai-hyperscalers-marketcap-race",
        "Accept": "application/json",
    }

    r = requests.get(
        url,
        params={"symbol": symbol, "apikey": api_key},
        headers=headers,
        timeout=60,
    )
    r.raise_for_status()

    js = r.json()

    if not isinstance(js, list) or not js:
        raise RuntimeError(f"Empty FMP profile response for {symbol}: {str(js)[:300]}")

    obj = js[0]
    price = obj.get("price")
    market_cap = obj.get("marketCap")

    if price is None or market_cap is None:
        raise RuntimeError(f"Missing price/marketCap for {symbol}: keys={list(obj.keys())[:30]}")

    price = float(price)
    market_cap = float(market_cap)

    if price <= 0 or market_cap <= 0:
        raise RuntimeError(f"Invalid price/marketCap for {symbol}: price={price}, marketCap={market_cap}")

    return price, market_cap


def main() -> None:
    api_key = os.getenv("FMP_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("FMP_API_KEY is not set.")

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    rows = []
    skipped = []

    for item in cfg.get("tickers", []):
        symbol = item["ticker"]
        name = item.get("name", symbol)
        category = item.get("category", "Unknown")

        try:
            prices_daily = fetch_fmp_historical_close(symbol, api_key)
            prices_m = to_monthly_eom(prices_daily, "date")

            price_now, market_cap_now = fetch_fmp_price_and_marketcap(symbol, api_key)
            derived_shares = market_cap_now / price_now

            prices_m["value"] = (prices_m["close"] * derived_shares) / 1e9
            prices_m["name"] = name
            prices_m["category"] = category
            prices_m["date"] = prices_m["date"].dt.strftime("%Y-%m-%d")

            rows.append(prices_m[["date", "name", "value", "category"]])
            print(f"{symbol}: OK rows={len(prices_m)}")

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

    print(f"Wrote: {OUT_PATH} rows={len(out):,}")

    if skipped:
        print(f"Skipped tickers: {', '.join(skipped)}")


if __name__ == "__main__":
    main()
