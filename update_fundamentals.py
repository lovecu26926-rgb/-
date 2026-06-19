import requests
import json
import pandas as pd
import time
import os

# 🔑 Finnhub API 키 (환경 변수 우선)
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY")

# 테스트용 직접 입력 (환경변수가 없을 경우에만 사용)
if not FINNHUB_API_KEY:
    FINNHUB_API_KEY = "YOUR_FINNHUB_TOKEN_HERE"  # 테스트 시에만 직접 입력

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

def fetch_finnhub(ticker):
    """
    Finnhub API (stock/metric)로 재무 데이터를 가져옵니다.
    - ROE, 이익률, EPS 성장률, 매출 성장률 획득
    - 무료 플랜: 분당 60회 제한 → 1초 간격 유지
    """
    try:
        url = f"https://finnhub.io/api/v1/stock/metric?symbol={ticker}&metric=all&token={FINNHUB_API_KEY}"
        resp = requests.get(url, timeout=10)
        
        if resp.status_code != 200:
            return None
            
        data = resp.json()
        if not data or 'metric' not in data:
            return None
        
        metric = data['metric']
        
        # 1. ROE (자기자본이익률)
        roe = metric.get('roe', 0) or metric.get('roeTTM', 0) or 0
        # 2. 이익률 (Net Profit Margin)
        margin = metric.get('netProfitMargin', 0) or metric.get('profitMargin', 0) or 0
        # 3. EPS 성장률 (YoY)
        eps_growth = metric.get('epsGrowth', 0) or metric.get('epsGrowthTTM', 0) or 0
        # 4. 매출 성장률 (YoY)
        rev_growth = metric.get('revenueGrowth', 0) or metric.get('revenueGrowthTTM', 0) or 0

        # Finnhub는 보통 소수점(0.15)으로 오지만, 가끔 퍼센트(15.0)로 올 수도 있음 -> 둘 다 대비
        def convert(val):
            if val is None:
                return 0.0
            # 1보다 크면 이미 퍼센트(%), 1보다 작으면 소수점 -> * 100
            return round(val * 100 if val < 1 else val, 2)

        return {
            'eps_growth': convert(eps_growth),
            'rev_growth': convert(rev_growth),
            'roe': convert(roe),
            'margin': convert(margin),
        }
    except Exception as e:
        return None

# =========================
# 실행
# =========================
tickers = get_tickers()
print(f"📊 총 {len(tickers)}개 종목")

fundamentals = {}

for i, t in enumerate(tickers, 1):
    print(f"[{i}/{len(tickers)}] {t} 조회 중...")
    data = fetch_finnhub(t)
    if data:
        fundamentals[t] = data
        print(f"  ✅ EPS {data['eps_growth']:.1f}% | 매출 {data['rev_growth']:.1f}% | ROE {data['roe']:.1f}% | 이익률 {data['margin']:.1f}%")
    else:
        print(f"  ❌ 데이터 없음")
    
    # Finnhub 분당 60회 제한 준수 (1초 대기)
    time.sleep(1)

with open("fundamentals.json", "w") as f:
    json.dump(fundamentals, f, indent=2)

print(f"\n✅ 완료! 총 {len(fundamentals)}개 저장됨")
