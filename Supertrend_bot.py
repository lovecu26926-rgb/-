#!/usr/bin/env python3
"""
Supertrend Alert Bot - 오직 매수 타점만 포착하여 텔레그램 전송
"""

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import logging
import warnings
from datetime import datetime
import pytz

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
yf.set_tz_cache_location("/tmp/py-yfinance-cache")

TELEGRAM_TOKEN = "8680217169:AAEsFlCloKbbVR40HxkoXtdZ6hLho9o1aGs"
CHAT_ID = "6147329612"

# 🛑 형님 차트와 완벽 일치하는 세팅값 (10, 3)
ST_PERIOD = 10
ST_MULTIPLIER = 3.0

MARKET_TZ = pytz.timezone("America/New_York")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def get_total_universe():
    """S&P 500 + 나스닥 100 + 러셀 2000 거래량 상위 주도주 취합"""
    tickers = set()
    
    # 1. S&P 500
    try:
        sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
        tickers.update(sp500['Symbol'].dropna().str.replace('.', '-').str.upper().tolist())
    except Exception: pass

    # 2. NASDAQ 100
    try:
        nasdaq100 = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")[4]
        if 'Ticker' in nasdaq100.columns:
            tickers.update(nasdaq100['Ticker'].dropna().str.upper().tolist())
        elif 'Symbol' in nasdaq100.columns:
            tickers.update(nasdaq100['Symbol'].dropna().str.upper().tolist())
    except Exception: pass

    # 3. 러셀 2000 중 가장 핫하고 거래량 터지는 핵심 주도주 40개
    russell_hot = [
        "MARA", "RIOT", "CLSK", "WULF", "CIFR", "IREN", "HUT", "BITF", "CORZ", "COIN",
        "SOUN", "BBAI", "PLTR", "HOOD", "GME", "AMC", "DKNG", "CELH", "RBLX", "NVAX",
        "AFRM", "UPST", "SOFI", "LCID", "RIVN", "OPEN", "COSM", "CVNA", "AI", "IONQ",
        "SERV", "LUNR", "OKLO", "NNE", "SMR", "ASTS", "VKTX", "ALT", "CRBU", "ACHR"
    ]
    tickers.update(russell_hot)
    
    return sorted([t for t in tickers if t and '^' not in t])

def calc_atr(high, low, close, period):
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def calc_supertrend(high, low, close, period=10, multiplier=3.0):
    atr = calc_atr(high, low, close, period)
    hl2 = (high + low) / 2
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr
    upper, lower = basic_upper.copy(), basic_lower.copy()
    direction = pd.Series(0, index=close.index)
    
    for i in range(1, len(close)):
        upper.iloc[i] = basic_upper.iloc[i] if basic_upper.iloc[i] < upper.iloc[i-1] or close.iloc[i-1] > upper.iloc[i-1] else upper.iloc[i-1]
        lower.iloc[i] = basic_lower.iloc[i] if basic_lower.iloc[i] > lower.iloc[i-1] or close.iloc[i-1] < lower.iloc[i-1] else lower.iloc[i-1]
        if direction.iloc[i-1] == 1:
            direction.iloc[i] = 1 if close.iloc[i] > lower.iloc[i] else -1
        else:
            direction.iloc[i] = -1 if close.iloc[i] < upper.iloc[i] else 1
    return direction

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
    except Exception: pass

def scan():
    now_et = datetime.now(MARKET_TZ)
    logging.info(f"=== 스캔 시작 {now_et.strftime('%Y-%m-%d %H:%M ET')} ===")

    if now_et.weekday() >= 5: return

    universe = get_total_universe()
    total_tickers = len(universe)
    
    chunk_size = 40
    combined_data = pd.DataFrame()
    
    for i in range(0, total_tickers, chunk_size):
        chunk = universe[i:i + chunk_size]
        try:
            raw_chunk = yf.download(chunk, period="1y", interval="1d", group_by="ticker", progress=False, threads=True)
            if not raw_chunk.empty:
                combined_data = pd.concat([combined_data, raw_chunk], axis=1)
        except Exception: pass
        time.sleep(0.1) 

    buy_alerts = []

    for ticker in universe:
        try:
            if combined_data.empty or (ticker not in combined_data.columns.levels[0]): continue
            
            hist = combined_data[ticker].dropna()
            if hist.empty or len(hist) < 20: continue

            direction = calc_supertrend(hist["High"], hist["Low"], hist["Close"], ST_PERIOD, ST_MULTIPLIER)
            
            # 🛑 오직 매수(하락정리 후 오늘 딱 롱 전환된 종목)만 수집
            if int(direction.iloc[-1]) == 1 and int(direction.iloc[-2]) == -1:
                buy_alerts.append({"ticker": ticker, "price": hist["Close"].iloc[-1]})
        except Exception: continue

    # 결과 전송
    date_str = now_et.strftime("%m/%d")
    if buy_alerts:
        chunks = []
        current_chunk = [f"<b>🎯 슈퍼트렌드 매수 신호 발생 [{date_str}]</b>\n"]
        for i, a in enumerate(buy_alerts):
            current_chunk.append(f"<b>{a['ticker']}</b>  ${a['price']:.2f} 🟢 매수 타점")
            if (i + 1) % 20 == 0:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
        if current_chunk: chunks.append("\n".join(current_chunk))
        for msg in chunks:
            send_telegram(msg)
            time.sleep(1)
    else:
        send_telegram(f"📊 [{date_str}] 오늘 매수 전환 종목 없음")

    logging.info("=== 스캔 완료 ===")

if __name__ == "__main__":
    scan()
