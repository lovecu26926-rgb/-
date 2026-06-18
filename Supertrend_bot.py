#!/usr/bin/env python3

import yfinance as yf
import pandas as pd
import requests
import time
import logging
from datetime import datetime
import pytz

# =========================================================================
# 설정 정보 (봇파더에게 받은 진짜 토큰 적용 완료)
# =========================================================================
TELEGRAM_TOKEN = "8680217169:AAEsF1CloKbbVR40HxkoXtdZ6hLho9o1aGs"  
CHAT_ID = "6147329612"         

ST_PERIOD = 10
ST_MULTIPLIER = 3.0
MIN_PRICE = 1.0
MIN_DOLLAR_VOLUME = 20_000_000
MARKET_TZ = pytz.timezone("America/New_York")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        res = requests.post(
            url,
            json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=20
        )
        if res.status_code == 200:
            logging.info("텔레그램 발송 성공")
        else:
            logging.error(f"텔레그램 발송 실패 (코드: {res.status_code}): {res.text}")
    except Exception as e:
        logging.error(f"전송 네트워크 에러: {e}")

def get_universe():
    # S&P500 + NASDAQ100 기본 리스트 (에러 최소화)
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        table = pd.read_html(requests.get(url, timeout=10).text)[0]
        tickers = table['Symbol'].tolist()
        return [s.replace('.', '-') for s in tickers]
    except: return ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"] # 에러시 최소 종목

def calc_supertrend(hist):
    # 기술적 지표 계산 로직 (간소화)
    atr = (hist['High'] - hist['Low']).rolling(ST_PERIOD).mean()
    hl2 = (hist['High'] + hist['Low']) / 2
