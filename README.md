# AI Hyperscalers + AI Infrastructure  
## Market Capitalization Bar Chart Race (D3.js)

▶ **Live Visualization:**  
https://mjmonnot.github.io/ai-hyperscalers-marketcap-race/

---

## Overview

This project renders an animated **D3.js bar chart race** comparing the market capitalization of major AI hyperscalers and AI infrastructure firms over time.

The visualization updates automatically via a GitHub Actions data pipeline and is designed to be:

- Fully reproducible
- Automated
- Lightweight (no backend required)
- Suitable for portfolio or research demonstration

---

## What the Animation Shows

The bar chart race:

- Animates **monthly market capitalization**
- Displays the **top 10 companies** by market cap at each frame
- Updates dynamically through time
- Uses smooth interpolation between months for visual continuity

### Date Coverage

The animation currently displays the **most recent 8 years** of monthly data (or full available history if shorter), ending at the most recent month-end in the dataset.

To change this window:

Edit `windowYears` in `index.html`.

---

## Data Methodology

Historical market capitalization is approximated using:

```
market_cap(t) ≈ monthly_close_price(t) × derived_shares_outstanding
```

Where:

- Monthly close prices are sourced from **Stooq**.
- Current market capitalization and price snapshot are sourced from **Financial Modeling Prep (FMP)**.
- Shares outstanding are derived as:

```
shares ≈ marketCap_now / price_now
```

This assumes constant shares over the time window.

### Why This Approach?

- Avoids paid historical market cap endpoints
- Avoids fragile SEC XBRL parsing
- Produces consistent coverage across companies
- Fully automated via GitHub Actions
- Suitable for visualization and relative comparison

**Note:** This is an approximation and should not be used for financial analysis.

---

## Companies Included

The default universe includes:

- Microsoft
- Amazon
- Alphabet (Google)
- Meta
- Oracle
- IBM
- NVIDIA
- TSMC
- Broadcom
- AMD

Company list is configurable in:

```
config/tickers.json
```

---

## Repository Structure

```
.
├── index.html                         # Main D3 entry point
├── src/
│   └── barChartRace.js                # Animated race logic
├── scripts/
│   └── pull_marketcap.py              # Data pipeline
├── config/
│   └── tickers.json                   # Company universe
├── data/
│   └── processed/
│       └── marketcap_monthly.csv      # Generated dataset
└── .github/workflows/
    └── refresh-data.yml               # Scheduled refresh
```

---

## Automated Data Pipeline

The GitHub Actions workflow:

1. Pulls daily historical prices from Stooq
2. Resamples to monthly end-of-month
3. Pulls current market cap snapshot from FMP
4. Derives constant shares outstanding
5. Writes:
   ```
   data/processed/marketcap_monthly.csv
   ```
6. Commits updated data automatically

You can manually trigger it via:

```
Actions → Refresh market cap data → Run workflow
```

---

## Required GitHub Secrets

Add in:

Settings → Secrets and variables → Actions

Required:

```
FMP_API_KEY
```

Optional (if rate limiting occurs):

```
SEC_USER_AGENT
```

---

## Running Locally

Install dependencies:

```
pip install -r requirements.txt
```

Set environment variables:

Mac/Linux:
```
export FMP_API_KEY="your_key"
```

Windows PowerShell:
```
setx FMP_API_KEY "your_key"
```

Run:

```
python scripts/pull_marketcap.py
python -m http.server 8000
```

Then open:

```
http://localhost:8000
```

---

## Enable GitHub Pages (If Forking)

1. Go to **Settings**
2. Click **Pages**
3. Source: Deploy from branch
4. Branch: `main`
5. Folder: `/ (root)`
6. Save

Your site will be live at:

```
https://<username>.github.io/<repo-name>/
```

---

## Design Notes

- Built using **D3 v7**
- Uses interpolation between monthly frames for smooth transitions
- Optimized for GitHub Pages deployment
- No build system required
- No backend required

---

## Future Enhancements (Planned)

- Play / Pause controls
- Speed adjustment slider
- Category filtering (Hyperscaler vs AI Infra)
- Tooltip with rank and detailed values
- Window length selector (3y / 5y / 10y / Full)

---

## Inspiration

Visualization style inspired by the D3 / Observable Bar Chart Race pattern:
https://observablehq.com/@d3/bar-chart-race

---

## License

MIT License
