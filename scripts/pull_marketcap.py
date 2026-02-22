import os
import json
import requests
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "tickers.json"
OUT_PATH = ROOT / "data" / "processed" / "marketcap_monthly.csv"

def fetch(symbol, api_key):
    url = "https://financialmodelingprep.com/stable/historical-market-capitalization"
    r = requests.get(url, params={"symbol": symbol, "apikey": api_key})
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    return df

def main():
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        raise RuntimeError("Set FMP_API_KEY environment variable.")

    with open(CONFIG_PATH) as f:
        cfg = json.load(f)

    rows = []

    for t in cfg["tickers"]:
        df = fetch(t["ticker"], api_key)
        df = df.set_index("date").resample("ME").last().reset_index()
        df["value"] = df["marketCap"] / 1e9
        df["name"] = t["name"]
        df["category"] = t["category"]
        rows.append(df[["date","name","value","category"]])

    out = pd.concat(rows)
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_PATH, index=False)
    print("Wrote:", OUT_PATH)

if __name__ == "__main__":
    main()
