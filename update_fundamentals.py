import requests
import time
import os
import json

API_KEY = os.getenv("FMP_API_KEY") or "YOUR_KEY"
CACHE_FILE = "fundamentals.json"

# 👉 여기에 티커 채우기 (1티커=1콜이라 무료 250콜 한도 안에서 운용)
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
            return None, None

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
        return None, None


print("🚀 FMP Growth Cache Builder Start\n")

fundamentals = {}

for i, t in enumerate(tickers, 1):
    rev, eps = fetch_fmp(t)

    # scanner.py가 fund.get("revenue_growth", "N/A") 식으로 조회하니까
    # 키가 없을 때뿐 아니라 값이 없을 때도 "N/A"로 통일해둠
    fundamentals[t] = {
        "revenue_growth": round(rev, 1) if rev is not None else "N/A",
        "eps_growth": round(eps, 1) if eps is not None else "N/A",
    }

    if rev is not None and eps is not None:
        print(f"[{i}] {t} | 매출 {rev:.1f}% | EPS {eps:.1f}%")
    else:
        print(f"[{i}] {t} | 데이터 없음")

    time.sleep(0.5)

with open(CACHE_FILE, "w") as f:
    json.dump(fundamentals, f, ensure_ascii=False, indent=2)

print(f"\n💾 {CACHE_FILE} 저장 완료 ({len(fundamentals)}개 종목)")

print("\n🔥 매출/EPS 둘 다 10% 이상")
for t, d in fundamentals.items():
    rev = d["revenue_growth"]
    eps = d["eps_growth"]
    if rev != "N/A" and eps != "N/A" and rev > 10 and eps > 10:
        print(f"  {t} | 매출 {rev}% | EPS {eps}%")
