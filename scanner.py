import os
import time
import json
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
import pytz

# ==================== 1. 환경 변수 ====================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FMP_API_KEY = os.environ.get("FMP_API_KEY")  # GitHub Secrets에 등록 필수!

# ==================== 2. 데이터 파일 경로 ====================
TREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"
SUPERTREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/supertrend_universe.csv"
FMP_CACHE = "fundamentals.json"

# ==================== 3. 텔레그램 발송 ====================
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(msg)
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=10
        )
    except Exception as e:
        print(f"텔레그램 발송 실패: {e}")

# ==================== 4. FMP 데이터 프리패치 (첫 실행 때만) ====================
def fetch_from_fmp(ticker):
    """실제 FMP API를 호출해서 재무 데이터를 가져옴"""
    url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}?limit=2&apikey={FMP_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            statements = response.json()
            if statements and len(statements) >= 2:
                current = statements[0]
                previous = statements[1]
                
                # 매출 성장률 (%)
                rev_growth = (current["revenue"] - previous["revenue"]) / abs(previous["revenue"]) * 100
                
                # EPS 성장률 (%)
                eps_current = current["netIncome"] / current["weightedAverageShsOut"]
                eps_previous = previous["netIncome"] / previous["weightedAverageShsOut"]
                eps_growth = (eps_current - eps_previous) / abs(eps_previous) * 100
                
                return {"eps_growth": eps_growth, "rev_growth": rev_growth}
    except Exception as e:
        print(f"FMP API 에러 ({ticker}): {e}")
    return {"eps_growth": 0, "rev_growth": 0}

def prefetch_fmp(tickers):
    """모든 티커의 FMP 데이터를 미리 가져와서 캐시에 저장"""
    # 기존 캐시 읽기
    if os.path.exists(FMP_CACHE):
        with open(FMP_CACHE, "r") as f:
            data = json.load(f)
    else:
        data = {}
    
    # 아직 캐시에 없는 종목 찾기
    missing = [t for t in tickers if t not in data]
    
    if not missing:
        print("✅ 모든 FMP 데이터가 캐시에 있습니다.")
        return
    
    print(f"🔄 FMP API 호출 중: {len(missing)}개 종목")
    for t in missing:
        data[t] = fetch_from_fmp(t)
        time.sleep(0.2)  # Rate limit 방지
    
    # 캐시 저장
    with open(FMP_CACHE, "w") as f:
        json.dump(data, f)
    print("✅ FMP 캐시 업데이트 완료!")

# ==================== 5. 캐시에서 FMP 데이터 읽기 (API 호출 없음) ====================
def get_fmp(ticker):
    if os.path.exists(FMP_CACHE):
        with open(FMP_CACHE, "r") as f:
            data = json.load(f)
        return data.get(ticker, {"eps_growth": 0, "rev_growth": 0})
    return {"eps_growth": 0, "rev_growth": 0}

def score_growth(f):
    eps = f.get("eps_growth", 0)
    rev = f.get("rev_growth", 0)
    return rev * 0.4 + eps * 0.6  # 매출 40%, EPS 60%

# ==================== 6. 기술적 분석 함수 ====================
def score_trend(df):
    close = df["Close"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    high20 = df["High"].rolling(20).max().shift(1)
    
    # ① 돌파매매 (60점)
    if close.iloc[-1] > high20.iloc[-1]:
        return 60, "BREAKOUT"
    # ② 골든크로스 (50점)
    if len(ma20) >= 2 and ma20.iloc[-2] <= ma50.iloc[-2] and ma20.iloc[-1] > ma50.iloc[-1]:
        return 50, "GOLDEN_CROSS"
    # ③ 눌림목매수 (40점)
    if ma20.iloc[-1] > ma50.iloc[-1]:
        return 40, "PULLBACK"
    return 0, None

def score_supertrend(df):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    
    atr = (high - low).rolling(14).mean()
    mid = (high + low) / 2
    upper = mid + 3 * atr
    lower = mid - 3 * atr
    
    trend = [1]
    for i in range(1, len(df)):
        if close.iloc[i] > upper.iloc[i-1]:
            trend.append(1)
        elif close.iloc[i] < lower.iloc[i-1]:
            trend.append(-1)
        else:
            trend.append(trend[-1])
    
    # 하락→상승 플립 감지
    if len(trend) >= 2 and trend[-2] == -1 and trend[-1] == 1:
        return 50, "ST_FLIP"
    return 0, None

# ==================== 7. 메인 스캔 함수 ====================
def scan(url, name, limit):
    tickers = pd.read_csv(url)["Symbol"].dropna().str.upper().tolist()
    results = []
    
    for t in tickers:
        try:
            # ① 주가 데이터 다운로드
            df = yf.download(t, period="3mo", interval="1d", auto_adjust=True, progress=False)
            if df.empty:
                continue
            
            # ② 리스트별 기술 분석 (게이트키퍼)
            if name == "TREND":
                tech, sig = score_trend(df)
            else:
                tech, sig = score_supertrend(df)
            
            # 신호 없으면 즉시 버림 (FMP 데이터 안 읽음)
            if not sig:
                continue
            
            # ③ FMP 캐시에서 성장 데이터 읽기
            f = get_fmp(t)
            g = score_growth(f)
            
            # ④ 가중치 적용
            if name == "TREND":
                final_score = tech * 0.7 + g * 0.3
            else:
                final_score = g * 0.7 + tech * 0.3
            
            results.append((t, final_score, g, tech, sig))
            time.sleep(0.2)  # yfinance 차단 방지
            
        except Exception as e:
            continue
    
    # ⑤ 점수 정렬 및 상위 N개 추출
    results.sort(key=lambda x: x[1], reverse=True)
    top = results[:limit]
    
    # ⑥ 결과가 없으면 발송 안 함
    if not top:
        print(f"[{name}] 오늘 감지된 신호가 없습니다.")
        return
    
    # ⑦ 메시지 생성 (한글 매핑)
    msg = f"[{name}] TOP {len(top)}\n\n"
    for i, (t, final_score, g, tech, sig) in enumerate(top, 1):
        if sig == "BREAKOUT":
            strategy = "돌파매매"
        elif sig == "GOLDEN_CROSS" and name == "TREND":
            strategy = "골든크로스"
        elif sig == "PULLBACK":
            strategy = "눌림목매수"
        elif sig == "ST_FLIP" and name == "SUPERTREND":
            strategy = "추세전환"
        else:
            strategy = sig
        
        msg += f"{i}. {t} | {final_score:.1f} (성장 {g:.1f} + 기술 {tech:.1f}) | {strategy}\n"
    
    # ⑧ 텔레그램 전송
    send_telegram(msg)

# ==================== 8. 실행 함수 ====================
def run():
    # 현재 한국 시간 확인
    now = datetime.now(pytz.timezone('Asia/Seoul'))
    current_hour = now.hour
    
    # ① 모든 티커 리스트 합치기 (중복 제거)
    trend_tickers = pd.read_csv(TREND_CSV)["Symbol"].dropna().str.upper().tolist()
    super_tickers = pd.read_csv(SUPERTREND_CSV)["Symbol"].dropna().str.upper().tolist()
    all_tickers = list(set(trend_tickers + super_tickers))
    
    # ② 첫 실행(오후 2시)일 때만 FMP API 호출해서 캐시 채움
    if current_hour == 14:  # 한국 오후 2시
        print("🔄 장전 실행 - FMP 데이터 프리패치 시작")
        prefetch_fmp(all_tickers)
    else:
        print(f"⏰ 현재 시간 {current_hour}시 - 캐시에서 FMP 데이터 읽기")
    
    # ③ TREND 스캔 (최대 50개)
    scan(TREND_CSV, "TREND", 50)
    
    # ④ SUPERTREND 스캔 (최대 10개)
    scan(SUPERTREND_CSV, "SUPERTREND", 10)

if __name__ == "__main__":
    run()
