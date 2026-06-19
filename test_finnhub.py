import requests
import os

API_KEY = os.getenv("FINNHUB_API_KEY") or "YOUR_KEY"

tickers = ["AAPL", "NVDA", "MU", "AMD", "TSLA"]

def growth(new, old):
    if new is None or old is None or old == 0:
        return None
    return (new - old) / abs(old) * 100

for t in tickers:
    url = f"https://finnhub.io/api/v1/stock/financials-reported?symbol={t}&token={API_KEY}"
    r = requests.get(url).json()

    try:
        data = r["data"]

        latest = data[0]["report"]["ic"]
        prev = data[1]["report"]["ic"]

        rev = growth(latest.get("revenue"), prev.get("revenue"))
        eps = growth(latest.get("eps"), prev.get("eps"))

        print(f"\n{t}")

        print("매출성장:", f"{rev:.2f}%" if rev is not None else "없음")
        print("EPS성장:", f"{eps:.2f}%" if eps is not None else "없음")

    except Exception as e:
        print(t, "파싱 실패:", e)
