import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import time
from datetime import date
import warnings
warnings.filterwarnings("ignore")

# =========================
# CONFIG
# =========================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FMP_API_KEY = os.environ.get("FMP_API_KEY")

TREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"
SUPERTREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/supertrend_universe.csv"

FMP_CACHE = "fmp_cache.json"


# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(msg)
        return
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
    )


# =========================
# FMP (1회/일)
# =========================
def load_cache():
    if os.path.exists(FMP_CACHE):
        return json.load(open(FMP_CACHE, "r"))
    return {}

def save_cache(data):
    json.dump(data, open(FMP_CACHE, "w"))

def update_fmp(tickers):
    data = {}

    for t in tickers:
        try:
            url = f"https://financialmodelingprep.com/api/v3/key-metrics-ttm/{t}?apikey={FMP_API_KEY}"
            r = requests.get(url).json()

            if isinstance(r, list) and len(r) > 0:
                d = r[0]
                data[t] = {
                    "eps": float(d.get("netIncomePerShareTTM", 0) or 0),
                    "rev": float(d.get("revenueGrowth", 0) or 0),
                    "margin": float(d.get("netProfitMarginTTM", 0) or 0)
                }
        except:
            continue

    save_cache(data)
    return data


# =========================
# SCORE
# =========================
def growth_score(eps, rev, margin):
    return (eps * 0.5) + (rev * 0.3) + (margin * 0.2)

def tech_score(mode):
    if mode == "BREAKOUT":
        return 70
    if mode == "PULLBACK":
        return 50
    if mode == "SUPERTREND":
        return 60
    return 40


# =========================
# SUPER TREND
# =========================
def supertrend(df):
    high, low, close = df["High"], df["Low"], df["Close"]
    atr = (high - low).rolling(10).mean()

    upper = (high + low)/2 + 3 * atr
    lower = (high + low)/2 - 3 * atr

    trend = [True]

    for i in range(1, len(df)):
        if close[i] > upper[i-1]:
            trend.append(True)
        elif close[i] < lower[i-1]:
            trend.append(False)
        else:
            trend.append(trend[-1])

    df["trend"] = trend
    return df


# =========================
# SIGNALS (3개 분리)
# =========================
def signals(df):
    close = df["Close"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()

    breakout = close.iloc[-1] > close.rolling(20).max().iloc[-2]
    pullback = abs(close.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1] < 0.03

    sigs = []

    if breakout:
        sigs.append("BREAKOUT")
    if ma20.iloc[-1] > ma50.iloc[-1] and pullback:
        sigs.append("PULLBACK")

    df = supertrend(df)
    if df["trend"].iloc[-1] and not df["trend"].iloc[-2]:
        sigs.append("SUPERTREND")

    return sigs


# =========================
# LOAD
# =========================
def load_tickers():
    df = pd.read_csv(TREND_CSV)
    return list(df["Symbol"].dropna().unique())


# =========================
# MAIN
# =========================
def run():
    print("RUNNING SCANNER")

    tickers = load_tickers()
    fmp = load_cache()

    if not fmp:
        fmp = update_fmp(tickers)

    results = []

    for t in tickers:
        try:
            df = yf.download(t, period="3mo", interval="1d", progress=False)
            if df.empty:
                continue

            sigs = signals(df)
            if not sigs:
                continue

            price = df["Close"].iloc[-1]
            f = fmp.get(t, {"eps":0,"rev":0,"margin":0})

            g = growth_score(f["eps"], f["rev"], f["margin"])

            tech = max([tech_score(s) for s in sigs])
            total = g * 0.6 + tech * 0.4

            results.append({
                "t": t,
                "p": price,
                "g": g,
                "tech": tech,
                "total": total,
                "sig": ",".join(sigs)
            })

        except:
            continue

    results = sorted(results, key=lambda x: x["total"], reverse=True)

    msg = "🏆 TOP 20\n\n"

    for i, r in enumerate(results[:20]):
        msg += f"{i+1}. {r['t']} {r['total']:.1f} (G{r['g']:.1f}/T{r['tech']:.1f}) {r['sig']}\n"

    send_telegram(msg)
    print("DONE")


# =========================
# RUN
# =========================
if __name__ == "__main__":
    run()
