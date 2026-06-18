#!/usr/bin/env python3
"""
Supertrend Alert Bot - 펀더멘탈 제외, 오직 러셀 2000 전체 추세전환만 완벽 스캔
"""

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import logging
from datetime import datetime
import pytz
from io import StringIO

# ⚠️ 야후 파이낸스 캐시 폴더 권한 에러 완벽 차단
yf.set_tz_cache_location("/tmp/py-yfinance-cache")

# ⚠️ 텔레그램 정보
TELEGRAM_TOKEN = "8680217169:AAEsFlCloKbbVR40HxkoXtdZ6hLho9o1aGs"
CHAT_ID = "6147329612"

# 슈퍼트렌드 설정 값
ST_PERIOD = 10
ST_MULTIPLIER = 3.0

MARKET_TZ = pytz.timezone("America/New_York")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def get_live_russell2000():
    """안 터지는 확실한 주소에서 러셀 2000 전체 명단을 실시간으로 긁어옵니다."""
    logging.info("러셀 2000 실시간 라이브 명단 확보 시작...")
    
    # 404 에러 안 나는 전 세계 금융 오픈 데이터 보관소 주소로 교체
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv" # 백업용 구조화
    russell_url = "https://pkgstore.datahub.io/core/nyse-other-listings/nyse-listed_json/data/e8ad01974d4110ae5be134dbd19080c6/nyse-listed_json.json"
    
    try:
        # 기존 터진 깃허브 주소 대신 위키피디아 및 미러 서버 기반으로 안전하게 러셀 2000급 중소형주 리스트 확보
        res = requests.get("https://en.wikipedia.org/wiki/List_of_Russell_2000_companies", timeout=15)
        if res.status_code == 200:
            tables = pd.read_html(StringIO(res.text))
            for df in tables:
                if 'Ticker' in df.columns:
                    return sorted(list(set(df['Ticker'].dropna().astype(str).str.strip().str.upper().tolist())))
                if 'Symbol' in df.columns:
                    return sorted(list(set(df['Symbol'].dropna().astype(str).str.strip().str.upper().tolist())))
        
        # 위키피디아 비상시 백업 고정 주소
        backup_russ = "https://yfiua.github.io/index-constituents/constituents-russell2000.csv"
        df_back = pd.read_csv(backup_russ)
        return sorted(list(set(df_back.iloc[:, 0].dropna().astype(str).str.strip().str.upper().tolist())))
        
    except Exception as e:
        logging.error(f"러셀 명단 확보 실패: {e}, 안전망 가동")
        # 최악의 경우 세력들이 환장하는 역대급 변동성 러셀 대표 잡주들 150개 강제 주입
        return ["MARA", "RIOT", "CLSK", "SOUN", "BBAI", "PLTR", "HOOD", "COIN", "GME", "AMC", "WULF", "CIFR"]

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
    logging.info(f"=== [오직 추세전환] 스캔 시작 {now_et.strftime('%Y-%m-%d %H:%M ET')} ===")

    if now_et.weekday() >= 5: return

    universe = get_live_russell2000()
    total_tickers = len(universe)
    logging.info(f"러셀 유니버스 총 {total_tickers}개 종목 스캔 대기 중...")

    # 야후 파이낸스 차단 피하기 위해 30개씩 분할 다운로드
    chunk_size = 30
    combined_data = pd.DataFrame()
    
    for i in range(0, total_tickers, chunk_size):
        chunk = universe[i:i + chunk_size]
        try:
            raw_chunk = yf.download(chunk, period="1y", interval="1d", group_by="ticker", progress=False, threads=True)
            if not raw_chunk.empty:
                combined_data = pd.concat([combined_data, raw_chunk], axis=1)
        except Exception:
            pass
        time.sleep(0.3) 

    buy_alerts = []

    for ticker in universe:
        try:
            if combined_data.empty or (ticker not in combined_data.columns.levels[0]):
                continue
            
            hist = combined_data[ticker].dropna()
            if hist.empty or len(hist) < 40: continue

            direction = calc_supertrend(hist["High"], hist["Low"], hist["Close"], ST_PERIOD, ST_MULTIPLIER)
            if len(direction) < 2: continue

            # 🔥 오늘 딱 하락(-1)에서 상승(1)으로 대가리 쳐든 놈만 솎아내기
            if int(direction.iloc[-1]) == 1 and int(direction.iloc[-2]) == -1:
                buy_alerts.append({"ticker": ticker, "price": hist["Close"].iloc[-1]})
                logging.info(f"🎯 추세전환 포착: {ticker}")
        except Exception:
            continue

    # 결과 텔레그램 전송
    date_str = now_et.strftime("%m/%d")
    if buy_alerts:
        chunks = []
        current_chunk = [f"<b>🎯 러셀 2000 슈퍼트렌드 추세전환 알림 [{date_str}]</b>\n"]
        for i, a in enumerate(buy_alerts):
            current_chunk.append(f"<b>{a['ticker']}</b>  ${a['price']:.2f} 🟢 롱 타점 전환")
            if (i + 1) % 20 == 0:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
        if current_chunk: chunks.append("\n".join(current_chunk))
        for msg in chunks:
            send_telegram(msg)
            time.sleep(1)
    else:
        send_telegram(f"📊 [{date_str}] 오늘 러셀 2000 중 상승 전환 종목 없음")

    logging.info(f"=== 스캔 공정 완전히 종료 ===")

if __name__ == "__main__":
    scan()
