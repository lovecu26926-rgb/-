import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime
import pytz
import sys

# =========================
# ⛔ 실행 시간 제한 (KST 14~15)
# =========================
kst = pytz.timezone("Asia/Seoul")
now_kst = datetime.now(kst)

if not (14 <= now_kst.hour < 15):
    print("⛔ 실행 시간 아님")
    sys.exit()

# =========================
# 🔐 텔레그램 설정
# =========================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        for _ in range(2):
            r = requests.post(url, data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg[:4000],
                "parse_mode": "HTML"
            }, timeout=10)

            if r.status_code == 200:
                return
            time.sleep(2)
    except:
        pass

# =========================
# 📥 안전 다운로드
# =========================
def safe_download(ticker):
    try:
        df = yf.download(
            ticker,
            period="2y",
            auto_adjust=True,
            progress=False,
            threads=False
        )
        if df is None or df.empty:
            return None

        df = df[['Open','High','Low','Close']].dropna()
        if len(df) < 200:
            return None

        return df.astype(float)

    except:
        return None

# =========================
# 📊 SuperTrend
# =========================
def supertrend(df, period=10, mult=3):
    high = df["High"].values
    low = df["Low"].values
    close = df["Close"].values
    n = len(df)

    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]

    tr = np.maximum(high-low, np.maximum(abs(high-prev_close), abs(low-prev_close)))
    atr = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean().values

    hl2 = (high + low) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr

    fu = upper.copy()
    fl = lower.copy()
    trend = np.ones(n, dtype=bool)

    for i in range(1, n):
        fu[i] = min(upper[i], fu[i-1]) if close[i-1] <= fu[i-1] else upper[i]
        fl[i] = max(lower[i], fl[i-1]) if close[i-1] >= fl[i-1] else lower[i]

        if close[i] > fu[i-1]:
            trend[i] = True
        elif close[i] < fl[i-1]:
            trend[i] = False
        else:
            trend[i] = trend[i-1]

    return trend

# =========================
# 📈 신호
# =========================
def signal(df):
    if df is None or len(df) < 220:
        return "데이터 부족", "❌", ""

    ma20 = df['Close'].rolling(20).mean().iloc[-1]
    ma50 = df['Close'].rolling(50).mean().iloc[-1]
    ma200 = df['Close'].rolling(200).mean().iloc[-1]

    if ma20 > ma50 > ma200:
        status, emoji = "정배열", "✅"
    elif ma20 > ma50:
        status, emoji = "상승", "🟡"
    elif ma20 < ma50 < ma200:
        status, emoji = "역배열", "❌"
    else:
        status, emoji = "혼조", "⚪️"

    trend = supertrend(df)

    sig = ""
    if len(trend) > 2:
        if not trend[-2] and trend[-1]:
            sig = "🟢 상승전환"
        elif trend[-2] and trend[-1] is False:
            sig = "🔴 하락전환"

    return status, emoji, sig

# =========================
# 🌍 티커
# =========================
tickers = {
    "SPY": "S&P500",
    "QQQ": "NASDAQ",
    "DIA": "DOW",
    "IWM": "RUSSELL",

    "EWY": "KOREA",
    "^KS11": "KOSPI",

    "XLK": "TECH",
    "SMH": "SEMICON",
    "XLF": "FINANCE",

    "UUP": "USD",
    "JPY=X": "USDJPY",

    "GC=F": "GOLD",
    "BTC-USD": "BTC",

    "^TNX": "10Y",
    "^IRX": "2Y",
    "^VIX": "VIX"
}

# =========================
# 📊 수집
# =========================
def run():
    results = {}

    for t, name in tickers.items():
        df = safe_download(t)

        if df is None:
            results[t] = {"name": name, "error": True}
            continue

        try:
            price = df['Close'].iloc[-1]
            prev = df['Close'].iloc[-2]
            chg = (price / prev - 1) * 100

            st, em, sig = signal(df)

            results[t] = {
                "name": name,
                "price": price,
                "change": chg,
                "status": st,
                "emoji": em,
                "signal": sig
            }

        except:
            results[t] = {"name": name, "error": True}

        time.sleep(0.3)

    return results

# =========================
# 📱 출력
# =========================
def format_msg(res):
    msg = "🌍 <b>MARKET DASHBOARD</b>\n\n"

    for k in ["SPY","QQQ","DIA","IWM"]:
        r = res.get(k)
        if r and "error" not in r:
            msg += f"{r['name']}: {r['change']:+.2f}% [{r['emoji']}{r['status']}] {r['signal']}\n"

    msg += "\n📊 SECTOR\n"
    for k in ["XLK","SMH","XLF"]:
        r = res.get(k)
        if r and "error" not in r:
            msg += f"{r['name']}: {r['change']:+.2f}%\n"

    msg += "\n💱 FX\n"
    for k in ["UUP","JPY=X"]:
        r = res.get(k)
        if r and "error" not in r:
            msg += f"{r['name']}: {r['price']:.2f}\n"

    msg += "\n🪙 ASSETS\n"
    for k in ["GC=F","BTC-USD","^VIX"]:
        r = res.get(k)
        if r and "error" not in r:
            msg += f"{r['name']}: {r['price']:.2f}\n"

    return msg

# =========================
# 🚀 실행
# =========================
if __name__ == "__main__":
    res = run()
    msg = format_msg(res)
    send_telegram(msg)
    print("DONE")
