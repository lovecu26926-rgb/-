import requests
import json
import os
import time
import pandas as pd

API_KEY = os.getenv("FMP_API_KEY")
CACHE_FILE = "fundamentals.json"

TREND_CSV = "trend_universe.csv"
SUPERTREND_CSV = "supertrend_universe.csv"


def load_tickers():
    t1 = pd.read_csv(TREND_CSV)["Symbol"].dropna().tolist()
    t2 = pd.read_csv(SUPERTREND_CSV)["Symbol"].dropna().tolist()
    return list(set(t1 + t2))


def fetch_forward(t):

    url = f"https://financialmodelingprep.com/stable/analyst-estimates?symbol={t}&limit=1&apikey={API_KEY}"

    try:
        r = requests.get(url, timeout=10).json()

        if not isinstance(r, list) or len(r) == 0:
            return None, None

        d = r[0]

        return d.get("estimatedEpsAvg"), d.get("estimatedRevenueAvg")

    except:
        return None, None


tickers = load_tickers()

fund = {}

for i, t in enumerate(tickers):

    eps, rev = fetch_forward(t)

    fund[t] = {
        "eps_forward_growth": eps if eps is not None else "N/A",
        "revenue_forward_growth": rev if rev is not None else "N/A",
    }

    print(i, t, fund[t])

    time.sleep(0.2)


with open(CACHE_FILE, "w") as f:
    json.dump(fund, f, indent=2)
