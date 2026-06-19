import os
import time
import json
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import date

# =========================
# CONFIG
# =========================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FMP_KEY = os.environ.get("FMP_API_KEY")

TREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"
SUPERTREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/supertrend_universe.csv"

FMP_CACHE = "fmp_cache.json"
SENT_FILE = "sent_signals.json"

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(msg)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg
    })

# =========================
# SENT CACHE
# =========================
def load_sent():
    if os.path.exists(SENT_FILE):
        return set(tuple(x) for x in json.load(open(SENT_FILE)))
    return set()

def save_sent(data):
    json.dump([list(x) for x in data], open(SENT_FILE, "w"))

# =========================
# FMP FUNDAMENTALS (CACHE 1 DAY)
# =========================
def get_fmp_data(ticker):
    today = str(date.today())

    if os.path.exists(FMP_CACHE):
        cache = json.load(open(FMP_CACHE))
    else:
        cache = {}

    if ticker in cache and cache[ticker]["date"] == today:
        return cache[ticker]["data"]

    try:
        url = f"https://financialmodelingprep.com/api/v3/key-metrics-ttm/{ticker}?apikey={FMP_KEY}"
        r = requests.get(url).json()[0]

        data = {
            "eps_growth": float(r.get("netIncomePerShareTTM", 0) or 0),
            "rev_growth": float(r.get("revenueGrowthTTM", 0) or 0),
            "roe": float(r.get("roeTTM", 0) or 0)
        }

        cache[ticker] = {"date": today, "data": data}
        json.dump(cache, open(FMP_CACHE, "w"))

        return data
    except:
        return {"eps_growth": 0, "rev_growth": 0, "roe": 0}

# =========================
# SCORE SYSTEM
# =========================
def growth_score(f):
    eps = f["eps_growth"]
    rev = f["rev_growth"]
    roe = f["roe"]

    return (
        min(max(eps, 0), 100) * 0.5 +
        min(max(rev, 0), 100) * 0.3 +
        min(max(roe, 0), 100) * 0.2
    )

def tech_score(signal_type):
    if "BREAKOUT" in signal_type:
        return 50
    if "PULLBACK" in signal_type:
        return 35
    return 40

# =========================
# TECH SIGNALS
# =========================
def check_signal(df):
    if len(df) < 50:
        return None

    close = df["Close"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()

    breakout = close.iloc[-1] > df["High"].rolling(20).max().iloc[-2]
    pullback = abs(close.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1] < 0.03

    if breakout:
        return "BREAKOUT"
    if ma20.iloc[-1] > ma50.iloc[-1] and pullback:
        return "PULLBACK"
    return None

# =========================
# SCAN ENGINE
# =========================
def scan(csv_url, name):
    tickers = pd.read_csv(csv_url)["Symbol"].dropna().tolist()
    results = []

    sent = load_sent()

    print(f"\n[{name}] SCAN START")

    for t in tickers:
        try:
            df = yf.download(t, period="3mo", interval="1d", progress=False)
            if df.empty:
                continue

            sig = check_signal(df)
            if not sig:
                continue

            key = (t, name, str(date.today()))
            if key in sent:
                continue

            price = df["Close"].iloc[-1]
            fmp = get_fmp_data(t)

            g_score = growth_score(fmp)
            t_score = tech_score(sig)

            total = round(g_score * 0.6 + t_score * 0.4, 2)

            results.append({
                "ticker": t,
                "price": price,
                "signal": sig,
                "growth": g_score,
                "tech": t_score,
                "total": total
            })

            sent.add(key)
            print(t, sig)

            time.sleep(0.2)

        except:
            continue

    save_sent(sent)

    results.sort(key=lambda x: x["total"], reverse=True)

    msg = f"\n🏆 {name} TOP\n\n"
    for i, r in enumerate(results[:20]):
        msg += f"{i+1}. {r['ticker']} {r['total']} (G:{r['growth']:.1f} T:{r['tech']})\n"

    send_telegram(msg)
    print("DONE")

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    print("RUNNING SCANNER")

    scan(TREND_CSV, "TREND")
    scan(SUPERTREND_CSV, "SUPERTREND")

    print("DONE")
