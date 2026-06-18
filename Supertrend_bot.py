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
# [설정 완료] 텔레그램 연동 정보 (아이디 및 토큰 자동 세팅)
# =========================================================================
TELEGRAM_TOKEN = "7483920174:AAH_xdfa8273"  # <-- 아까 보내주신 토큰 값 적용!
CHAT_ID = "6147329612"         # <-- 질문자님 챗아이디 적용!

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
# 3대 지수 수집 (위키피디아 통합)
# ==========================
def get_integrated_universe():
    tickers = set()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    # 1. S&P 500
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        req = requests.get(url, headers=headers, timeout=15)
        table = pd.read_html(req.text)[0]
        for sym in table['Symbol'].dropna():
            symbol = str(sym).strip().replace('.', '-')
            if symbol and not any(c in symbol for c in ['$', '.']):
                tickers.add(symbol)
        logging.info(f"S&P 500 수집 완료 (누적: {len(tickers)}개)")
    except Exception as e:
        logging.error(f"S&P 500 위키 수집 에러: {e}")

    # 2. NASDAQ 100
    try:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        req = requests.get(url, headers=headers, timeout=15)
        tables = pd.read_html(req.text)
        for table in tables:
            if 'Ticker' in table.columns:
                for sym in table['Ticker'].dropna():
                    symbol = str(sym).strip()
                    if symbol and not any(c in symbol for c in ['$', '.']):
                        tickers.add(symbol)
                break
        logging.info(f"NASDAQ 100 수집 완료 (누적: {len(tickers)}개)")
    except Exception as e:
        logging.error(f"NASDAQ 100 위키 수집 에러: {e}")

    # 3. Russell 1000
    try:
        url = "https://en.wikipedia.org/wiki/Russell_1000_Index"
        req = requests.get(url, headers=headers, timeout=15)
        tables = pd.read_html(req.text)
        for table in tables:
            if 'Symbol' in table.columns:
                for sym in table['Symbol'].dropna():
                    symbol = str(sym).strip().replace('.', '-')
                    if symbol and not any(c in symbol for c in ['$', '.']):
                        tickers.add(symbol)
        logging.info(f"Russell 1000 수집 완료 (중복제거 최종 합계: {len(tickers)}개)")
    except Exception as e:
        logging.error(f"Russell 1000 위키 수집 에러: {e}")

    return sorted(list(tickers))

# =
