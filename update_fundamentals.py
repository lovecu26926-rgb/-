import requests
import os
import time

API_KEY = os.getenv("FMP_API_KEY") or "YOUR_KEY"

tickers = [...]  # 150개

def growth(now, prev):
    if now is None or prev is None or prev == 0:
        return None
    return (now - prev) / abs(prev) * 100


def fetch_fmp(ticker):
    url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}?limit=2&apikey={API_KEY}"
    r = requests.get(url).json()

    if not isinstance(r, list) or len(r) < 2:
        return None

    now = r[0]
    prev = r[1]

    rev_now = now.get("revenue")
    rev_prev = prev.get("revenue")

    eps_now = now.get("eps")
    eps_prev = prev.get("eps")

    return {
        "rev_growth": growth(rev_now, rev_prev),
        "eps_growth": growth(eps_now, eps_prev),
    }


for i, t in enumerate(tickers, 1):
    res = fetch_fmp(t)

    if res:
        print(f"[{i}] {t} | 매출 {res['rev_growth']:.1f}% | EPS {res['eps_growth']:.1f}%")

    time.sleep(0.3)  # 250 calls/day 안전
