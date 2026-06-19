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

# 🔥 수정: fmp_cache.json → fundamentals.json
FMP_CACHE = "fundamentals.json"
SENT_FILE = "sent_signals.json"

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(msg)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown"
        }, timeout=10)
    except:
        pass

# =========================
# SENT CACHE
# =========================
def load_sent():
    if os.path.exists(SENT_FILE):
        try:
            with open(SENT_FILE, "r") as f:
                return set(tuple(x) for x in json.load(f))
        except:
            return set()
    return set()

def save_sent(data):
    with open(SENT_FILE, "w") as f:
        json.dump([list(x) for x in data], f)

# =========================
# 🔥 FMP FUNDAMENTALS (fundamentals.json 읽기)
# =========================
def get_fmp_data(ticker):
    cache = {}
    if os.path.exists(FMP_CACHE):
        try:
            with open(FMP_CACHE, "r") as f:
                cache = json.load(f)
        except:
            cache = {}
    return cache.get(ticker, {"eps_growth": 0, "rev_growth": 0, "roe": 0})

# =========================
# SCORE SYSTEM
# =========================
def growth_score(f):
    eps = f.get("eps_growth", 0)
    rev = f.get("rev_growth", 0)
    roe = f.get("roe", 0)

    eps_scaled = min(max(eps, 0), 100)
    rev_scaled = min(max(rev, 0), 100)
    roe_scaled = min(max(roe, 0), 100)

    return (eps_scaled * 0.5 + rev_scaled * 0.3 + roe_scaled * 0.2)

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

    high20 = df["High"].rolling(20).max().shift(1)
    breakout = close.iloc[-1] > high20.iloc[-1]

    pullback = ma20.iloc[-1] > ma50.iloc[-1] and abs(close.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1] < 0.03

    if breakout:
        return "BREAKOUT"
    if pullback:
        return "PULLBACK"
    return None

# =========================
# SCAN ENGINE
# =========================
def scan(csv_url, name):
    try:
        df_csv = pd.read_csv(csv_url)
        tickers = df_csv["Symbol"].dropna().astype(str).str.strip().str.upper().tolist()
    except Exception as e:
        print(f"CSV 오류 {name}: {e}")
        return

    results = []
    sent = load_sent()
    today = str(date.today())
    print(f"\n🔥 [{name}] 스캔 시작 (종목수: {len(tickers)})")

    for t in tickers:
        try:
            df = yf.download(t, period="3mo", interval="1d", auto_adjust=True, progress=False)
            if df.empty:
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs(t, axis=1, level=1)

            sig = check_signal(df)
            if not sig:
                continue

            key = (t, name, today)
            if key in sent:
                continue

            price = float(df["Close"].iloc[-1])
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
            print(f"  ✅ {t} {sig} (G:{g_score:.0f} T:{t_score:.0f} 합:{total:.1f})")

            time.sleep(0.2)

        except Exception as e:
            print(f"  ⚠️ {t} 에러: {e}")
            continue

    save_sent(sent)

    results.sort(key=lambda x: x["total"], reverse=True)

    if not results:
        send_telegram(f"🏆 [{name}] 오늘 신호 없음")
        return

    msg = f"🏆 *[{name}] TOP {min(20, len(results))}*\n\n"
    for i, r in enumerate(results[:20], 1):
        msg += (
            f"{i}. *{r['ticker']}* 总分 {r['total']:.1f}\n"
            f"   성장 {r['growth']:.0f} | 기술 {r['tech']:.0f} | ${r['price']:.2f}\n\n"
        )

    send_telegram(msg)
    print(f"✅ [{name}] 완료 ({len(results)}개 발견)")

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 스캐너 실행 (FMP 연동 완료)")
    print("=" * 50)

    scan(TREND_CSV, "TREND")
    scan(SUPERTREND_CSV, "SUPERTREND")

    print("\n✅ 모든 스캔 완료")
