import requests
import os

API_KEY = os.getenv("FINNHUB_API_KEY") or "YOUR_KEY"

tickers = ["AAPL", "NVDA", "MU", "AMD", "TSLA"]

def growth(new, old):
    if new is None or old is None or old == 0:
        return None
    return (new - old) / abs(old) * 100


for t in tickers:
    url = f"https://finnhub.io/api/v1/stock/financials?symbol={t}&statement=ic&freq=annual&token={API_KEY}"
    r = requests.get(url).json()

    try:
        data = r["data"]

        latest = data[0]
        prev = data[1]

        rev_now = latest.get("revenue")
        rev_old = prev.get("revenue")

        eps_now = latest.get("eps")
        eps_old = prev.get("eps")

        print(f"\n{t}")
        print("매출성장:", f"{growth(rev_now, rev_old):.2f}%" if rev_now and rev_old else "없음")
        print("EPS성장:", f"{growth(eps_now, eps_old):.2f}%" if eps_now and eps_old else "없음")

    except Exception as e:
        print(t, "실패:", e)
