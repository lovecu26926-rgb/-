#!/usr/bin/env python3

import yfinance as yf
import pandas as pd
import requests
import time
import logging
import warnings
from datetime import datetime
import pytz

warnings.filterwarnings("ignore")

# =========================================================================
# [최종] 텔레그램 연동 정보 (토큰/아이디 확인 완료)
# =========================================================================
TELEGRAM_TOKEN = "8680217169:AAEsF1CloKbbVR40HxkoXtdZ6hLho9o1aGs"  
CHAT_ID = "6147329612"         

ST_PERIOD = 10
ST_MULTIPLIER = 3.0

MIN_PRICE = 1.0
MIN_DOLLAR_VOLUME = 20_000_000

MARKET_TZ = pytz.timezone("America/New_York")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# ==========================
# 텔레그램 전송 함수
# ==========================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=20
        )
    except Exception as e:
        logging.error(f"Telegram 전송 실패: {e}")

# ==========================
# 3대 지수 수집
# ==========================
def get_integrated_universe():
    tickers = set()
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # 1. S&P 500
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        table = pd.read_html(requests.get(url, headers=headers, timeout=15).text)[0]
        for sym in table['Symbol'].dropna():
            symbol = str(sym).strip().replace('.', '-')
            if symbol and not any(c in symbol for c in ['$', '.']): tickers.add(symbol)
    except: pass

    # 2. NASDAQ 100
    try:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        tables = pd.read_html(requests.get(url, headers=headers, timeout=15).text)
        for table in tables:
            if 'Ticker' in table.columns:
                for sym in table['Ticker'].dropna():
                    symbol = str(sym).strip()
                    if symbol and not any(c in symbol for c in ['$', '.']): tickers.add(symbol)
                break
    except: pass

    # 3. Russell 1000
    try:
        url = "https://en.wikipedia.org/wiki/Russell_1000_Index"
        tables = pd.read_html(requests.get(url, headers=headers, timeout=15).text)
        for table in tables:
            if 'Symbol' in table.columns:
                for sym in table['Symbol'].dropna():
                    symbol = str(sym).strip().replace('.', '-')
                    if symbol and not any(c in symbol for c in ['$', '.']): tickers.add(symbol)
    except: pass

    return sorted(list(tickers))

# ==========================
# 기술적 지표 연산
# ==========================
def calc_atr(high, low, close, period):
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()

def calc_supertrend(high, low, close, period=10, multiplier=3.0):
    df = pd.DataFrame({'High': high, 'Low': low, 'Close': close}).reset_index(drop=True)
    atr = calc_atr(df['High'], df['Low'], df['Close'], period)
    hl2 = (df['High'] + df['Low']) / 2
    upperband, lowerband = hl2 + multiplier * atr, hl2 - multiplier * atr
    final_upper, final_lower = upperband.copy(), lowerband.copy()
    direction = pd.Series(1, index=df.index, dtype="int64")
    for i in range(1, len(df)):
        if upperband.iloc[i] < final_upper.iloc[i - 1] or df['Close'].iloc[i - 1] > final_upper.iloc[i - 1]: final_upper.iloc[i] = upperband.iloc[i]
        else: final_upper.iloc[i] = final_upper.iloc[i - 1]
        if lowerband.iloc[i] > final_lower.iloc[i - 1] or df['Close'].iloc[i - 1] < final_lower.iloc[i - 1]: final_lower.iloc[i] = lowerband.iloc[i]
        else: final_lower.iloc[i] = final_lower.iloc[i - 1]
        direction.iloc[i] = 1 if df['Close'].iloc[i] > final_lower.iloc[i] else -1 if df['Close'].iloc[i] < final_upper.iloc[i] else direction.iloc[i - 1]
    return direction

# ==========================
# 스캔 엔진
# ==========================
def scan():
    now_et = datetime.now(MARKET_TZ)
    if now_et.weekday() >= 5: return

    universe = get_integrated_universe()
    buy_alerts = []
    chunk_size = 45 

    for i in range(0, len(universe), chunk_size):
        chunk = universe[i:i + chunk_size]
        data = yf.download(chunk, period="6mo", interval="1d", group_by="ticker", progress=False, threads=True)
        if data.empty: continue

        for ticker in chunk:
            try:
                hist = data[ticker].dropna(subset=["Close"])
                if len(hist) < 50: continue
                close_price = float(hist["Close"].iloc[-1])
                if close_price < MIN_PRICE: continue
                
                avg_dollar_volume = (hist["Close"].tail(20) * hist["Volume"].tail(20)).mean()
                if avg_dollar_volume < MIN_DOLLAR_VOLUME: continue

                direction = calc_supertrend(hist["High"], hist["Low"], hist["Close"], ST_PERIOD, ST_MULTIPLIER)
                if int(direction.iloc[-2]) == -1 and int(direction.iloc[-1]) == 1:
                    buy_alerts.append({"ticker": ticker, "price": close_price, "volume": avg_dollar_volume})
            except: continue
        time.sleep(0.5)

    date_str = now_et.strftime("%Y-%m-%d")

    # 🎯 매수 종목 없어도 알림 발송
    if not buy_alerts:
        send_telegram(f"📊 <b>[{date_str}]</b> 미국 주요 지수 중 오늘 매수 전환 종목 없음")
        return

    buy_alerts.sort(key=lambda x: x["volume"], reverse=True)
    lines = [f"<b>🎯 Supertrend Buy Signal [{date_str}]</b>", ""]
    for item in buy_alerts:
        lines.append(f"<b>{item['ticker']}</b>  ${item['price']:.2f} (대금: ${item['volume']/1_000_000:.1f}M)")
    send_telegram("\n".join(lines))

if __name__ == "__main__":
    scan()
