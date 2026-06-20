import pandas as pd
import yfinance as yf
import requests
import json
import os
import time

# =========================
# 설정
# =========================
TREND_CSV = "trend_universe.csv"
SUPERTREND_CSV = "supertrend_universe.csv"

FMP_CACHE_FILE = "fundamentals.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =========================
# 텔레그램
# =========================
def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=10
        )
    except Exception as e:
        print("Telegram error:", e)

# =========================
# FMP 캐시 로드
# =========================
def load_fmp():
    if not os.path.exists(FMP_CACHE_FILE):
        return {}
    with open(FMP_CACHE_FILE, "r") as f:
        return json.load(f)

fmp_data = load_fmp()

# =========================
# SPY 기준 RS
# =========================
def get_spy_return():
    spy = yf.download("SPY", period="1y", interval="1d", auto_adjust=True, progress=False)
    if spy.empty:
        return 0
    return (spy["Close"].iloc[-1] / spy["Close"].iloc[0] - 1) * 100

SPY_RET = get_spy_return()

def calc_rs(df):
    try:
        stock_ret = (df["Close"].iloc[-1] / df["Close"].iloc[0] - 1) * 100
        return stock_ret - SPY_RET
    except:
        return 0

# =========================
# 신호 생성
# =========================
def get_signals(df):
    close = df["Close"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    high20 = df["High"].rolling(20).max().shift(1)

    signals = []

    # 돌파
    if close.iloc[-1] > high20.iloc[-1] * 1.01:
        signals.append("돌파")

    # 눌림목
    if ma20.iloc[-1] > ma50.iloc[-1] and close.iloc[-1] < ma20.iloc[-1]:
        signals.append("눌림목")

    # 골든크로스
    if ma20.iloc[-2] <= ma50.iloc[-2] and ma20.iloc[-1] > ma50.iloc[-1]:
        signals.append("골든크로스")

    # 추세전환
    if ma20.iloc[-2] < ma50.iloc[-2] and ma20.iloc[-1] > ma50.iloc[-1]:
        signals.append("추세전환")

    return signals

# =========================
# 20일 모멘텀
# =========================
def momentum_20d(df):
    try:
        return (df["Close"].iloc[-1] / df["Close"].iloc[-20] - 1) * 100
    except:
        return 0

# =========================
# 스캔
# =========================
def scan():
    trend = pd.read_csv(TREND_CSV)["Symbol"].dropna().tolist()
    supert = pd.read_csv(SUPERTREND_CSV)["Symbol"].dropna().tolist()

    tickers = list(set(trend + supert))

    buckets = {
        "돌파": [],
        "눌림목": [],
        "골든크로스": [],
        "추세전환": []
    }

    print(f"[SCAN] tickers={len(tickers)} | SPY_RS={SPY_RET:.2f}%")

    for t in tickers:
        try:
            df = yf.download(t, period="1y", interval="1d", auto_adjust=True, progress=False)

            if df.empty:
                continue

            rs = calc_rs(df)
            signals = get_signals(df)

            if not signals:
                continue

            for s in signals:
                if s == "추세전환":
                    buckets[s].append((t, momentum_20d(df)))
                else:
                    buckets[s].append((t, rs))

            time.sleep(0.1)

        except:
            continue

    # 정렬
    for k in ["돌파", "눌림목", "골든크로스"]:
        buckets[k].sort(key=lambda x: x[1], reverse=True)

    buckets["추세전환"].sort(key=lambda x: x[1], reverse=True)

    # =========================
    # 출력 (전체)
    # =========================
    msg = ""

    for cat in ["돌파", "눌림목", "골든크로스", "추세전환"]:
        msg += f"\n🏆 [{cat}]\n\n"

        items = buckets[cat]

        if not items:
            msg += "없음\n"
            continue

        for i, (t, val) in enumerate(items, 1):

            fund = fmp_data.get(t, {})
            rev = fund.get("revenue_growth", 0)
            eps = fund.get("eps_growth", 0)

            if cat == "추세전환":
                msg += f"{i}. {t} | 20D {val:.1f}% | 매출 {rev}% | EPS {eps}%\n"
            else:
                msg += f"{i}. {t} | RS {val:.1f} | 매출 {rev}% | EPS {eps}%\n"

    print(msg)
    send_telegram(msg)

# =========================
# 실행
# =========================
if __name__ == "__main__":
    scan()
