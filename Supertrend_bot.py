#!/usr/bin/env python3
"""
Supertrend Alert Bot
- 대상: S&P500 + NASDAQ100 + Russell 2000 전종목
- 조건: 가격>$1, ADR>4%, 3/6/12개월 퍼포먼스>0%, EMA8>EMA21, 가격>EMA60,
        거래대금 30일평균>50M, 당일거래대금>20M, EPS희석성장률TTM YoY>20%
- 슈퍼트렌드(10, 3.0) 일봉 플립 시 텔레그램 알람
- 매일 미장 마감 후 1회 실행 (ET 16:30)
"""

import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import time
import logging
import schedule
from datetime import datetime
import pytz

# ──────────────────────────────────────────
# 설정
# ──────────────────────────────────────────
TELEGRAM_TOKEN = "8680217169:AAEsFlCloKbbVR40HxkoXtdZ6hLho9o1aGs"
CHAT_ID = "6147329612"

ST_PERIOD = 10
ST_MULTIPLIER = 3.0

MIN_PRICE = 1.0
MIN_ADR = 4.0
MIN_PERF_3M = 0.0
MIN_PERF_6M = 0.0
MIN_PERF_1Y = 0.0
MIN_AVG_VOL_30D = 50_000_000
MIN_TODAY_VOL = 20_000_000
MIN_EPS_GROWTH = 20.0

MARKET_TZ = pytz.timezone("America/New_York")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("supertrend_bot.log"),
        logging.StreamHandler()
    ]
)

# ──────────────────────────────────────────
# 유니버스: S&P500 + NASDAQ100 + Russell 2000
# ──────────────────────────────────────────
def get_universe():
    tickers = set()

    # S&P500
    try:
        sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
        tickers.update(sp500["Symbol"].str.replace(".", "-").tolist())
        logging.info(f"S&P500: {len(tickers)}개")
    except Exception as e:
        logging.warning(f"S&P500 실패: {e}")

    # NASDAQ100
    try:
        ndx = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")[4]
        tickers.update(ndx["Ticker"].tolist())
        logging.info(f"NDX100 추가 후: {len(tickers)}개")
    except Exception as e:
        logging.warning(f"NDX100 실패: {e}")

    # Russell 2000 (iShares ETF 구성종목 CSV)
    try:
        url = "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
        df = pd.read_csv(url, skiprows=9)
        df = df[df["Asset Class"] == "Equity"]
        r2k = df["Ticker"].dropna().str.strip().tolist()
        tickers.update(r2k)
        logging.info(f"Russell2000 추가 후: {len(tickers)}개")
    except Exception as e:
        logging.warning(f"Russell2000 실패: {e}")

    return list(tickers)


# ──────────────────────────────────────────
# 텔레그램 전송
# ──────────────────────────────────────────
def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            logging.info("텔레그램 전송 성공")
        else:
            logging.error(f"텔레그램 오류: {r.text}")
    except Exception as e:
        logging.error(f"텔레그램 예외: {e}")


# ──────────────────────────────────────────
# 슈퍼트렌드 계산
# ──────────────────────────────────────────
def calc_supertrend(df):
    st = ta.supertrend(df["High"], df["Low"], df["Close"],
                       length=ST_PERIOD, multiplier=ST_MULTIPLIER)
    if st is None or st.empty:
        return None, None
    dir_col = [c for c in st.columns if c.startswith("SUPERTd")]
    if not dir_col:
        return None, None
    directions = st[dir_col[0]].dropna()
    if len(directions) < 2:
        return None, None
    return int(directions.iloc[-1]), int(directions.iloc[-2])


# ──────────────────────────────────────────
# 단일 종목 체크
# ──────────────────────────────────────────
def check_ticker(ticker):
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="1y", interval="1d")
        if hist is None or len(hist) < 70:
            return None

        close = hist["Close"]
        volume = hist["Volume"]
        price = close.iloc[-1]

        if price < MIN_PRICE:
            return None

        # ADR
        recent = hist.tail(5)
        adr = ((recent["High"] - recent["Low"]) / recent["Low"] * 100).mean()
        if adr < MIN_ADR:
            return None

        # 퍼포먼스
        def perf(days):
            idx = max(0, len(close) - days)
            past = close.iloc[idx]
            return (price - past) / past * 100 if past > 0 else -999

        if perf(63) < MIN_PERF_3M: return None
        if perf(126) < MIN_PERF_6M: return None
        if perf(252) < MIN_PERF_1Y: return None

        # EMA 정배열
        ema8  = ta.ema(close, length=8)
        ema21 = ta.ema(close, length=21)
        ema60 = ta.ema(close, length=60)
        if ema8 is None or ema21 is None or ema60 is None: return None
        if ema8.iloc[-1] <= ema21.iloc[-1]: return None
        if price <= ema60.iloc[-1]: return None

        # 거래대금
        avg_dv = (close.tail(30) * volume.tail(30)).mean()
        today_dv = price * volume.iloc[-1]
        if avg_dv < MIN_AVG_VOL_30D: return None
        if today_dv < MIN_TODAY_VOL: return None

        # EPS 성장률
        info = tk.info
        eps_g = info.get("earningsQuarterlyGrowth") or info.get("earningsGrowth")
        if eps_g is None or eps_g * 100 < MIN_EPS_GROWTH: return None

        # 슈퍼트렌드 플립 (상승 전환만)
        curr_dir, prev_dir = calc_supertrend(hist)
        if curr_dir is None: return None
        if curr_dir == prev_dir: return None
        if curr_dir != 1: return None  # 상승 전환만

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


# ──────────────────────────────────────────
# 메인 스캔
# ──────────────────────────────────────────
def scan():
    now_et = datetime.now(MARKET_TZ)
    logging.info(f"=== 스캔 시작 {now_et.strftime('%Y-%m-%d %H:%M ET')} ===")

    # 주말 스킵
    if now_et.weekday() >= 5:
        logging.info("주말 — 스킵")
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


# ──────────────────────────────────────────
# 스케줄러 - 매일 ET 16:30 (미장 마감 30분 후)
# ──────────────────────────────────────────
def main():
    send_telegram("🤖 슈퍼트렌드 봇 시작!\n대상: S&P500 + NASDAQ100 + Russell2000\n⏰ 매일 미장 마감 후 스캔 (한국 새벽 5:30)")

    # ET 16:30 = 한국 05:30 (서머타임 기준)
    schedule.every().day.at("21:30").do(scan)  # UTC 21:30 = ET 16:30 (서머타임)

    # 테스트: 바로 한 번 실행하려면 아래 주석 해제
    # scan()

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
