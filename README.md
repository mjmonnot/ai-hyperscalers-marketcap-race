# AI Hyperscalers — Market Cap Bar Chart Race (D3)

## ▶ View the Live Chart

https://mjmonnot.github.io/ai-hyperscalers-marketcap-race/

---

## Overview

This repository renders a D3 bar chart visualization comparing market capitalization over time for major AI hyperscalers and AI infrastructure firms.

The visualization is powered by:

- `index.html` (entry point)
- `src/barChartRace.js` (D3 visualization logic)
- `data/processed/marketcap_monthly.csv` (generated dataset)
- GitHub Actions workflow for automated refresh


## Repository Structure

.
├── index.html  
├── src/  
│   └── barChartRace.js  
├── scripts/  
│   └── pull_marketcap.py  
├── config/  
│   └── tickers.json  
├── data/  
│   └── processed/  
│       └── marketcap_monthly.csv  
└── .github/workflows/  
    └── refresh-data.yml  

---

## Data Pipeline (Automatic Refresh)

The GitHub Actions workflow:

- Pulls historical market cap data (or computes approximation if necessary)
- Resamples to monthly end-of-month
- Writes:
  data/processed/marketcap_monthly.csv
- Commits updates automatically

---

## Required Repository Secrets

Go to:

Settings → Secrets and variables → Actions → New repository secret

Add:

Name: FMP_API_KEY  
Value: your_api_key_here  

Optional (recommended):

Name: SEC_USER_AGENT  
Value: Your Name (your@email.com) ai-hyperscalers-marketcap-race  

---

## Manually Trigger the First Data Pull

1. Click **Actions**
2. Select **Refresh market cap data**
3. Click **Run workflow**
4. Choose branch `main`

After it runs successfully, the CSV file will appear in:

data/processed/

---

## Run Locally (Optional)

Install dependencies:

pip install -r requirements.txt

Set environment variables:

Mac/Linux:
export FMP_API_KEY="your_key"
export SEC_USER_AGENT="Your Name (your@email.com)"

Windows PowerShell:
setx FMP_API_KEY "your_key"
setx SEC_USER_AGENT "Your Name (your@email.com)"

Pull data:

python scripts/pull_marketcap.py

Run local server:

python -m http.server 8000

Open:

http://localhost:8000

---

## Customizing the Company Universe

Edit:

config/tickers.json

Then rerun the workflow or local script.

---

## Methodological Note

When provider historical market capitalization is available, it is used directly.

When unavailable, market capitalization is approximated using:

Monthly closing price × SEC-reported shares outstanding (forward-filled).

This ensures the pipeline remains fully automated and reproducible.

---

## Credits

Visualization pattern inspired by the D3 / Observable Bar Chart Race:
https://observablehq.com/@d3/bar-chart-race
