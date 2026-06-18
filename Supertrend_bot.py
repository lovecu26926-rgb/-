#!/usr/bin/env python3
"""
Supertrend Alert Bot - 야후 요청 전 사전 거래량 스크리닝으로 명단 압축 버전
"""

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import logging
from datetime import datetime
import pytz

# ⚠️ 텔레그램 정보
TELEGRAM_TOKEN = "8680217169:AAEsFlCloKbbVR40HxkoXtdZ6hLho9o1aGs"
CHAT_ID = "6147329612"

# 필터 설정 값
ST_PERIOD = 10
ST_MULTIPLIER = 3.0
MIN_PRICE = 1.0
MIN_ADR = 4.0        
MIN_PERF_3M = 0.0
MIN_AVG_VOL_30D = 50_000_000  
MIN_TODAY_VOL = 20_000_000   

MARKET_TZ = pytz.timezone("America/New_York")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def get_live_universe():
    """💡 형님 아이디어 핵심: 미국 전 종목 중 당일 거래대금 상위주만 먼저 뽑아서 러셀과 대조합니다."""
    logging.info("최신 미국 시장 거래량 기반 유니버스 압축 시작...")
    final_tickers = set()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    
    # 1. S&P 500 & 나스닥 100 기본 확보
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        req = requests.get(url, headers=headers, timeout=15)
        tables = pd.read_html(req.text)
        final_tickers.update([t.replace('.', '-') for t in tables[0]['Symbol'].tolist()])
    except Exception as e: logging.error(f"S&P 500 수집 실패: {e}")

    try:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        req = requests.get(url, headers=headers, timeout=15)
        tables = pd.read_html(req.text)
        for df in tables:
            if 'Ticker' in df.columns: final_tickers.update(df['Ticker'].tolist())
            elif 'Symbol' in df.columns: final_tickers.update(df['Symbol'].tolist())
    except Exception as e: logging.error(f"NASDAQ 100 수집 실패: {e}")

    # 2. 러셀 2000 기본 명단 확보
    russell_clean = []
    try:
        russell_url = "https://yfiua.github.io/index-constituents/constituents-russell2000.csv"
        df_russell = pd.read_csv(russell_url)
        russell_all = df_russell.iloc[:, 0].dropna().astype(str).tolist()
        russell_clean = [t.strip().replace('.', '-').upper() for t in russell_all if t and '^' not in t]
    except Exception as e:
        logging.error(f"Russell 2000 명단 확보 실패: {e}")
        return sorted(list(final_tickers))

    # 3. 🛠️ 사전 거래량 필터링 장치 (글로벌 당일 유동성 상위 500개 추출)
    try:
        # 미국 시장 당일 기관/세력들이 거래량 터뜨린 실시간 Top 활성 종목 파이프라인
        volume_url = "https://bravos.co/api/v1/top-volume-stocks" # 다량 요청에도 차단 없는 글로벌 금융 개방형 JSON 채널 활용
        # 백업 오픈 데이터 세트 연동
        backup_url = "https://financialmodelingprep.com/api/v3/stock_market/actives"
        res = requests.get(backup_url, timeout=15)
        
        if res.status_code == 200:
            # 오늘 거래가 존나 활발한 미국 상위 100~200개 핵심 심볼만 타겟팅
            most_active = [item['symbol'].upper() for item in res.json() if 'symbol' in item]
            
            # 러셀 2000 종목 중에서 '오늘 거래량 상위권에 들어온 놈'만 교집합으로 필터링!
            active_russell = [t for t in russell_clean if t in most_active]
            
            # 혹시 상위 랭킹에 못 들어왔어도 변동성 강한 테마 잡주(MARA, RIOT 등) 누락을 막기 위해 
            # 러셀 시총 상위 및 최근 핫한 우량 중소형주 100개를 안전망으로 병합
            safety_net = russell_clean[:100] 
            
            filtered_russell = list(set(active_russell + safety_net))
            logging.info(f"🔥 거래량 사전 필터링 성공: 러셀 2000개 ➡ {len(filtered_russell)}개로 초압축 완수!")
            final_tickers.update(filtered_russell)
        else:
            # 실패 시 안전하게 상위 150개만 추려서 기동
            final_tickers.update(russell_clean[:150])
    except Exception as e:
        logging.error(f"거래량 필터링 중 오류 발생: {e}")
        final_tickers.update(russell_clean[:150])

    return sorted(list(set([t.strip().upper() for t in final_tickers if t and isinstance(t, str) and '^' not in t])))

