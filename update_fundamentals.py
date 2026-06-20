import requests
import time
import os
import json

API_KEY = os.getenv("FMP_API_KEY") or "YOUR_KEY"
CACHE_FILE = "fundamentals.json"

# 👉 여기에 티커 채우기 (1티커=2콜이라 무료 250콜 한도면 약 120종목까지 가능)
tickers = ["AAPL", "NVDA", "TSLA", "AMD", "MU"]


def growth(now, prev):
    if now is None or prev is None or prev == 0:
        return None
    return (now - prev) / abs(prev) * 100


def fetch_income(ticker):
    """매출/EPS 성장률 (1콜)"""
    url = f"https://financialmodelingprep.com/stable/income-statement?symbol={ticker}&limit=2&apikey={API_KEY}"
    try:
        r = requests.get(url, timeout=10).json()
        if not isinstance(r, list) or len(r) < 2:
            print(f"  ⚠️ {ticker} income 응답 이상함: {r}")
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
        print(f"  ⚠️ {ticker} income 에러: {e}")
        return None, None


def fetch_roe(ticker):
    """ROE (1콜) - key-metrics 엔드포인트에서 returnOnEquity 가져옴"""
    url = f"https://financialmodelingprep.com/stable/key-metrics?symbol={ticker}&limit=1&apikey={API_KEY}"
    try:
        r = requests.get(url, timeout=10).json()
        if not isinstance(r, list) or len(r) < 1:
            print(f"  ⚠️ {ticker} key-metrics 응답 이상함: {r}")
            return None

        roe = r[0].get("returnOnEquity")
        if roe is None:
            return None

        # FMP는 보통 비율(0.15)로 줌 -> % 로 변환
        return roe * 100 if abs(roe) < 5 else roe
    except Exception as e:
        print(f"  ⚠️ {ticker} roe 에러: {e}")
        return None


print("🚀 FMP Growth + ROE Cache Builder Start\n")
print(f"📊 종목 수: {len(tickers)}개 (예상 콜 수: {len(tickers) * 2}회)\n")

fundamentals = {}

for i, t in enumerate(tickers, 1):
    rev, eps = fetch_income(t)
    time.sleep(0.3)
    roe = fetch_roe(t)
    time.sleep(0.3)

    # scanner.py가 fund.get("revenue_growth", "N/A") 식으로 조회하니까
    # 키가 없을 때뿐 아니라 값이 없을 때도 "N/A"로 통일해둠
    fundamentals[t] = {
        "revenue_growth": round(rev, 1) if rev is not None else "N/A",
        "eps_growth": round(eps, 1) if eps is not None else "N/A",
        "roe": round(roe, 1) if roe is not None else "N/A",
    }

    rev_s = f"{rev:.1f}%" if rev is not None else "N/A"
    eps_s = f"{eps:.1f}%" if eps is not None else "N/A"
    roe_s = f"{roe:.1f}%" if roe is not None else "N/A"
    print(f"[{i}/{len(tickers)}] {t} | 매출 {rev_s} | EPS {eps_s} | ROE {roe_s}")

with open(CACHE_FILE, "w") as f:
    json.dump(fundamentals, f, ensure_ascii=False, indent=2)

print(f"\n💾 {CACHE_FILE} 저장 완료 ({len(fundamentals)}개 종목)")

print("\n🔥 매출/EPS 둘 다 10% 이상 + ROE 10% 이상")
for t, d in fundamentals.items():
    rev = d["revenue_growth"]
    eps = d["eps_growth"]
    roe = d["roe"]
    if rev != "N/A" and eps != "N/A" and roe != "N/A" and rev > 10 and eps > 10 and roe > 10:
        print(f"  {t} | 매출 {rev}% | EPS {eps}% | ROE {roe}%")
