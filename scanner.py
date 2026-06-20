import os
import time
import json
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
import pytz

# ==================== ENV ====================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FMP_API_KEY = os.environ.get("FMP_API_KEY")

TREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"
SUPERTREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/supertrend_universe.csv"
FMP_CACHE = "fundamentals.json"

# ==================== LOG ====================
def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

# ==================== SAFE SCALAR ====================
def s(x):
    try:
        return float(x)
    except:
        return 0.0

# ==================== TELEGRAM ====================
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
        log(f"Telegram error: {e}")

# ==================== FMP ====================
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
    except Exception as e:
        log(f"FMP error {ticker}: {e}")

    return {"rev_growth": 0, "eps_growth": 0}


def get_fmp(ticker):
    if os.path.exists(FMP_CACHE):
        with open(FMP_CACHE, "r") as f:
            data = json.load(f)
        return data.get(ticker, {"rev_growth": 0, "eps_growth": 0})
    return {"rev_growth": 0, "eps_growth": 0}


def score_growth(f):
    return f["rev_growth"] * 0.4 + f["eps_growth"] * 0.6

# ==================== TECH SAFE ====================
def score_trend(df):
    close = df["Close"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    high20 = df["High"].rolling(20).max().shift(1)

    if len(df) < 60:
        return 0, None

    c = s(close.iloc[-1])
    m20 = s(ma20.iloc[-1])
    m50 = s(ma50.iloc[-1])
    h20 = s(high20.iloc[-1])

    score = 0
    sig = []

    if c >= h20 * 0.98:
        score += 60
        sig.append("BREAKOUT")

    if m20 > m50:
        score += 50
        sig.append("UPTREND")

    if m20 != 0 and abs(c - m20) / m20 < 0.02:
        score += 40
        sig.append("PULLBACK")

    return score, sig if sig else None


def score_supertrend(df):
    if len(df) < 30:
        return 0, None

    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    atr = (high - low).rolling(14).mean()
    mid = (high + low) / 2
    upper = mid + 3 * atr
    lower = mid - 3 * atr

    trend = [1]

    for i in range(1, len(df)):
        c = s(close.iloc[i])
        u = s(upper.iloc[i-1])
        l = s(lower.iloc[i-1])

        if c > u:
            trend.append(1)
        elif c < l:
            trend.append(-1)
        else:
            trend.append(trend[-1])

    if len(trend) >= 2 and trend[-2] <= 0 and trend[-1] == 1:
        return 50, "BUY_FLIP"

    return 0, None

# ==================== SCAN SAFE ====================
def scan(url, name, limit):
    tickers = pd.read_csv(url)["Symbol"].dropna().str.upper().tolist()
    results = []

    log(f"[{name}] start tickers={len(tickers)}")

    for t in tickers:
        try:
            df = yf.download(
                t,
                period="3mo",
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=False
            )

            if df is None or df.empty:
                log(f"[SKIP EMPTY] {t}")
                continue

            df = df.dropna()

            if name == "TREND":
                tech, sig = score_trend(df)
            else:
                tech, sig = score_supertrend(df)

            if not sig:
                continue

            log(f"[SIGNAL] {t} {sig}")

            f = get_fmp(t)
            g = score_growth(f)

            if name == "TREND":
                final_score = tech * 0.7 + g * 0.3
            else:
                final_score = tech * 0.3 + g * 0.7

            results.append((t, final_score, g, tech, sig))

            time.sleep(0.12)

        except Exception as e:
            log(f"[ERROR] {t} {e}")

    results.sort(key=lambda x: x[1], reverse=True)
    top = results[:limit]

    if not top:
        log(f"[{name}] NO SIGNALS")
        return

    msg = f"[{name}] TOP {len(top)}\n\n"

    for i, (t, final_score, g, tech, sig) in enumerate(top, 1):
        sig_str = " + ".join(sig) if isinstance(sig, list) else sig
        msg += f"{i}. {t} | {final_score:.1f} (성장 {g:.1f} + 기술 {tech:.1f}) | {sig_str}\n"

    send_telegram(msg)

# ==================== RUN ====================
def run():
    now = datetime.now(pytz.timezone("Asia/Seoul"))
    hour = now.hour

    trend = pd.read_csv(TREND_CSV)["Symbol"].dropna().str.upper().tolist()
    supert = pd.read_csv(SUPERTREND_CSV)["Symbol"].dropna().str.upper().tolist()

    all_tickers = list(set(trend + supert))

    if hour == 14:
        log("FMP CACHE UPDATE START")
        cache = {}

        for t in all_tickers:
            cache[t] = fetch_from_fmp(t)
            time.sleep(0.25)

        with open(FMP_CACHE, "w") as f:
            json.dump(cache, f)

        log("FMP CACHE SAVED")

    scan(TREND_CSV, "TREND", 20)
    scan(SUPERTREND_CSV, "SUPERTREND", 10)

if __name__ == "__main__":
    run()
