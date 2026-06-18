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

# ==========================
# 설정 (토큰과 ID를 입력하세요)
# ==========================
TELEGRAM_TOKEN = "YOUR_NEW_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

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
# 3대 지수 수집 (위키피디아 통합 - 버그 수정 완료)
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
            # 파이썬 기본 replace 문법으로 수정 (.str.replace가 아님)
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
                    # 파이썬 기본 replace 문법으로 수정
                    symbol = str(sym).strip().replace('.', '-')
                    if symbol and not any(c in symbol for c in ['$', '.']):
                        tickers.add(symbol)
        logging.info(f"Russell 1000 수집 완료 (중복제거 최종 합계: {len(tickers)}개)")
    except Exception as e:
        logging.error(f"Russell 1000 위키 수집 에러: {e}")

    return sorted(list(tickers))

# ==========================
# 기술적 지표 연산
# ==========================
def calc_atr(high, low, close, period):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()

def calc_supertrend(high, low, close, period=10, multiplier=3.0):
    df = pd.DataFrame({'High': high, 'Low': low, 'Close': close}).reset_index(drop=True)
    
    atr = calc_atr(df['High'], df['Low'], df['Close'], period)
    hl2 = (df['High'] + df['Low']) / 2

    upperband = hl2 + multiplier * atr
    lowerband = hl2 - multiplier * atr

    final_upper = upperband.copy()
    final_lower = lowerband.copy()
    direction = pd.Series(1, index=df.index, dtype="int64")

    for i in range(1, len(df)):
        if upperband.iloc[i] < final_upper.iloc[i - 1] or df['Close'].iloc[i - 1] > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = upperband.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]

        if lowerband.iloc[i] > final_lower.iloc[i - 1] or df['Close'].iloc[i - 1] < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = lowerband.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]

        if direction.iloc[i - 1] == 1:
            direction.iloc[i] = 1 if df['Close'].iloc[i] > final_lower.iloc[i] else -1
        else:
            direction.iloc[i] = -1 if df['Close'].iloc[i] < final_upper.iloc[i] else 1

    direction.index = close.index
    return direction

# ==========================
# 코어 스캔 엔진
# ==========================
def scan():
    now_et = datetime.now(MARKET_TZ)
    if now_et.weekday() >= 5:
        logging.info("주말이므로 스캔을 패스합니다.")
        return

    universe = get_integrated_universe()
    if not universe:
        logging.error("스캔할 종목 리스트가 비어있습니다. 종료합니다.")
        return

    buy_alerts = []
    chunk_size = 45 

    for i in range(0, len(universe), chunk_size):
        chunk = universe[i:i + chunk_size]
        logging.info(f"데이터 다운로드 중: {i + 1} ~ {min(i + chunk_size, len(universe))} / {len(universe)}")

        try:
            data = yf.download(
                chunk,
                period="6mo",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=True
            )
        except Exception as e:
            logging.error(f"yf.download 실패 (Chunk {i}): {e}")
            continue

        if data.empty:
            continue

        for ticker in chunk:
            try:
                if len(chunk) == 1:
                    hist = data.dropna(subset=["Close"])
                else:
                    if ticker not in data.columns.levels[1]:
                        continue
                    hist = data.xs(ticker, level=1, axis=1).dropna(subset=["Close"])

                if len(hist) < 50:
                    continue

                close_price = float(hist["Close"].iloc[-1])

                # [조건 1] 주가 필터
                if close_price < MIN_PRICE:
                    continue

                # [조건 2] 거래대금 필터 (20일 평균 2천만 달러)
                avg_dollar_volume = (hist["Close"].tail(20) * hist["Volume"].tail(20)).mean()
                if avg_dollar_volume < MIN_DOLLAR_VOLUME:
                    continue

                # [조건 3] Supertrend 연산
                direction = calc_supertrend(
                    hist["High"],
                    hist["Low"],
                    hist["Close"],
                    ST_PERIOD,
                    ST_MULTIPLIER
                )

                # [조건 4] 당일 매수 전환 신호 체크
                if int(direction.iloc[-2]) == -1 and int(direction.iloc[-1]) == 1:
                    buy_alerts.append({
                        "ticker": ticker,
                        "price": close_price,
                        "volume": avg_dollar_volume
                    })

            except Exception:
                continue

        time.sleep(0.25)

    # 결과 정렬 및 전송
    buy_alerts.sort(key=lambda x: x["volume"], reverse=True)
    date_str = now_et.strftime("%Y-%m-%d")

    if not buy_alerts:
        send_telegram(f"📊 <b>[{date_str}]</b> 미국 주요 지수 중 오늘 매수 전환 종목 없음")
        return

    lines = [
        f"<b>🎯 Supertrend Buy Signal [{date_str}]</b>",
        f"<i>필터: 주요 지수 우량주 (대금 > ${MIN_DOLLAR_VOLUME/1_000_000:.0f}M)</i>",
        ""
    ]

    for item in buy_alerts:
        lines.append(f"<b>{item['ticker']}</b>  ${item['price']:.2f} (대금: ${item['volume']/1_000_000:.1f}M)")

    lines.append("")
    lines.append(f"총 <b>{len(buy_alerts)}</b> 개 종목 포착")

    send_telegram("\n".join(lines))

if __name__ == "__main__":
    scan()
