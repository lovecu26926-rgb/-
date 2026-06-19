import requests
import os

API_KEY = os.getenv("FINNHUB_API_KEY") or "YOUR_KEY"

tickers = ["AAPL", "NVDA", "MU", "AMD", "TSLA"]

def growth(new, old):
    if new is None or old is None or old == 0:
        return None
    return (new - old) / abs(old) * 100


def find_value(report, key):
    # 여러 구조 대응
    paths = [
        ["ic", key],
        ["incomeStatement", key],
        [key]
    ]

    for path in paths:
        cur = report
        try:
            for p in path:
                cur = cur.get(p, {})
            if isinstance(cur, (int, float)):
                return cur
        except:
            pass

    return None


for t in tickers:
    url = f"https://finnhub.io/api/v1/stock/financials-reported?symbol={t}&token={API_KEY}"
    r = requests.get(url).json()

    try:
        data = r["data"]

        latest = data[0]["report"]
        prev = data[1]["report"]

        rev_now = find_value(latest, "revenue")
        rev_old = find_value(prev, "revenue")

        eps_now = find_value(latest, "eps")
        eps_old = find_value(prev, "eps")

        rev_growth = growth(rev_now, rev_old)
        eps_growth = growth(eps_now, eps_old)

        print(f"\n{t}")

        print("매출성장:", f"{rev_growth:.2f}%" if rev_growth is not None else "없음")
        print("EPS성장:", f"{eps_growth:.2f}%" if eps_growth is not None else "없음")

    except Exception as e:
        print(t, "데이터 구조 실패:", e)
