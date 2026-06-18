import pandas as pd
import numpy as np
import yfinance as yf
import time
import requests
from datetime import datetime
import pytz

# =========================
# 🔐 텔레그램 설정
# =========================
TOKEN = "8680217169"
CHAT_ID = "6147329612"

def send_msg(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})


# =========================
# 📡 유니버스 (NYSE + NASDAQ)
# =========================
def get_universe():
    nasdaq = pd.read_csv(
        "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt",
        sep="|"
    )
    nyse = pd.read_csv(
        "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
        sep="|"
    )

    nasdaq = nasdaq[nasdaq["Test Issue"] == "N"]
    nyse = nyse[nyse["Test Issue"] == "N"]

    tickers = set()
    tickers.update(nasdaq["Symbol"].dropna())
    tickers.update(nyse["ACT Symbol"].dropna())

    return list(tickers)


# =========================
# 💰 유동성 필터
# =========================
def liquidity_filter(df):
    price = df["Close"].iloc[-1]
    if price < 1:
        return False

    dollar_vol = (df["Close"] * df["Volume"]).rolling(20).mean().iloc[-1]

    if pd.isna(dollar_vol):
        return False

    return dollar_vol >= 20_000_000


# =========================
# 📊 ADR 4 필터
# =========================
def adr_filter(df, threshold=4):
    adr = ((df["High"] - df["Low"]) / df["Close"]) * 100
    avg_adr = adr.rolling(20).mean().iloc[-1]

    if pd.isna(avg_adr):
        return False

    return avg_adr >= threshold


# =========================
# 📈 Supertrend
# =========================
def supertrend(df, period=10, mult=3):
    high, low, close = df["High"], df["Low"], df["Close"]

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1/period, adjust=False).mean()

    hl2 = (high + low) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr

    trend = [False] * len(df)
    trend[0] = True

    for i in range(1, len(df)):
        if close.iloc[i] > upper.iloc[i - 1]:
            trend[i] = True
        elif close.iloc[i] < lower.iloc[i - 1]:
            trend[i] = False
        else:
            trend[i] = trend[i - 1]

    df["trend"] = trend
    return df


# =========================
# 🔍 스캔 엔진
# =========================
def scan():
    tickers = get_universe()
    signals = []

    for t in tickers:
        try:
            df = yf.download(t, period="6mo", interval="1d", progress=False)
            df = df.dropna()

            if len(df) < 50:
                continue

            if not liquidity_filter(df):
                continue

            if not adr_filter(df, 4):
                continue

            df = supertrend(df)

            # 하락 → 상승 전환
            if df["trend"].iloc[-2] == False and df["trend"].iloc[-1] == True:
                signals.append(t)

        except:
            continue

        time.sleep(0.15)

    return signals


# =========================
# ⏰ 미국시간 스케줄
# =========================
def is_trigger_time():
    ny = pytz.timezone("America/New_York")
    now = datetime.now(ny)

    # 14:00 ET → KST 04:00
    if now.hour == 14 and now.minute < 3:
        return True

    # 00:00 ET → KST 14:00
    if now.hour == 0 and now.minute < 3:
        return True

    return False


# =========================
# 🚀 자동사냥 루프
# =========================
send_msg("🔥 AUTO HUNT BOT STARTED")

last_run = None

while True:

    if is_trigger_time():

        if last_run != datetime.now().hour:

            send_msg("🚀 SCAN STARTED")

            result = scan()

            if result:
                msg = "🔥 BUY SIGNALS\n" + "\n".join(result)
            else:
                msg = "❌ NO TRADE SETUP"

            send_msg(msg)

            last_run = datetime.now().hour

    time.sleep(30)
