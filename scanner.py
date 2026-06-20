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
FMP_CACHE = "fundamentals.json"

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

# ==================== 4. FMP API ====================
def fetch_from_fmp(ticker):
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

def get_fmp(ticker):
    if os.path.exists(FMP_CACHE):
        with open(FMP_CACHE, "r") as f:
            data = json.load(f)
        return data.get(ticker, {"rev_growth": 0, "eps_growth": 0})
    return {"rev_growth": 0, "eps_growth": 0}

def score_growth(f):
    return f["rev_growth"] * 0.4 + f["eps_growth"] * 0.6

# ==================== 5. 🔥 기술신호 (완화 버전 핵심) ====================
def score_trend(df):
    close = df["Close"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    high20 = df["High"].rolling(20).max().shift(1)

    score = 0
    sig = []

    # 돌파 (근접 돌파)
    if close.iloc[-1] >= high20.iloc[-1] * 0.98:
        score += 60
        sig.append("BREAKOUT")

    # 추세 상태 (골든 대신 상태형)
    if ma20.iloc[-1] > ma50.iloc[-1]:
        score += 50
        sig.append("UPTREND")

    # 눌림 (MA20 근처)
    if abs(close.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1] < 0.02:
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

    if len(trend) >= 2 and trend[-2] <= 0 and trend[-1] == 1:
        return 50, "BUY_FLIP"

    return 0, None

# ==================== 6. 스캐너 ====================
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

            f = get_fmp(t)
            g = score_growth(f)

            if name == "TREND":
                final_score = tech * 0.7 + g * 0.3
            else:
                final_score = tech * 0.3 + g * 0.7

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
        sig_str = " + ".join(sig) if isinstance(sig, list) else sig
        msg += f"{i}. {t} | {final_score:.1f} (성장 {g:.1f} + 기술 {tech:.1f}) | {sig_str}\n"

    send_telegram(msg)

# ==================== 7. 실행 ====================
def run():
    now = datetime.now(pytz.timezone("Asia/Seoul"))
    hour = now.hour

    trend = pd.read_csv(TREND_CSV)["Symbol"].dropna().str.upper().tolist()
    supert = pd.read_csv(SUPERTREND_CSV)["Symbol"].dropna().str.upper().tolist()

    all_tickers = list(set(trend + supert))

    if hour == 14:
        print("🔄 FMP 프리패치 실행")
        cache = {}
        for t in all_tickers:
            cache[t] = fetch_from_fmp(t)
            time.sleep(0.3)

        with open(FMP_CACHE, "w") as f:
            json.dump(cache, f)

        print("✅ 캐시 저장 완료")

    scan(TREND_CSV, "TREND", 20)
    scan(SUPERTREND_CSV, "SUPERTREND", 10)


if __name__ == "__main__":
    run()
