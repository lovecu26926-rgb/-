import os
import time
import json
import requests
import pandas as pd
import yfinance as yf
from datetime import date

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

TREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"
SUPERTREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/supertrend_universe.csv"

FMP_CACHE = "fundamentals.json"
SENT_FILE = "sent_signals.json"

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(msg)
        return
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
        timeout=10
    )

def load_sent():
    if os.path.exists(SENT_FILE):
        with open(SENT_FILE, "r") as f:
            return set(tuple(x) for x in json.load(f))
    return set()

def save_sent(s):
    with open(SENT_FILE, "w") as f:
        json.dump([list(x) for x in s], f)

def get_fmp(ticker):
    if os.path.exists(FMP_CACHE):
        with open(FMP_CACHE, "r") as f:
            data = json.load(f)
    else:
        data = {}
    return data.get(ticker, {"eps_growth": 0, "rev_growth": 0, "roe": 0})

def score_growth(f):
    eps = f.get("eps_growth", 0)
    rev = f.get("rev_growth", 0)
    roe = f.get("roe", 0)
    return eps * 0.5 + rev * 0.4 + roe * 0.1

def tech_score(df):
    close = df["Close"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    high20 = df["High"].rolling(20).max().shift(1)

    if close.iloc[-1] > high20.iloc[-1]:
        return 60, "BREAKOUT"
    if ma20.iloc[-1] > ma50.iloc[-1]:
        return 40, "PULLBACK"
    return 30, None

def scan(url, name, limit):
    tickers = pd.read_csv(url)["Symbol"].dropna().str.upper().tolist()

    sent = load_sent()
    today = str(date.today())

    results = []

    for t in tickers:
        try:
            df = yf.download(t, period="3mo", interval="1d", auto_adjust=True, progress=False)
            if df.empty:
                continue

            tech, sig = tech_score(df)
            if not sig:
                continue

            key = (t, name, today)
            if key in sent:
                continue

            f = get_fmp(t)
            g = score_growth(f)

            total = g + tech

            results.append((t, total, g, tech))

            sent.add(key)

            time.sleep(0.2)

        except:
            continue

    save_sent(sent)

    results.sort(key=lambda x: x[1], reverse=True)

    top = results[:limit]

    msg = f"[{name}] TOP {len(top)}\n\n"
    for i, r in enumerate(top, 1):
        msg += f"{i}. {r[0]} | {r[1]:.1f}\n"

    send_telegram(msg)

def run():
    scan(TREND_CSV, "TREND", 10)
    scan(SUPERTREND_CSV, "SUPERTREND", 30)

if __name__ == "__main__":
    run()
