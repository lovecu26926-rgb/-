import pandas as pd
import numpy as np
import yfinance as yf
import requests
import os
import time

# =========================
# 설정
# =========================
TREND_CSV = "trend_universe.csv"
SUPERTREND_CSV = "supertrend_universe.csv"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

MAX_PER_CATEGORY = 5

VOL_BREAK_20  = 1.2
VOL_BREAK_50  = 1.3
VOL_BREAK_52W = 1.5

TREND_REVERSAL_MIN_VOL = 1.3

RS_MIN = {
    "돌파_52W": 0,
    "돌파_50": 0,
    "돌파_20": 0,
    "눌림목": 0,
    "골든크로스": -20,
    "추세전환": None,
}

SUPERTREND_CATS = {"돌파_52W", "돌파_50", "돌파_20", "눌림목", "골든크로스"}
TREND_CATS = {"추세전환"}

CATEGORIES = ["돌파_52W", "돌파_50", "돌파_20", "눌림목", "골든크로스", "추세전환"]

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
# SPY
# =========================
def get_spy_return():
    spy = yf.download("SPY", period="1y", auto_adjust=True, progress=False)
    if spy is None or spy.empty:
        return 0.0
    return float((spy["Close"].iloc[-1] / spy["Close"].iloc[0] - 1) * 100)

SPY_RET = get_spy_return()

# =========================
# RS
# =========================
def calc_rs(df):
    try:
        stock_ret = (df["Close"].iloc[-1] / df["Close"].iloc[0] - 1) * 100
        return float(stock_ret - SPY_RET)
    except:
        return None

# =========================
# VOL
# =========================
def calc_vol_ratio(df):
    vol = df["Volume"]
    today = vol.iloc[-1]
    avg20 = vol.iloc[-21:-1].mean()
    return float(today / avg20) if avg20 else 1.0

# =========================
# SIGNAL ENGINE 1 (SUPER TREND)
# =========================
def get_supertrend_signals(df, vol_ratio):
    signals = []

    close = df["Close"]
    high = df["High"]

    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()

    c = close.iloc[-1]

    high52 = high.rolling(252).max().shift(1).iloc[-1]
    high50 = high.rolling(50).max().shift(1).iloc[-1]
    high20 = high.rolling(20).max().shift(1).iloc[-1]

    ma20_last = ma20.iloc[-1]
    ma50_last = ma50.iloc[-1]
    ma20_prev = ma20.iloc[-2]
    ma50_prev = ma50.iloc[-2]

    # 돌파
    if c > high52 and vol_ratio >= VOL_BREAK_52W:
        signals.append("돌파_52W")
    elif c > high50 and vol_ratio >= VOL_BREAK_50:
        signals.append("돌파_50")
    elif c > high20 and vol_ratio >= VOL_BREAK_20:
        signals.append("돌파_20")

    # 눌림
    if ma20_last > ma50_last and c < ma20_last:
        signals.append("눌림목")

    # 골든크로스
    if ma20_prev <= ma50_prev and ma20_last > ma50_last:
        signals.append("골든크로스")

    return signals

# =========================
# SIGNAL ENGINE 2 (TREND REVERSAL)
# =========================
def get_trend_signals(df, vol_ratio):
    signals = []

    close = df["Close"]

    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()

    c = close.iloc[-1]

    ma20_last = ma20.iloc[-1]
    ma50_last = ma50.iloc[-1]
    ma20_prev = ma20.iloc[-2]
    ma50_prev = ma50.iloc[-2]

    if (ma20_prev > ma50_prev and
        ma20_last > ma50_last and
        c > ma20_last):
        signals.append("추세전환")

    return signals

# =========================
# RS FILTER
# =========================
def rs_pass(cat, rs):
    min_rs = RS_MIN.get(cat)
    if min_rs is None:
        return True
    if rs is None:
        return False
    return rs >= min_rs

# =========================
# FUND LOAD (간단 버전 유지)
# =========================
def load_symbols():
    dfs = []

    for path, source in [(SUPERTREND_CSV, "supertrend"), (TREND_CSV, "trend")]:
        if os.path.exists(path):
            df = pd.read_csv(path)
            df["source"] = source
            dfs.append(df)

    df = pd.concat(dfs)
    if "Symbol" not in df.columns:
        df = df.rename(columns={df.columns[0]: "Symbol"})

    return df.set_index("Symbol")["source"].to_dict()

# =========================
# SCAN
# =========================
def scan():

    source_map = load_symbols()
    tickers = list(source_map.keys())

    buckets = {c: [] for c in CATEGORIES}

    print(f"[SCAN] {len(tickers)} tickers | SPY {SPY_RET:.2f}%")

    for t in tickers:

        source = source_map.get(t)

        try:
            df = yf.download(t, period="1y", auto_adjust=True, progress=False)
            if df is None or df.empty:
                continue

            rs = calc_rs(df)
            vol = calc_vol_ratio(df)
            price = df["Close"].iloc[-1]

            # 🔥 핵심 분리
            if source == "supertrend":
                signals = get_supertrend_signals(df, vol)
                allowed = SUPERTREND_CATS
            else:
                signals = get_trend_signals(df, vol)
                allowed = TREND_CATS

            if not signals:
                continue

            for s in signals:

                if s not in allowed:
                    continue

                if not rs_pass(s, rs):
                    continue

                primary = rs

                buckets[s].append((t, primary, vol, price))

            time.sleep(0.2)

        except:
            continue

    # =========================
    # OUTPUT
    # =========================
    msg = ""

    for cat in CATEGORIES:
        msg += f"\n🏆 [{cat}]\n\n"

        items = buckets[cat][:MAX_PER_CATEGORY]

        if not items:
            msg += "없음\n"
            continue

        for i, (t, rs, vol, price) in enumerate(items, 1):
            msg += f"{i}. {t} ${price:.2f} | RS {rs:.1f} | VOL {vol:.2f}x\n"

    print(msg)
    send_telegram(msg)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    scan()
