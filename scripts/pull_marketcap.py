#!/usr/bin/env python3
import os
import json
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "tickers.json"
OUT_PATH = ROOT / "data" / "processed" / "marketcap_monthly.csv"

FMP_STABLE_BASE = "https://financialmodelingprep.com/stable"


def to_monthly_eom(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col).set_index(date_col)
    return df.resample("ME").last().dropna().reset_index()


def fetch_stooq_daily_close(symbol: str) -> pd.DataFrame:
    """
    Pull daily close prices directly from Stooq CSV endpoint.

    Example:
    https://stooq.com/q/d/l/?s=msft.us&i=d
    """
    stooq_symbol = f"{symbol.lower()}.us"
    url = "https://stooq.com/q/d/l/"
    params = {"s": stooq_symbol, "i": "d"}

    headers = {
        "User-Agent": "ai-hyperscalers-marketcap-race GitHub Actions",
        "Accept": "text/csv,text/plain,*/*",
    }

    r = requests.get(url, params=params, headers=headers, timeout=60)
    r.raise_for_status()

    text = r.text.strip()

    if not text or "No data" in text or "<html" in text.lower():
        raise RuntimeError(f"Stooq returned no usable CSV for {symbol}: {text[:200]}")

    df = pd.read_csv(StringIO(text))

    if "Date" not in df.columns or "Close" not in df.columns:
        raise RuntimeError(f"Unexpected Stooq CSV columns for {symbol}: {list(df.columns)}")

    df = df.rename(columns={"Date": "date", "Close": "close"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"])

    if df.empty:
        raise RuntimeError(f"No valid Stooq price rows for {symbol}")

    return df[["date", "close"]]


def fetch_fmp_price_and_marketcap(symbol: str, api_key: str) -> tuple[float, float]:
    """
    Pull current price and marketCap from FMP stable profile endpoint.
    Derive shares as marketCap / price.
    """
    url = f"{FMP_STABLE_BASE}/profile"
    headers = {
        "User-Agent": "ai-hyperscalers-marketcap-race GitHub Actions",
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
        raise RuntimeError(f"Empty FMP profile response for {symbol}: {str(js)[:200]}")

    obj = js[0]
    price = obj.get("price")
    market_cap = obj.get("marketCap")

    if price is None or market_cap is None:
        raise RuntimeError(f"Missing price/marketCap for {symbol}: keys={list(obj.keys())[:25]}")

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
            prices_daily = fetch_stooq_daily_close(symbol)
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
