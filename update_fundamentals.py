import requests
import time
import os
import json
import pandas as pd

API_KEY = os.getenv("FMP_API_KEY") or "YOUR_KEY"
CACHE_FILE = "fundamentals.json"

TREND_CSV = "trend_universe.csv"
SUPERTREND_CSV = "supertrend_universe.csv"


def load_tickers_from_csv():
    """scanner.py와 동일한 유니버스(TREND_CSV + SUPERTREND_CSV)에서 티커를 자동으로 가져옴"""
    try:
        trend = pd.read_csv(TREND_CSV)["Symbol"].dropna().tolist()
        supert = pd.read_csv(SUPERTREND_CSV)["Symbol"].dropna().tolist()
        tickers = sorted(set(trend + supert))
        print(f"📂 CSV에서 {len(tickers)}개 종목 로드 (TREND+SUPERTREND 중복 제거)")
        return tickers
    except Exception as e:
        print(f"❌ CSV 로드 실패: {e}")
        # CSV가 없거나 깨졌을 때를 대비한 최소 안전망
        return ["AAPL", "NVDA", "TSLA", "AMD", "MU"]


tickers = load_tickers_from_csv()


def growth(now, prev):
    if now is None or prev is None or prev == 0:
        return None
    return (now - prev) / abs(prev) * 100


DEBUG = False  # MU "Special Endpoint" 원인 확인 완료. 필요시 다시 True로

def fetch_income(ticker):
    """매출/EPS 성장률 (1콜)"""
    url = f"https://financialmodelingprep.com/stable/income-statement?symbol={ticker}&limit=2&apikey={API_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        if DEBUG:
            print(f"  🔍 {ticker} income status={resp.status_code}")
            print(f"  🔍 {ticker} income raw={resp.text[:300]}")
        r = resp.json()
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
        resp = requests.get(url, timeout=10)
        if DEBUG:
            print(f"  🔍 {ticker} roe status={resp.status_code}")
            print(f"  🔍 {ticker} roe raw={resp.text[:300]}")
        r = resp.json()
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

# 🔥 무료 플랜 일일 250콜 한도 안전장치
# 1티커당 2콜(income+roe)이므로 125종목 초과 시 자동으로 잘라냄
MAX_DAILY_CALLS = 250
max_tickers = MAX_DAILY_CALLS // 2

if len(tickers) > max_tickers:
    print(f"⚠️ 종목수({len(tickers)})가 일일 한도 기준 최대치({max_tickers})를 초과해 {max_tickers}개로 제한합니다")
    tickers = tickers[:max_tickers]

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
