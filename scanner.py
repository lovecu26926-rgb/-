import pandas as pd
import numpy as np
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
    except:
        pass

# =========================
# FMP 캐시 로드
# =========================
def load_fmp():
    if not os.path.exists(FMP_CACHE_FILE):
        return {}
    try:
        with open(FMP_CACHE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

fmp_data = load_fmp()

# =========================
# SPY 기준
# =========================
def get_spy_return():
    try:
        spy = yf.download("SPY", period="1y", auto_adjust=True, progress=False)
        if spy is None or spy.empty:
            return 0.0

        close = spy["Close"]
        first = close.iloc[0].item()
        last = close.iloc[-1].item()

        return float((last / first - 1) * 100)
    except:
        return 0.0

SPY_RET = get_spy_return()

# =========================
# RS 계산
# =========================
def calc_rs(df):
    try:
        if df is None or df.empty:
            return None

        close = df["Close"]

        first = close.iloc[0].item()
        last = close.iloc[-1].item()

        stock_ret = (last / first - 1) * 100
        return float(stock_ret - SPY_RET)

    except:
        return None

# =========================
# 신호
# =========================
def get_signals(df):
    try:
        close = df["Close"]
        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()
        high20 = df["High"].rolling(20).max().shift(1)

        # yfinance가 단일 티커도 MultiIndex 컬럼을 반환하는 경우가 있어
        # close/high20 등이 1컬럼 DataFrame이 되고 .iloc[-1]이 Series로 나옴.
        # 이를 if문에 바로 넣으면 "truth value of a Series is ambiguous" 에러가 나서
        # 아래 except에 걸려 무조건 빈 리스트가 반환됨 -> 모든 종목이 신호 없음으로 처리되던 버그.
        # .item()으로 스칼라 변환해서 해결.
        c_last = close.iloc[-1].item()
        h20_last = high20.iloc[-1].item()
        ma20_last = ma20.iloc[-1].item()
        ma50_last = ma50.iloc[-1].item()
        ma20_prev = ma20.iloc[-2].item()
        ma50_prev = ma50.iloc[-2].item()

        signals = []

        # 돌파 (완화)
        if c_last > h20_last:
            signals.append("돌파")

        # 눌림목 (완화)
        if ma20_last > ma50_last and c_last < ma20_last:
            signals.append("눌림목")

        # 골든크로스
        if ma20_prev <= ma50_prev and ma20_last > ma50_last:
            signals.append("골든크로스")

        # 추세전환
        if ma20_prev < ma50_prev and ma20_last > ma50_last:
            signals.append("추세전환")

        return signals

    except:
        return []

# =========================
# 모멘텀
# =========================
def momentum_20d(df):
    try:
        return float((df["Close"].iloc[-1].item() / df["Close"].iloc[-20].item() - 1) * 100)
    except:
        return None

# =========================
# SCAN
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
            df = yf.download(t, period="1y", auto_adjust=True, progress=False)

            if df is None or df.empty:
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

            time.sleep(0.05)

        except:
            continue

    # =========================
    # RS 정렬
    # =========================
    for k in ["돌파", "눌림목", "골든크로스"]:
        buckets[k].sort(key=lambda x: x[1] if x[1] is not None else -9999, reverse=True)

    buckets["추세전환"].sort(key=lambda x: x[1] if x[1] is not None else -9999, reverse=True)

    # =========================
    # 출력
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
            rev = fund.get("revenue_growth", "N/A")
            eps = fund.get("eps_growth", "N/A")

            if cat == "추세전환":
                msg += f"{i}. {t} | 20D {val:.1f} | 매출 {rev} | EPS {eps}\n"
            else:
                msg += f"{i}. {t} | RS {val:.1f} | 매출 {rev} | EPS {eps}\n"

    print(msg)
    send_telegram(msg)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    scan()
