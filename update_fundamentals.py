import requests
import os
import time

API_KEY = os.getenv("FINNHUB_API_KEY") or "YOUR_KEY"

tickers = [...]  # 150개

def growth(now, prev):
    if now is None or prev is None or prev == 0:
        return None
    return (now - prev) / abs(prev) * 100


def fetch(ticker):
    url = f"https://finnhub.io/api/v1/stock/financials?symbol={ticker}&statement=ic&freq=annual&token={API_KEY}"
    r = requests.get(url).json()

    try:
        data = r["data"]
        if len(data) < 2:
            return None

        now = data[0]
        prev = data[1]

        rev_now = now.get("revenue")
        rev_prev = prev.get("revenue")

        eps_now = now.get("eps")
        eps_prev = prev.get("eps")

        return {
            "rev_growth": growth(rev_now, rev_prev),
            "eps_growth": growth(eps_now, eps_prev),
        }

    except:
        return None


for i, t in enumerate(tickers):
    res = fetch(t)

    if res:
        print(t,
              "매출:", f"{res['rev_growth']:.1f}%" if res['rev_growth'] else "없음",
              "EPS:", f"{res['eps_growth']:.1f}%" if res['eps_growth'] else "없음")

    time.sleep(1)  # free 60/min 보호
