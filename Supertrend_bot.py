#!/usr/bin/env python3

import yfinance as yf
import pandas as pd
import requests
import time
import logging
from datetime import datetime
import pytz

# 설정 정보
TELEGRAM_TOKEN = "8680217169:AAEsF1CloKbbVR40HxkoXtdZ6hLho9o1aGs"
CHAT_ID = "6147329612"

ST_PERIOD = 10
ST_MULTIPLIER = 3.0
MIN_PRICE = 1.0
MIN_DOLLAR_VOLUME = 20_000_000
MARKET_TZ = pytz.timezone("America/New_York")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"})

def get_universe():
    # 주요 지수 티커 리스트
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        table = pd.read_html(requests.get(url, timeout=10).text)[0]
        return [s.replace('.', '-') for s in table['Symbol'].tolist()]
    except: return ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"]

def calc_supertrend(hist):
    atr = (hist['High'] - hist['Low']).rolling(ST_PERIOD).mean()
    hl2 = (hist['High'] + hist['Low']) / 2
    upper = hl2 + ST_MULTIPLIER * atr
    lower = hl2 - ST_MULTIPLIER * atr
    direction = pd.Series(1, index=hist.index)
    for i in range(1, len(hist)):
        if hist['Close'].iloc[i] > lower.iloc[i-1]: direction.iloc[i] = 1
        elif hist['Close'].iloc[i] < upper.iloc[i-1]: direction.iloc[i] = -1
        else: direction.iloc[i] = direction.iloc[i-1]
    return direction

def scan():
    tickers = get_universe()
    buy_alerts = []
    
    for i in range(0, len(tickers), 30):
        chunk = tickers[i:i+30]
        try:
            data = yf.download(chunk, period="3mo", group_by="ticker", progress=False, threads=True)
            for ticker in chunk:
                if ticker not in data.columns.levels[0]: continue
                hist = data[ticker].dropna()
                if len(hist) < 30: continue
                vol = hist['Volume'].tail(20).mean() * hist['Close'].tail(20).mean()
                if vol < MIN_DOLLAR_VOLUME: continue
                direction = calc_supertrend(hist)
                if direction.iloc[-2] == -1 and direction.iloc[-1] == 1:
                    buy_alerts.append(f"<b>{ticker}</b> (${hist['Close'].iloc[-1]:.2f})")
        except: continue
        time.sleep(0.5)

    # 결과 전송 (종목 있든 없든 무조건)
    date_str = datetime.now(MARKET_TZ).strftime("%Y-%m-%d")
    if not buy_alerts:
        send_telegram(f"📊 [{date_str}] 금일 매수 신호 포착된 종목 없음")
    else:
        msg = f"🎯 <b>[{date_str}] 매수 신호 포착 목록</b>\n\n" + "\n".join(buy_alerts)
        send_telegram(msg)

if __name__ == "__main__":
    scan()
