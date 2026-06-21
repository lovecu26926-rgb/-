import requests
import json
import os
import time
import pandas as pd

# =========================
# 설정
# =========================
API_KEY = os.getenv("FMP_API_KEY")
CACHE_FILE = "fundamentals.json"

TREND_CSV = "trend_universe.csv"
SUPERTREND_CSV = "supertrend_universe.csv"

# =========================
# 티커 로드
# =========================
def load_tickers():
    t1 = pd.read_csv(TREND_CSV)["Symbol"].dropna().tolist()
    t2 = pd.read_csv(SUPERTREND_CSV)["Symbol"].dropna().tolist()
    return list(set(t1 + t2))

# =========================
# 과거 (income statement)
# =========================
def fetch_past(ticker):

    url = f"https://financialmodelingprep.com/stable/income-statement?symbol={ticker}&limit=2&apikey={API_KEY}"

    try:
        r = requests.get(url, timeout=10).json()

        if not isinstance(r, list) or len(r) < 2:
            return None

        r = sorted(r, key=lambda x: x.get("date", ""), reverse=True)

        now = r[0]
        prev = r[1]

        rev_now = now.get("revenue")
        rev_prev = prev.get("revenue")

        eps_now = now.get("eps") or now.get("epsdiluted") or now.get("netIncomePerShare")
        eps_prev = prev.get("eps") or prev.get("epsdiluted") or prev.get("netIncomePerShare")

        def growth(a, b):
            if a is None or b is None or b == 0:
                return None
            return (a - b) / abs(b) * 100

        return {
            "eps_yoy": round(growth(eps_now, eps_prev), 2) if growth(eps_now, eps_prev) is not None else None,
            "rev_yoy": round(growth(rev_now, rev_prev), 2) if growth(rev_now, rev_prev) is not None else None
        }

    except:
        return None

# =========================
# 미래 (analyst estimates)
# =========================
def fetch_forward(ticker):

    url = f"https://financialmodelingprep.com/stable/analyst-estimates?symbol={ticker}&limit=1&apikey={API_KEY}"

    try:
        r = requests.get(url, timeout=10).json()

        if not isinstance(r, list) or len(r) == 0:
            return None

        d = r[0]

        return {
            "eps_fwd": d.get("estimatedEpsAvg"),
            "rev_fwd": d.get("estimatedRevenueAvg")
        }

    except:
        return None

# =========================
# 메인
# =========================
def build():

    tickers = load_tickers()

    print(f"[FUNDAMENTAL] {len(tickers)} tickers start")

    data = {}

    for i, t in enumerate(tickers, 1):

        past = fetch_past(t)
        time.sleep(0.2)

        forward = fetch_forward(t)
        time.sleep(0.2)

        if past is None:
            past = {}

        if forward is None:
            forward = {}

        data[t] = {
            "eps_yoy": past.get("eps_yoy"),
            "rev_yoy": past.get("rev_yoy"),
            "eps_fwd": forward.get("eps_fwd"),
            "rev_fwd": forward.get("rev_fwd")
        }

        print(i, t, data[t])

    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nDONE -> {CACHE_FILE}")

# =========================
# RUN
# =========================
if __name__ == "__main__":
    build()
