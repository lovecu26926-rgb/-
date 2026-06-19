import requests
import json
import pandas as pd
import time

FMP_API_KEY = "Us5oERwTgTB1pQFmxv5RW0e7uMVG8mjd"

TREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"
SUPERTREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/supertrend_universe.csv"

def get_tickers():
    all_tickers = set()

    for url in [TREND_CSV, SUPERTREND_CSV]:
        df = pd.read_csv(url)
        for t in df.iloc[:, 0]:
            t = str(t).strip().upper()
            if t:
                all_tickers.add(t)

    return sorted(list(all_tickers))

def fetch_fmp(ticker):
    url = f"https://financialmodelingprep.com/api/v3/key-metrics-ttm/{ticker}?apikey={FMP_API_KEY}"
    r = requests.get(url, timeout=15)
    data = r.json()

    if not data:
        return None

    d = data[0]

    return {
        "eps": d.get("netIncomePerShareTTM", 0),
        "rev": d.get("revenuePerShareTTM", 0)
    }

fundamentals = {}

tickers = get_tickers()

print(f"총 {len(tickers)}개")

for t in tickers:
    try:
        data = fetch_fmp(t)

        if data:
            fundamentals[t] = data
            print("OK", t)

        time.sleep(0.2)

    except Exception as e:
        print("ERR", t, e)

with open("fundamentals.json", "w") as f:
    json.dump(fundamentals, f, indent=2)

print("완료")
