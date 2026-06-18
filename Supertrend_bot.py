#!/usr/bin/env python3
"""
Supertrend Alert Bot - pandas-ta 없이 직접 계산
"""

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import logging
from datetime import datetime
import pytz

TELEGRAM_TOKEN = "8680217169:AAEsFlCloKbbVR40HxkoXtdZ6hLho9o1aGs"
CHAT_ID = "6147329612"

ST_PERIOD = 10
ST_MULTIPLIER = 3.0
MIN_PRICE = 1.0
MIN_ADR = 5.0
MIN_PERF_3M = 0.0
MIN_PERF_6M = 0.0
MIN_PERF_1Y = 0.0
MIN_AVG_VOL_30D = 50_000_000
MIN_TODAY_VOL = 20_000_000
MIN_EPS_GROWTH = 20.0

MARKET_TZ = pytz.timezone("America/New_York")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

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
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr

    supertrend = pd.Series(index=close.index, dtype=float)
    direction = pd.Series(index=close.index, dtype=int)

    for i in range(1, len(close)):
        # 상단밴드
        if upper.iloc[i] < upper.iloc[i-1] or close.iloc[i-1] > upper.iloc[i-1]:
            upper.iloc[i] = upper.iloc[i]
        else:
            upper.iloc[i] = upper.iloc[i-1]

        # 하단밴드
        if lower.iloc[i] > lower.iloc[i-1] or close.iloc[i-1] < lower.iloc[i-1]:
            lower.iloc[i] = lower.iloc[i]
        else:
            lower.iloc[i] = lower.iloc[i-1]

        # 방향
        if i == 1:
            direction.iloc[i] = 1
        elif supertrend.iloc[i-1] == upper.iloc[i-1]:
            direction.iloc[i] = -1 if close.iloc[i] > upper.iloc[i] else 1
        else:
            direction.iloc[i] = 1 if close.iloc[i] < lower.iloc[i] else -1

        supertrend.iloc[i] = lower.iloc[i] if direction.iloc[i] == -1 else upper.iloc[i]

    return direction

def get_universe():
    tickers = set()
    try:
        sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
        tickers.update(sp500["Symbol"].str.replace(".", "-").tolist())
        logging.info(f"S&P500: {len(tickers)}개")
    except Exception as e:
        logging.warning(f"S&P500 실패: {e}")
    try:
        ndx = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")[4]
        tickers.update(ndx["Ticker"].tolist())
        logging.info(f"NDX100 추가 후: {len(tickers)}개")
    except Exception as e:
        logging.warning(f"NDX100 실패: {e}")
    try:
        url = "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
        df = pd.read_csv(url, skiprows=9)
        df = df[df["Asset Class"] == "Equity"]
        tickers.update(df["Ticker"].dropna().str.strip().tolist())
        logging.info(f"Russell2000 추가 후: {len(tickers)}개")
    except Exception as e:
        logging.warning(f"Russell2000 실패: {e}")
    return list(tickers)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
        logging.info("텔레그램 전송 성공" if r.status_code == 200 else f"오류: {r.text}")
    except Exception as e:
        logging.error(f"텔레그램 예외: {e}")

def check_ticker(ticker):
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="1y", interval="1d")
        if hist is None or len(hist) < 70:
            return None

        close = hist["Close"]
        volume = hist["Volume"]
        high = hist["High"]
        low = hist["Low"]
        price = close.iloc[-1]

        if price < MIN_PRICE:
            return None

        adr = ((high.tail(5) - low.tail(5)) / low.tail(5) * 100).mean()
        if adr < MIN_ADR:
            return None

        def perf(days):
            idx = max(0, len(close) - days)
            past = close.iloc[idx]
            return (price - past) / past * 100 if past > 0 else -999

        if perf(63) < MIN_PERF_3M: return None
        if perf(126) < MIN_PERF_6M: return None
        if perf(252) < MIN_PERF_1Y: return None

        ema8  = calc_ema(close, 8)
        ema21 = calc_ema(close, 21)
        ema60 = calc_ema(close, 60)
        if ema8.iloc[-1] <= ema21.iloc[-1]: return None
        if price <= ema60.iloc[-1]: return None

        avg_dv = (close.tail(30) * volume.tail(30)).mean()
        today_dv = price * volume.iloc[-1]
        if avg_dv < MIN_AVG_VOL_30D: return None
        if today_dv < MIN_TODAY_VOL: return None

        info = tk.info
        eps_g = info.get("earningsQuarterlyGrowth") or info.get("earningsGrowth")
        if eps_g is None or eps_g * 100 < MIN_EPS_GROWTH: return None

        direction = calc_supertrend(high, low, close, ST_PERIOD, ST_MULTIPLIER)
        direction = direction.dropna()
        if len(direction) < 2: return None

        curr = int(direction.iloc[-1])
        prev = int(direction.iloc[-2])
        if curr == prev: return None
        if curr != -1: return None  # -1 = 상승 (하단밴드 = 지지)

        return {
            "ticker": ticker,
            "price": price,
            "adr": round(adr, 1),
            "eps_growth": round(eps_g * 100, 1),
            "perf_3m": round(perf(63), 1),
        }

    except Exception as e:
        logging.debug(f"{ticker} 오류: {e}")
        return None

def scan():
    now_et = datetime.now(MARKET_TZ)
    logging.info(f"=== 스캔 시작 {now_et.strftime('%Y-%m-%d %H:%M ET')} ===")

    if now_et.weekday() >= 5:
        logging.info("주말 스킵")
        return

    universe = get_universe()
    logging.info(f"총 {len(universe)}개 종목 스캔")

    buy_alerts = []
    for i, ticker in enumerate(universe):
        result = check_ticker(ticker)
        if result:
            buy_alerts.append(result)
            logging.info(f"매수 후보: {ticker}")
        if i % 100 == 0:
            logging.info(f"진행: {i}/{len(universe)}")
        time.sleep(0.1)

    date_str = now_et.strftime("%m/%d")
    if buy_alerts:
        lines = [f"<b>📊 슈퍼트렌드 매수 후보 [{date_str}]</b>\n"]
        for a in buy_alerts:
            lines.append(
                f"<b>{a['ticker']}</b>  ${a['price']:.2f}\n"
                f"🟢 상승 전환\n"
                f"ADR {a['adr']}%  EPS {a['eps_growth']}%  3M {a['perf_3m']}%\n"
            )
        send_telegram("\n".join(lines))
    else:
        send_telegram(f"📊 [{date_str}] 오늘 매수 후보 없음")

    logging.info(f"=== 완료. 매수 후보 {len(buy_alerts)}개 ===")

if __name__ == "__main__":
    scan()