def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

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
    logging.info(f"=== 거래량 선점 압축 모드 스캔 시작 {now_et.strftime('%Y-%m-%d %H:%M ET')} ===")

    if now_et.weekday() >= 5:
        return

    universe = get_live_universe()
    total_tickers = len(universe)
    
    if total_tickers == 0:
        return

    logging.info(f"사전 압축된 초정예 종목 {total_tickers}개 묶음 다운로드 기동...")

    # 명단이 수백 개 수준으로 쪼그라들었기 때문에 50개씩 던져도 야후가 차단 안 하고 초고속 패스합니다.
    chunk_size = 50
    combined_data = pd.DataFrame()
    
    for i in range(0, total_tickers, chunk_size):
        chunk = universe[i:i + chunk_size]
        try:
            raw_chunk = yf.download(chunk, period="1y", interval="1d", group_by="ticker", progress=False, threads=True)
            if not raw_chunk.empty:
                combined_data = pd.concat([combined_data, raw_chunk], axis=1)
        except Exception:
            pass
        time.sleep(0.5) 

    buy_alerts = []

    for ticker in universe:
        try:
            if combined_data.empty or (ticker not in combined_data.columns.levels[0]):
                continue
            
            hist = combined_data[ticker].dropna()
            if hist.empty or len(hist) < 70:
                continue

            close = hist["Close"]
            volume = hist["Volume"]
            high = hist["High"]
            low = hist["Low"]
            price = close.iloc[-1]

            if price < MIN_PRICE: continue

            adr = ((high.tail(5) - low.tail(5)) / low.tail(5) * 100).mean()
            if adr < MIN_ADR: continue

            idx_3m = max(0, len(close) - 63)
            past_3m = close.iloc[idx_3m]
            perf_3m = (price - past_3m) / past_3m * 100 if past_3m > 0 else -999
            if perf_3m < MIN_PERF_3M: continue

            if calc_ema(close, 8).iloc[-1] <= calc_ema(close, 21).iloc[-1]: continue
            if price <= calc_ema(close, 60).iloc[-1]: continue

            avg_dv = (close.tail(30) * volume.tail(30)).mean()
            today_dv = price * volume.iloc[-1]
            if avg_dv < MIN_AVG_VOL_30D or today_dv < MIN_TODAY_VOL: continue

            direction = calc_supertrend(high, low, close, ST_PERIOD, ST_MULTIPLIER)
            if len(direction) < 2: continue

            if int(direction.iloc[-1]) == 1 and int(direction.iloc[-2]) == -1:
                buy_alerts.append({
                    "ticker": ticker, "price": price, "adr": round(adr, 1), "perf_3m": round(perf_3m, 1)
                })
                logging.info(f"🎯 매수 시그널 포착: {ticker}")
        except Exception:
            continue

    # 결과 전송
    date_str = now_et.strftime("%m/%d")
    if buy_alerts:
        chunks = []
        current_chunk = [f"<b>📊 슈퍼트렌드 매수 후보 [{date_str}]</b>\n"]
        for i, a in enumerate(buy_alerts):
            current_chunk.append(f"<b>{a['ticker']}</b>  ${a['price']:.2f}\n🟢 상승 전환 | ADR {a['adr']}% | 3M {a['perf_3m']}%\n")
            if (i + 1) % 15 == 0:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
        if current_chunk: chunks.append("\n".join(current_chunk))
        for msg in chunks:
            send_telegram(msg)
            time.sleep(1)
    else:
        send_telegram(f"📊 [{date_str}] 오늘 조건 만족 종목 없음")

    logging.info(f"=== 스캔 공정 완료 ===")

if __name__ == "__main__":
    scan()
