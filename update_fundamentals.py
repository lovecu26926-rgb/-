import requests
import json
import pandas as pd
import time
import os

# 🔑 API 키는 환경 변수로 관리하세요 (보안)
# 직접 입력 시에는 여기에 본인 키를 넣으세요
FMP_API_KEY = os.environ.get("FMP_API_KEY", "YOUR_API_KEY_HERE")

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
    """
    FMP API에서 재무 데이터를 가져옵니다.
    - 연간(Annual) 데이터를 강제로 가져옵니다 (period=annual)
    - 분모가 0이거나 음수인 경우를 방어합니다.
    """
    try:
        # 1️⃣ 연간 손익계산서 (period=annual 필수!)
        income_url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}?apikey={FMP_API_KEY}&limit=2&period=annual"
        income_resp = requests.get(income_url, timeout=10)
        income_data = income_resp.json()

        if not income_data or len(income_data) < 2:
            return None

        latest = income_data[0]    # 올해
        previous = income_data[1]  # 작년

        # --- 매출 성장률 ---
        rev_latest = latest.get('revenue', 0)
        rev_prev = previous.get('revenue', 0)
        if rev_prev > 0:
            rev_growth = ((rev_latest - rev_prev) / rev_prev) * 100
        else:
            rev_growth = 0  # 분모가 0이면 0으로 처리 (또는 None)

        # --- EPS 성장률 (음수/0 방어) ---
        eps_latest = latest.get('eps', 0)
        eps_prev = previous.get('eps', 0)

        if eps_prev > 0:
            eps_growth = ((eps_latest - eps_prev) / eps_prev) * 100
        elif eps_prev < 0 and eps_latest > eps_prev:
            # 적자에서 흑자로 전환된 경우 (예: -1 → 2)
            eps_growth = 999.0  # "흑자전환"을 의미하는 큰 값
        else:
            eps_growth = 0  # 적자 지속 또는 데이터 없음

        # --- 순이익률 (프로필) ---
        profile_url = f"https://financialmodelingprep.com/api/v3/profile/{ticker}?apikey={FMP_API_KEY}"
        profile_resp = requests.get(profile_url, timeout=10)
        profile_data = profile_resp.json()
        margin = 0
        if profile_data and isinstance(profile_data, list):
            margin = profile_data[0].get('profitMargin', 0) * 100  # 퍼센트

        return {
            'eps_growth': round(eps_growth, 2),
            'rev_growth': round(rev_growth, 2),
            'margin': round(margin, 2),
            # 디버깅용 원본 데이터 (필요시 활용)
            'eps_prev': round(eps_prev, 2),
            'eps_latest': round(eps_latest, 2)
        }
    except Exception as e:
        print(f"⚠️ {ticker} 오류: {e}")
        return None

# =========================
# 실행
# =========================
tickers = get_tickers()
print(f"📊 총 {len(tickers)}개 종목")

fundamentals = {}

for i, t in enumerate(tickers, 1):
    print(f"[{i}/{len(tickers)}] {t} 조회 중...")
    data = fetch_fmp(t)
    if data:
        fundamentals[t] = data
        # 성장률이 999인 경우 "흑자전환"으로 표시
        eps_display = "흑자전환" if data['eps_growth'] == 999 else f"{data['eps_growth']:.1f}%"
        print(f"  ✅ EPS {eps_display} | 매출 {data['rev_growth']:.1f}% | 이익률 {data['margin']:.1f}%")
    else:
        print(f"  ❌ 데이터 없음")
    time.sleep(0.3)  # FMP 무료 제한 (분당 5회)

# 저장
with open("fundamentals.json", "w") as f:
    json.dump(fundamentals, f, indent=2)

print(f"\n✅ 완료! 총 {len(fundamentals)}개 저장됨")
