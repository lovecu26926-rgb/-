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
# 펀더멘탈 로드 (YoY 통일)
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
# SPY RS
# =========================
def get_spy_return():
    spy = yf.download("SPY", period="1y", auto_adjust=True, progress=False)
    if spy is None or spy.empty:
        return 0.0
    c = spy["Close"]
    return float((c.iloc[-1] / c.iloc[0] - 1) * 100)

SPY_RET = get_spy_return()

def calc_rs(df):
    if df is None or df.empty:
        return None
    c = df["Close"]
    return float((c.iloc[-1] / c.iloc[0] - 1) * 100 - SPY_RET)

# =========================
# 거래량
# =========================
def calc_vol_ratio(df):
    try:
        vol = df["Volume"]
        return float(vol.iloc[-1] / vol.iloc[-21:-1].mean())
    except:
        return None

# =========================
# 시그널
# =========================
def get_signals(df):
    close = df["Close"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    high20 = df["High"].rolling(20).max().shift(1)

    c = close.iloc[-1]

    sig = []

    if c > high20.iloc[-1]:
        sig.append("돌파")

    if ma20.iloc[-1] > ma50.iloc[-1] and c < ma20.iloc[-1]:
        sig.append("눌림목")

    if ma20.iloc[-2] <= ma50.iloc[-2] and ma20.iloc[-1] > ma50.iloc[-1]:
        sig.append("골든크로스")

    if ma20.iloc[-2] < ma50.iloc[-2] and ma20.iloc[-1] > ma50.iloc[-1]:
        sig.append("추세전환")

    return sig

# =========================
# 티커
# =========================
def load_tickers():
    t1 = pd.read_csv(TREND_CSV)["Symbol"].dropna().tolist()
    t2 = pd.read_csv(SUPERTREND_CSV)["Symbol"].dropna().tolist()
    return list(set(t1 + t2))

# =========================
# SCAN
# =========================
def scan():

    tickers = load_tickers()

    buckets = {
        "돌파": [],
        "눌림목": [],
        "골든크로스": [],
        "추세전환": []
    }

    print(f"[SCAN] {len(tickers)} tickers | SPY={SPY_RET:.2f}")

    for t in tickers:

        try:
            df = yf.download(t, period="1y", auto_adjust=True, progress=False)

            if df is None or df.empty:
                continue

            rs = calc_rs(df)
            vol = calc_vol_ratio(df)
            sigs = get_signals(df)

            if not sigs:
                continue

            for s in sigs:
                buckets[s].append((t, rs, vol))

            time.sleep(0.05)

        except:
            continue

    # =========================
    # OUTPUT
    # =========================
    msg = ""

    for cat in ["돌파", "눌림목", "골든크로스", "추세전환"]:

        msg += f"\n[{cat}]\n\n"

        items = buckets[cat]

        if not items:
            msg += "없음\n"
            continue

        for i, (t, rs, vol) in enumerate(items, 1):

            f = fmp_data.get(t, {})

            eps_yoy = f.get("eps_yoy", None)
            rev_yoy = f.get("rev_yoy", None)
            eps_fwd_yoy = f.get("eps_fwd_yoy", None)
            rev_fwd_yoy = f.get("rev_fwd_yoy", None)

            msg += (
                f"{i}. {t} | RS {rs:.1f} | VOL {vol:.1f}x\n"
                f"EPS YoY {eps_yoy} | EPS FWD YoY {eps_fwd_yoy}\n"
                f"REV YoY {rev_yoy} | REV FWD YoY {rev_fwd_yoy}\n\n"
            )

    print(msg)
    send_telegram(msg)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    scan()
