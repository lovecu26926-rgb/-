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
# SAFE UTIL
# =========================
def safe_float(x, default=-9999):
    try:
        if x is None:
            return default
        if isinstance(x, pd.Series):
            x = x.iloc[0]
        if isinstance(x, (list, tuple)):
            x = x[0]
        if pd.isna(x):
            return default
        return float(x)
    except:
        return default


def safe_df(df):
    if df is None:
        return None
    if not isinstance(df, pd.DataFrame):
        return None
    if df.empty:
        return None
    if "Close" not in df.columns:
        return None
    return df


def safe_sort_key(x):
    return safe_float(x[1], -9999)


def safe_text(x):
    return x if x is not None else "N/A"

# =========================
# TELEGRAM
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
# FMP CACHE
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
# SPY RS 기준
# =========================
def get_spy_return():
    try:
        spy = yf.download("SPY", period="1y", auto_adjust=True, progress=False)
        spy = safe_df(spy)

        if spy is None:
            return 0.0

        close = spy["Close"]
        return safe_float((close.iloc[-1] / close.iloc[0] - 1) * 100, 0.0)

    except:
        return 0.0


SPY_RET = safe_float(get_spy_return(), 0.0)

# =========================
# RS 계산
# =========================
def calc_rs(df, spy_ret):
    try:
        df = safe_df(df)
        if df is None:
            return None

        close = df["Close"]

        first = safe_float(close.iloc[0])
        last = safe_float(close.iloc[-1])

        if first <= 0 or last <= 0:
            return None

        stock_ret = (last / first - 1) * 100
        return safe_float(stock_ret - spy_ret)

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

        signals = []

        if close.iloc[-1] > high20.iloc[-1] * 1.01:
            signals.append("돌파")

        if ma20.iloc[-1] > ma50.iloc[-1] and close.iloc[-1] < ma20.iloc[-1]:
            signals.append("눌림목")

        if ma20.iloc[-2] <= ma50.iloc[-2] and ma20.iloc[-1] > ma50.iloc[-1]:
            signals.append("골든크로스")

        if ma20.iloc[-2] < ma50.iloc[-2] and ma20.iloc[-1] > ma50.iloc[-1]:
            signals.append("추세전환")

        return signals

    except:
        return []

# =========================
# 모멘텀
# =========================
def momentum_20d(df):
    try:
        df = safe_df(df)
        if df is None:
            return None

        return safe_float(
            (df["Close"].iloc[-1] / df["Close"].iloc[-20] - 1) * 100
        )
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
            df = safe_df(df)

            if df is None:
                continue

            rs = calc_rs(df, SPY_RET)
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

    # 정렬
    for k in ["돌파", "눌림목", "골든크로스"]:
        buckets[k].sort(key=safe_sort_key, reverse=True)

    buckets["추세전환"].sort(key=safe_sort_key, reverse=True)

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

            rev = safe_text(fund.get("revenue_growth"))
            eps = safe_text(fund.get("eps_growth"))

            if cat == "추세전환":
                msg += f"{i}. {t} | 20D {safe_float(val):.1f} | 매출 {rev} | EPS {eps}\n"
            else:
                msg += f"{i}. {t} | RS {safe_float(val):.1f} | 매출 {rev} | EPS {eps}\n"

    print(msg)
    send_telegram(msg)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    scan()
