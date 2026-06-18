#!/usr/bin/env python3
"""
Supertrend Alert Bot - S&P500, NASDAQ100, Russell2000 전 종목 100% 자동 갱신 및 에러 차단 버전
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
MIN_ADR = 4.0        # 변동성 기준 4.0%로 설정
MIN_PERF_3M = 0.0
MIN_AVG_VOL_30D = 50_000_000  # 30일 평균 거래대금 ($)
MIN_TODAY_VOL = 20_000_000   # 오늘 거래대금 ($)

MARKET_TZ = pytz.timezone("America/New_York")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def get_live_universe():
    """S&P 500, NASDAQ 100, Russell 2000 전 종목을 웹에서 실시간으로 자동 크롤링합니다."""
    logging.info("최신 시장 유니버스(S&P500, 나스닥100, 러셀2000) 동적 수집 시작...")
    tickers = set()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # 1. S&P 500 자동 크롤링
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        response = requests.get(url, headers=headers, timeout=10)
        tables = pd.read_html(response.text)
        sp500 = tables[0]['Symbol'].tolist()
        tickers.update([t.replace('.', '-') for t in sp500])
        logging.info(f"S&P 500 수집 완료 (누적 종목 수: {len(tickers)}개)")
    except Exception as e:
        logging.error(f"S&P 500 수집 실패: {e}")

    # 2. NASDAQ 100 자동 크롤링
    try:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        response = requests.get(url, headers=headers, timeout=10)
        tables = pd.read_html(response.text)
        for df in tables:
            if 'Ticker' in df.columns:
                tickers.update(df['Ticker'].tolist())
                break
            elif 'Symbol' in df.columns:
                tickers.update(df['Symbol'].tolist())
                break
        logging.info(f"NASDAQ 100 수집 완료 (누적 종목 수: {len(tickers)}개)")
    except Exception as e:
        logging.error(f"NASDAQ 100 수집 실패: {e}")

    # 3. Russell 2000 자동 크롤링 (오픈소스 금융 가이드 저장소 연동)
    try:
        # 러셀 2000 전체 구성 종목을 실시간으로 추적하는 공인 데이터 소스 사용
        url = "https://raw.githubusercontent.com/mrgnprime/russell-2000-tickers/main/russell2000_tickers.csv"
        df_russell = pd.read_csv(url)
        if 'Ticker' in df_russell.columns:
            russell_list = df_russell['Ticker'].tolist()
        elif 'ticker' in df_russell.columns:
            russell_list = df_russell['ticker'].tolist()
        else:
            russell_list = df_russell.iloc[:, 0].tolist()
            
        # 야후 파이낸스 포맷에 맞게 점(.)을 대시(-)로 변환
        russell_clean = [str(t).strip().replace('.', '-').upper() for t in russell_list if t and not pd.isna(t)]
        tickers.update(russell_clean)
        logging.info(f"Russell 2000 실시간 수집 완료 (최종 통합 유니버스: {len(tickers)}개)")
    except Exception as e:
        logging.error(f"Russell 2000 수집 실패: {e}")

    final_list = [t.strip().upper() for t in tickers if t and isinstance(t, str) and '^' not in t]
    return sorted(list(set(final_list)))

def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calc_atr(high, low, close, period):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def calc_supertrend(high, low, close, period=10, multiplier=3.0):
    atr = calc_atr(high, low, close, period)
    hl2 = (high + low) / 2
    
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr
    
    upper = basic_upper.copy()
    lower = basic_lower.copy()
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
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
        logging.info("텔레그램 전송 성공" if r.status_code == 200 else f"오류: {r.text}")
    except Exception as e:
        logging.error(f"텔레그램 예외: {e}")

def scan():
    now_et = datetime.now(MARKET_TZ)
    logging.info(f"=== 전체 자동 갱신 스캔 시작 {now_et.strftime('%Y-%m-%d %H:%M ET')} ===")

    if now_et.weekday() >= 5:
        logging.info("주말 스킵")
        return

    # 100% 동적 수집된 유니버스 (S&P500 + 나스닥100 + 러셀2000 전체 약 2500개 이상)
    universe = get_live_universe()
    total_tickers = len(universe)
    
    if total_tickers == 0:
        logging.error("수집된 종목이 없습니다. 스캔을 종료합니다.")
        return

    logging.info(f"대상 종목 총 {total_tickers}개 에러 차단 분할 배치 다운로드 시작...")

    # 과부하 및 차단을 막기 위해 60개씩 안전하게 쪼개서 다운로드
    chunk_size = 60
    combined_data = pd.DataFrame()
    
    for i in range(0, total_tickers, chunk_size):
        chunk = universe[i:i + chunk_size]
        logging.info(f"진행 상황: {i}/{total_tickers} 묶음 다운로드 중...")
        try:
            # 주가 데이터 수집 (에러 종목이 섞여있어도 무시하고 통과하도록 셋업)
            raw_chunk = yf.download(chunk, period="1y", interval="1d", group_by="ticker", progress=False, threads=True)
            if not raw_chunk.empty:
                combined_data = pd.concat([combined_data, raw_chunk], axis=1)
        except Exception as e:
            logging.error(f"묶음 다운로드 중 오류 발생 (건너뜀): {e}")
        time.sleep(0.4) # 서버 보호를 위한 미세 마진

    buy_alerts = []

    # 전체 수집 데이터 순회 분석
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

            # ADR 변동성 계산
            adr = ((high.tail(5) - low.tail(5)) / low.tail(5) * 100).mean()
            if adr < MIN_ADR: continue

            # 3개월 수익률 필터
            idx_3m = max(0, len(close) - 63)
            past_3m = close.iloc[idx_3m]
            perf_3m = (price - past_3m) / past_3m * 100 if past_3m > 0 else -999
            if perf_3m < MIN_PERF_3M: continue

            # 이평선 정배열 조건
            ema8  = calc_ema(close, 8)
            ema21 = calc_ema(close, 21)
            ema60 = calc_ema(close, 60)
            if ema8.iloc[-1] <= ema21.iloc[-1]: continue
            if price <= ema60.iloc[-1]: continue

            # 거래대금 필터 (가격 * 거래량)
            avg_dv = (close.tail(30) * volume.tail(30)).mean()
            today_dv = price * volume.iloc[-1]
            if avg_dv < MIN_AVG_VOL_30D: continue
            if today_dv < MIN_TODAY_VOL: continue

            # 슈퍼트렌드 신호 계산
            direction = calc_supertrend(high, low, close, ST_PERIOD, ST_MULTIPLIER)
            if len(direction) < 2: continue

            curr = int(direction.iloc[-1])
            prev = int(direction.iloc[-2])
            
            # 신호 포착: 전일 하락(-1)에서 오늘 상승(1) 전환 시점
            if curr == 1 and prev == -1:
                buy_alerts.append({
                    "ticker": ticker,
                    "price": price,
                    "adr": round(adr, 1),
                    "perf_3m": round(perf_3m, 1),
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
            current_chunk.append(
                f"<b>{a['ticker']}</b>  ${a['price']:.2f}\n"
                f"🟢 슈퍼트렌드 상승 전환\n"
                f"ADR {a['adr']}% | 3M {a['perf_3m']}%\n"
            )
            if (i + 1) % 15 == 0:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
        
        if current_chunk:
            chunks.append("\n".join(current_chunk))
            
        for msg in chunks:
            send_telegram(msg)
            time.sleep(1)
    else:
        send_telegram(f"📊 [{date_str}] 오늘 조건 만족 종목 없음")

    logging.info(f"=== 스캔 완료. 매수 후보 총 {len(buy_alerts)}개 ===")

if __name__ == "__main__":
    scan()
