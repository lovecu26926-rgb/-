import requests
import time
import os
import sys
import json
import pandas as pd

API_KEY = os.getenv("FMP_API_KEY") or "YOUR_KEY"
CACHE_FILE = "fundamentals.json"

TREND_CSV = "trend_universe.csv"
SUPERTREND_CSV = "supertrend_universe.csv"

DEBUG = False  # 응답 원문 디버깅 필요할 때만 True로


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
        return []  # 더미 종목으로 대체하지 않음 (안전망 제거)


tickers = load_tickers_from_csv()

# 🔥 핵심 수정 1: 종목이 0개면 여기서 바로 종료.
# 이 가드 없으면 아래 json.dump가 그대로 실행돼서 fundamentals.json이
# 빈 파일로 덮어써지고, CSV 로드만 잠깐 실패해도 어제까지 쌓인 캐시 전체가 날아감.
if not tickers:
    print("⚠️ 종목 리스트가 비어있음 - fundamentals.json을 건드리지 않고 종료합니다 (기존 캐시 유지)")
    sys.exit(0)


def growth(now, prev):
    try:
        if now is None or prev is None or prev == 0:
            return None
        return (now - prev) / abs(prev) * 100
    except Exception:
        return None


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
            print(f"⚠️ {ticker} income 데이터 부족: {r}")
            return None, None

        # 날짜 기준 내림차순 정렬 - API가 항상 최신순으로 준다는 보장이 없어서 안전장치
        r = sorted(r, key=lambda x: x.get("date", ""), reverse=True)

        now = r[0]
        prev = r[1]

        rev_now = now.get("revenue")
        rev_prev = prev.get("revenue")

        eps_now = now.get("eps") or now.get("epsdiluted") or now.get("netIncomePerShare")
        eps_prev = prev.get("eps") or prev.get("epsdiluted") or prev.get("netIncomePerShare")

        rev_growth = growth(rev_now, rev_prev)
        eps_growth = growth(eps_now, eps_prev)

        return rev_growth, eps_growth

    except Exception as e:
        print(f"⚠️ {ticker} income 에러: {e}")
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
            print(f"⚠️ {ticker} key-metrics 부족: {r}")
            return None

        roe = r[0].get("returnOnEquity")
        if roe is None:
            return None

        # 🔥 핵심 수정 2: FMP는 보통 비율(0.15)로 줌 -> % 로 변환.
        # abs()를 써야 적자 ROE(음수)도 똑같이 "비율"로 판단됨.
        # (이전 버전의 roe < 1 조건은 음수면 크기 상관없이 무조건 *100 처리돼서,
        #  이미 %로 온 큰 음수값까지 잘못 곱해버릴 수 있었음)
        if abs(roe) < 10:
            return roe * 100
        print(f"  ℹ️ {ticker} ROE={roe} (절댓값 10 이상) - 이미 %로 추정돼 변환 생략")
        return roe

    except Exception as e:
        print(f"⚠️ {ticker} roe 에러: {e}")
        return None


print("🚀 FMP Growth + ROE Cache Builder Start\n")
print(f"📊 종목 수: {len(tickers)}개 (예상 콜 수: {len(tickers) * 2}회)\n")

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

    fundamentals[t] = {
        "revenue_growth": round(rev, 1) if rev is not None else "N/A",
        "eps_growth": round(eps, 1) if eps is not None else "N/A",
        "roe": round(roe, 1) if roe is not None else "N/A",
    }

    print(f"[{i}/{len(tickers)}] {t} | "
          f"매출 {fundamentals[t]['revenue_growth']} | "
          f"EPS {fundamentals[t]['eps_growth']} | "
          f"ROE {fundamentals[t]['roe']}")

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
