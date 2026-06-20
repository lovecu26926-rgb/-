import requests
import time
import os

API_KEY = os.getenv("FMP_API_KEY") or "YOUR_KEY"

# 👉 여기에 150개 넣으면 됨
tickers = ["AAPL", "NVDA", "TSLA", "AMD", "MU"]

def growth(now, prev):
    if now is None or prev is None or prev == 0:
        return None
    return (now - prev) / abs(prev) * 100


def fetch_fmp(ticker):
    url = f"https://financialmodelingprep.com/stable/income-statement?symbol={ticker}&limit=2&apikey={API_KEY}"

    try:
        r = requests.get(url, timeout=10).json()

        if not isinstance(r, list) or len(r) < 2:
            print(f"  ⚠️ {ticker} 응답 이상함: {r}")
            return None

        now = r[0]
        prev = r[1]

        rev_now = now.get("revenue")
        rev_prev = prev.get("revenue")

        eps_now = now.get("eps") or now.get("epsdiluted")
        eps_prev = prev.get("eps") or prev.get("epsdiluted")

        rev_growth = growth(rev_now, rev_prev)
        eps_growth = growth(eps_now, eps_prev)

        return rev_growth, eps_growth

    except Exception as e:
        print(f"  ⚠️ {ticker} 에러: {e}")
        return None


print("🚀 FMP Growth Scanner Start\n")

results = []

for i, t in enumerate(tickers, 1):
    data = fetch_fmp(t)

    if data:
        rev, eps = data
        if rev is not None and eps is not None:
            print(f"[{i}] {t} | 매출 {rev:.1f}% | EPS {eps:.1f}%")
            if rev > 10 and eps > 10:
                results.append((t, rev, eps))
    else:
        print(f"[{i}] {t} | 데이터 없음")

    time.sleep(0.5)


print("\n🔥 FINAL PICKS")
for r in results:
    print(r)
