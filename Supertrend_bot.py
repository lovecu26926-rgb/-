#!/usr/bin/env python3

import yfinance as yf
import pandas as pd
import requests
import time
import logging
from datetime import datetime
import pytz
import io # 🎯 에러 방지를 위해 추가

# 설정
TELEGRAM_TOKEN = "8680217169:AAEsF1CloKbbVR40HxkoXtdZ6hLho9o1aGs"
CHAT_ID = "6147329612"
MARKET_TZ = pytz.timezone("America/New_York")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"})

def get_universe():
    # 에러 방지를 위해 헤더 추가
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        html = requests.get(url, headers=headers, timeout=20).text
        # 🎯 경고창 해결: StringIO 사용
        table = pd.read_html(io.StringIO(html))[0]
        return [s.replace('.', '-') for s in table['Symbol'].tolist()]
    except Exception as e:
        logging.error(f"데이터 수집 실패: {e}")
        return ["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "GOOGL"]

def scan():
    tickers = get_universe()
    buy_alerts = []
    
    # 30개씩 나눠서 분석 (종목이 적으면 바로 끝남)
    for i in range(0, len(tickers), 30):
        chunk = tickers[i:i+30]
        data = yf.download(chunk, period="3mo", group_by="ticker", progress=False, threads=True)
        # 데이터가 비어있으면 건너뜀
        if data.empty: continue
        
        for ticker in chunk:
            if ticker not in data.columns.levels[0]: continue
            hist = data[ticker].dropna()
            if len(hist) < 30: continue
            
            # 여기서 매수 로직이 들어가는데, 
            # 일단 메시지가 오는지 보려고 강제 메시지 발송 루틴을 넣습니다.
            if ticker == "AAPL": # 테스트용
                buy_alerts.append("테스트 종목(AAPL)")
    
    date_str = datetime.now(MARKET_TZ).strftime("%Y-%m-%d")
    msg = f"📊 [{date_str}] 스캔 완료. 포착된 종목 수: {len(buy_alerts)}개"
    send_telegram(msg)

if __name__ == "__main__":
    scan()
