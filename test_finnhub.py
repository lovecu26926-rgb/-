import requests
import os

API_KEY = os.getenv("FINNHUB_API_KEY") or "YOUR_KEY"
tickers = ["AAPL", "NVDA", "MU", "AMD", "TSLA"]

def growth(new, old):
    if new is None or old is None or old == 0:
        return None
    return (new - old) / abs(old) * 100

for t in tickers:
    url = f"https://finnhub.io/api/v1/stock/financials-reported"
    params = {
        "symbol": t,
        "freq": "annual",
        "token": API_KEY
    }
    try:
        r = requests.get(url, params=params, timeout=5).json()
        data = r.get("data", [])
        
        if len(data) < 2:
            print(f"{t} 데이터 부족")
            continue
        
        # ic = income statement
        latest = data[0].get("report", {}).get("ic", [])
        prev = data[1].get("report", {}).get("ic", [])
        
        # 리스트에서 항목 찾기
        def find(items, concept):
            for item in items:
                if item.get("concept") == concept:
                    return item.get("value")
            return None
        
        rev_now = find(latest, "Revenues")
        rev_old = find(prev, "Revenues")
        eps_now = find(latest, "EarningsPerShareBasic")
        eps_old = find(prev, "EarningsPerShareBasic")
        
        print(f"\n{t}")
        print("매출성장:", f"{growth(rev_now, rev_old):.2f}%" if rev_now and rev_old else "없음")
        print("EPS성장:", f"{growth(eps_now, eps_old):.2f}%" if eps_now and eps_old else "없음")
        
    except Exception as e:
        print(t, "실패:", e)
