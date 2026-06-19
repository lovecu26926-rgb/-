import requests
import json
import pandas as pd
import time

FMP_API_KEY = "여기에_네_API키"

TREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"
SUPERTREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/supertrend_universe.csv"

# =========================
# 티커 수집
# =========================

all_tickers = set()

for url in [TREND_CSV, SUPERTREND_CSV]:
    try:
        df = pd.read_csv(url)

        for ticker in df.iloc[:,0]:
            ticker = str(ticker).strip().upper()

            if ticker:
                all_tickers.add(ticker)

    except Exception as e:
        print(e)

print(f"총 {len(all_tickers)}개 종목")

# =========================
# FMP 조회
# =========================

fundamentals = {}

for ticker in sorted(all_tickers):

    try:

        url = (
            f"https://financialmodelingprep.com/api/v3/"
            f"ratios-ttm/{ticker}?apikey={FMP_API_KEY}"
        )

        r = requests.get(url, timeout=20)

        data = r.json()

        if not data:
            continue

        fundamentals[ticker] = {
            "eps_growth": 0,
            "rev_growth": 0
        }

        print("OK", ticker)

        time.sleep(0.3)

    except Exception as e:

        print("ERR", ticker, e)

# =========================
# 저장
# =========================

with open("fundamentals.json", "w") as f:

    json.dump(
        fundamentals,
        f,
        indent=2
    )

print("완료")
