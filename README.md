# AI Hyperscalers — Market Cap Bar Chart Race (D3)

Animated bar chart race of market capitalization for major AI hyperscalers + AI infrastructure companies.

## Setup Instructions

### 1️⃣ Create a new GitHub repository
Go to GitHub → New Repository  
Name it: `ai-hyperscalers-marketcap-race`  
Do NOT initialize with README (we provide one).

### 2️⃣ Upload this folder
Unzip this archive and drag the entire folder contents into the root of your GitHub repo.

### 3️⃣ Add API Key
This project uses Financial Modeling Prep (FMP) for historical market cap data.

Create a free API key at:
https://site.financialmodelingprep.com/

Then in GitHub:
Settings → Secrets and Variables → Actions → New Repository Secret
Name: FMP_API_KEY
Value: YOUR_API_KEY

### 4️⃣ Run locally (optional test)
pip install -r requirements.txt
export FMP_API_KEY=YOUR_KEY   (Mac/Linux)
setx FMP_API_KEY YOUR_KEY     (Windows PowerShell)
python scripts/pull_marketcap.py

Then run:
python -m http.server 8000

Open: http://localhost:8000

### Output
Data file generated:
data/processed/marketcap_monthly.csv

Columns:
date,name,value,category
