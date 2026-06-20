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
FMP_API_KEY = os.environ.get("FMP_API_KEY")

# ==================== 2. 데이터 ====================
TREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"
SUPERTREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/supertrend_universe.csv"
FMP_CACHE = "fundamentals.json"   # 👈 이 파일에 모든 종목의 재무 데이터를 저장

# ==================== 3. 텔레그램 ====================
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
        print("텔레그램 오류:", e)

# ==================== 4. FMP API (데이터 가져오기) ====================
def fetch_from_fmp(ticker):
    """실제 FMP API를 호출해서 재무 데이터를 가져옴 (JSON 저장용)"""
    url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}?limit=2&apikey={FMP_API_KEY}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if len(data) >= 2:
                cur, prev = data[0], data[1]

                rev_growth = (cur["revenue"] - prev["revenue"]) / abs(prev["revenue"]) * 100
                eps_cur = cur["netIncome"] / cur["weightedAverageShsOut"]
                eps_prev = prev["netIncome"] / prev["weightedAverageShsOut"]
                eps_growth = (eps_cur - eps_prev) / abs(eps_prev) * 100

                return {"rev_growth": rev_growth, "eps_growth": eps_growth}
    except:
        pass
    return {"rev_growth": 0, "eps_growth": 0}

# ==================== 5. FMP 캐시 (읽기 전용) ====================
def get_fmp(ticker):
    """👉 [수정] JSON 파일에서 읽기만 함 (API 호출 없음)"""
    if os.path.exists(FMP_CACHE):
        with open(FMP_CACHE, "r") as f:
            data = json.load(f)
        return data.get(ticker, {"rev_growth": 0, "eps_growth": 0})
    return {"rev_growth": 0, "eps_growth": 0}

def score_growth(f):
    return f["rev_growth"] * 0.4 + f["eps_growth"] * 0.6

# ==================== 6. 기술적 분석 ====================
def score_trend(df):
    close = df["Close"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    high20 = df["High"].rolling(20).max().shift(1)

    score = 0
    sig = []

    if close.iloc[-1] > high20.iloc[-1]:
        score += 60
        sig.append("BREAKOUT")

    if ma20.iloc[-2] <= ma50.iloc[-2] and ma20.iloc[-1] > ma50.iloc[-1]:
        score += 50
        sig.append("GOLDEN_CROSS")

    if ma20.iloc[-1] > ma50.iloc[-1] and close.iloc[-1] < ma20.iloc[-1]:
        score += 40
        sig.append("PULLBACK")

    return score, sig if sig else None

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

    if len(trend) >= 2 and trend[-2] == -1 and trend[-1] == 1:
        return 50, "BUY_FLIP"
    return 0, None

# ==================== 7. 스캐너 ====================
def scan(url, name, limit):
    tickers = pd.read_csv(url)["Symbol"].dropna().str.upper().tolist()
    results = []

    for t in tickers:
        try:
            df = yf.download(t, period="3mo", interval="1d", auto_adjust=True, progress=False)
            if df.empty:
                continue

            if name == "TREND":
                tech, sig = score_trend(df)
            else:
                tech, sig = score_supertrend(df)

            if not sig:
                continue

            # 👉 [수정] 여기서는 JSON에서만 읽음 (API 호출 없음)
            f = get_fmp(t)
            g = score_growth(f)

            if name == "TREND":
                final_score = tech * 0.7 + g * 0.3
            else:
                final_score = g * 0.7 + tech * 0.3

            results.append((t, final_score, g, tech, sig))
            time.sleep(0.15)

        except:
            continue

    results.sort(key=lambda x: x[1], reverse=True)
    top = results[:limit]

    if not top:
        print(f"[{name}] 신호 없음")
        return

    msg = f"[{name}] TOP {len(top)}\n\n"
    for i, (t, final_score, g, tech, sig) in enumerate(top, 1):
        # sig가 리스트면 예쁘게 출력
        if isinstance(sig, list):
            sig_str = " + ".join(sig)
        else:
            sig_str = sig
        msg += f"{i}. {t} | {final_score:.1f} (성장 {g:.1f} + 기술 {tech:.1f}) | {sig_str}\n"

    send_telegram(msg)

# ==================== 8. 실행 (메인) ====================
def run():
    now = datetime.now(pytz.timezone("Asia/Seoul"))
    hour = now.hour

    # 모든 티커 리스트 합치기
    trend = pd.read_csv(TREND_CSV)["Symbol"].dropna().str.upper().tolist()
    supert = pd.read_csv(SUPERTREND_CSV)["Symbol"].dropna().str.upper().tolist()
    all_tickers = list(set(trend + supert))

    # 👉 [수정] 오후 2시에만 전체 종목 API 호출 → JSON 통째로 저장 (프리패치)
    if hour == 14:
        print("🔄 오후 2시 프리패치 실행 (전체 종목 JSON 저장)")
        cache = {}
        for t in all_tickers:
            cache[t] = fetch_from_fmp(t)   # 실제 API 호출
            time.sleep(0.3)                # Rate Limit 방지
        with open(FMP_CACHE, "w") as f:
            json.dump(cache, f)
        print(f"✅ fundamentals.json 저장 완료! (총 {len(cache)}개)")

    # 기술적 스캔 실행 (get_fmp는 JSON에서 읽기만 함)
    scan(TREND_CSV, "TREND", 20)
    scan(SUPERTREND_CSV, "SUPERTREND", 10)

if __name__ == "__main__":
    run()
