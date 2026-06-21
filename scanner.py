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

VOL_FAVORS_HIGH = {
    "돌파": True,
    "눌림목": False,
    "골든크로스": True,
    "추세전환": True,
}

CATEGORY_WEIGHTS = {
    "돌파": {"rs": 0.5, "vol": 0.5},
    "눌림목": {"rs": 0.7, "vol": 0.3},
    "골든크로스": {"rs": 0.6, "vol": 0.4},
    "추세전환": {"rs": 0.7, "vol": 0.3},
}

TREND_REVERSAL_MIN_VOL_RATIO = 1.3


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
# 캐시 로드 (forward fundamentals)
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
# SPY
# =========================
def get_spy_return():
    spy = yf.download("SPY", period="1y", auto_adjust=True, progress=False)
    if spy is None or spy.empty:
        return 0.0

    c = spy["Close"]
    return float((c.iloc[-1] / c.iloc[0] - 1) * 100)

SPY_RET = get_spy_return()


# =========================
# RS
# =========================
def calc_rs(df):
    if df is None or df.empty:
        return None

    c = df["Close"]
    stock_ret = (c.iloc[-1] / c.iloc[0] - 1) * 100
    return float(stock_ret - SPY_RET)


# =========================
# volume ratio
# =========================
def calc_vol_ratio(df):
    try:
        vol = df["Volume"]
        return float(vol.iloc[-1] / vol.iloc[-21:-1].mean())
    except:
        return None


# =========================
# signals
# =========================
def get_signals(df):
    close = df["Close"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    high20 = df["High"].rolling(20).max().shift(1)

    c = close.iloc[-1]
    h = high20.iloc[-1]

    signals = []

    if c > h:
        signals.append("돌파")

    if ma20.iloc[-1] > ma50.iloc[-1] and c < ma20.iloc[-1]:
        signals.append("눌림목")

    if ma20.iloc[-2] <= ma50.iloc[-2] and ma20.iloc[-1] > ma50.iloc[-1]:
        signals.append("골든크로스")

    if ma20.iloc[-2] < ma50.iloc[-2] and ma20.iloc[-1] > ma50.iloc[-1]:
        signals.append("추세전환")

    return signals


# =========================
# momentum
# =========================
def momentum_20d(df):
    try:
        return float(df["Close"].iloc[-1] / df["Close"].iloc[-20] - 1) * 100
    except:
        return None


# =========================
# percentile rank
# =========================
def percentile_rank(vals):
    clean = [(i, v) for i, v in enumerate(vals) if v is not None]
    clean.sort(key=lambda x: x[1])

    n = len(clean)
    out = {}

    for r, (i, v) in enumerate(clean):
        out[i] = (r / (n - 1) * 100) if n > 1 else 50

    return out


# =========================
# scoring
# =========================
def attach_scores(items, cat):
    prim = [x[1] for x in items]
    vol = [x[2] for x in items]

    pr = percentile_rank(prim)
    vr = percentile_rank(vol)

    weights = CATEGORY_WEIGHTS.get(cat)

    scored = []

    for i, (t, p, v) in enumerate(items):

        p_score = pr.get(i, 50)
        v_score = vr.get(i, 50)

        if not VOL_FAVORS_HIGH[cat]:
            v_score = 100 - v_score

        score = weights["rs"] * p_score + weights["vol"] * v_score

        scored.append((t, p, v, score))

    return sorted(scored, key=lambda x: x[3], reverse=True)


# =========================
# scan
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

    print(f"tickers={len(tickers)} SPY={SPY_RET:.2f}")

    for t in tickers:

        try:
            df = yf.download(t, period="1y", auto_adjust=True, progress=False)

            if df is None or df.empty:
                continue

            rs = calc_rs(df)
            vol = calc_vol_ratio(df)
            sig = get_signals(df)

            if not sig:
                continue

            for s in sig:

                primary = momentum_20d(df) if s == "추세전환" else rs

                if s == "추세전환":
                    if vol is None or vol < TREND_REVERSAL_MIN_VOL_RATIO:
                        continue

                buckets[s].append([t, primary, vol])

            time.sleep(0.05)

        except:
            continue


    msg = ""

    for cat in ["돌파", "눌림목", "골든크로스", "추세전환"]:

        msg += f"\n[{cat}]\n"

        scored = attach_scores(buckets[cat], cat)

        if not scored:
            msg += "없음\n"
            continue

        for i, (t, p, v, s) in enumerate(scored, 1):

            f = fmp_data.get(t, {})

            eps = f.get("eps_forward_growth", "N/A")
            rev = f.get("revenue_forward_growth", "N/A")

            msg += (
                f"{i}. {t} | {s:.0f} | RS {p:.1f} | VOL {v:.1f}x "
                f"| EPS {eps} | REV {rev}\n"
            )

    print(msg)
    send_telegram(msg)


if __name__ == "__main__":
    scan()
