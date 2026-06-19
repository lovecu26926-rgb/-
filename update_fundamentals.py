import requests
import json
import pandas as pd
import time
import os

FMP_API_KEY = os.environ.get("FMP_API_KEY")

if not FMP_API_KEY:
    FMP_API_KEY = "YOUR_API_KEY_HERE"

TREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"
SUPERTREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/supertrend_universe.csv"

def get_tickers():
    all_tickers = set()
    for url in [TREND_CSV, SUPERTREND_CSV]:
        df = pd.read_csv(url)
        for t in df.iloc[:, 0]:
            t = str(t).strip().upper()
            if t:
                all_tickers.add(t)
    return sorted(list(all_tickers))

def fetch_fmp(ticker):
    try:
        # 1️⃣ 프로필 (stable)
        profile_url = f"https://financialmodelingprep.com/stable/profile?symbol={ticker}&apikey={FMP_API_KEY}"
        profile_resp = requests.get(profile_url, timeout=10)
        if profile_resp.status_code != 200:
            return None
        profile = profile_resp.json()
        if not profile:
            return None
        p = profile[0]

        # 2️⃣ 키 메트릭스 TTM (stable)
        metrics_url = f"https://financialmodelingprep.com/stable/key-metrics-ttm?symbol={ticker}&apikey={FMP_API_KEY}"
        metrics_resp = requests.get(metrics_url, timeout=10)
        metrics = metrics_resp.json() if metrics_resp.status_code == 200 else []
        m = metrics[0] if metrics else {}

        # 3️⃣ 손익계산서 TTM (stable)
        eps_growth = 0
        income_url = f"https://financialmodelingprep.com/stable/income-statement-ttm?symbol={ticker}&apikey={FMP_API_KEY}"
        income_resp = requests.get(income_url, timeout=10)
        if income_resp.status_code == 200:
            income_data = income_resp.json()
            if income_data and len(income_data) >= 2:
                curr = income_data[0]
                prev = income_data[1]
                eps_prev = prev.get('eps', 0)
                eps_curr = curr.get('eps', 0)
                if eps_prev > 0:
                    eps_growth = ((eps_curr - eps_prev) / eps_prev) * 100

        # profitMargin이 None이면 netProfitMargin 사용
        margin = p.get('profitMargin', p.get('netProfitMargin', 0))
        if margin is None:
            margin = 0

        return {
            'eps_growth': round(eps_growth, 2),
            'rev_growth': round(m.get('revenueGrowthTTM', 0) * 100, 2),
            'roe': round(p.get('roe', 0) * 100, 2),
            'margin': round(margin * 100, 2),
        }
    except Exception as e:
        print(f"⚠️ {ticker} 오류: {e}")
        return None

# 실행
tickers = get_tickers()
print(f"📊 총 {len(tickers)}개 종목")

fundamentals = {}

for i, t in enumerate(tickers, 1):
    print(f"[{i}/{len(tickers)}] {t} 조회 중...")
    data = fetch_fmp(t)
    if data:
        fundamentals[t] = data
        eps_display = "흑자전환" if data['eps_growth'] == 999 else f"{data['eps_growth']:.1f}%"
        print(f"  ✅ EPS {eps_display} | 매출 {data['rev_growth']:.1f}% | 이익률 {data['margin']:.1f}%")
    else:
        print(f"  ❌ 데이터 없음")
    time.sleep(0.3)

with open("fundamentals.json", "w") as f:
    json.dump(fundamentals, f, indent=2)

print(f"\n✅ 완료! 총 {len(fundamentals)}개 저장됨")
