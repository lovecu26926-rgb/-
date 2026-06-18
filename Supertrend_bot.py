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
# 설정
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
# 텔레그램
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
        logging.error(e)

# ==========================
# 종목 수집
# ==========================

def get_total_universe():

    tickers = set()

    try:
        nasdaq = pd.read_csv(
            "https://ftp.nasdaqtrader.com/SymbolDirectory/nasdaqlisted.txt",
            sep="|"
        )

        for _, row in nasdaq.iterrows():

            symbol = str(row["Symbol"]).strip()

            if symbol == "File Creation Time":
                continue

            if "." in symbol:
                continue

            if "$" in symbol:
                continue

            tickers.add(symbol)

    except Exception as e:
        logging.error(f"NASDAQ ERROR: {e}")

    try:
        other = pd.read_csv(
            "https://ftp.nasdaqtrader.com/SymbolDirectory/otherlisted.txt",
            sep="|"
        )

        for _, row in other.iterrows():

            symbol = str(row["ACT Symbol"]).strip()

            if symbol == "File Creation Time":
                continue

            if "." in symbol:
                continue

            if "$" in symbol:
                continue

            tickers.add(symbol)

    except Exception as e:
        logging.error(f"OTHER ERROR: {e}")

    tickers = sorted(list(tickers))

    logging.info(f"TOTAL SYMBOLS: {len(tickers)}")

    return tickers

# ==========================
# ATR (TradingView 스타일)
# ==========================

def calc_atr(high, low, close, period):

    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ],
        axis=1
    ).max(axis=1)

    atr = tr.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    return atr

# ==========================
# Supertrend
# ==========================

def calc_supertrend(
    high,
    low,
    close,
    period=10,
    multiplier=3.0
):

    atr = calc_atr(
        high,
        low,
        close,
        period
    )

    hl2 = (high + low) / 2

    upperband = hl2 + multiplier * atr
    lowerband = hl2 - multiplier * atr

    final_upper = upperband.copy()
    final_lower = lowerband.copy()

    direction = pd.Series(
        index=close.index,
        dtype="int64"
    )

    direction.iloc[0] = 1

    for i in range(1, len(close)):

        if (
            upperband.iloc[i] < final_upper.iloc[i - 1]
            or close.iloc[i - 1] > final_upper.iloc[i - 1]
        ):
            final_upper.iloc[i] = upperband.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]

        if (
            lowerband.iloc[i] > final_lower.iloc[i - 1]
            or close.iloc[i - 1] < final_lower.iloc[i - 1]
        ):
            final_lower.iloc[i] = lowerband.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]

        if direction.iloc[i - 1] == 1:

            direction.iloc[i] = (
                1
                if close.iloc[i] > final_lower.iloc[i]
                else -1
            )

        else:

            direction.iloc[i] = (
                -1
                if close.iloc[i] < final_upper.iloc[i]
                else 1
            )

    return direction

# ==========================
# 스캔
# ==========================

def scan():

    now_et = datetime.now(MARKET_TZ)

    if now_et.weekday() >= 5:
        return

    universe = get_total_universe()

    buy_alerts = []

    chunk_size = 50

    for i in range(0, len(universe), chunk_size):

        chunk = universe[i:i + chunk_size]

        logging.info(
            f"{i + 1} ~ {min(i + chunk_size, len(universe))}"
        )

        try:

            data = yf.download(
                chunk,
                period="6mo",
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True
            )

        except Exception:
            continue

        if data.empty:
            continue

        for ticker in chunk:

            try:

                if ticker not in data.columns.levels[0]:
                    continue

                hist = data[ticker].dropna()

                if len(hist) < 50:
                    continue

                close_price = float(
                    hist["Close"].iloc[-1]
                )

                # 주가 1달러 이상

                if close_price < MIN_PRICE:
                    continue

                # 거래대금 필터

                avg_dollar_volume = (
                    hist["Close"].tail(20)
                    * hist["Volume"].tail(20)
                ).mean()

                if avg_dollar_volume < MIN_DOLLAR_VOLUME:
                    continue

                direction = calc_supertrend(
                    hist["High"],
                    hist["Low"],
                    hist["Close"],
                    ST_PERIOD,
                    ST_MULTIPLIER
                )

                # 어제 Sell → 오늘 Buy

                if (
                    int(direction.iloc[-2]) == -1
                    and
                    int(direction.iloc[-1]) == 1
                ):

                    buy_alerts.append(
                        {
                            "ticker": ticker,
                            "price": close_price,
                            "volume": avg_dollar_volume
                        }
                    )

            except Exception:
                continue

        time.sleep(0.2)

    # 거래대금 순 정렬

    buy_alerts.sort(
        key=lambda x: x["volume"],
        reverse=True
    )

    date_str = now_et.strftime("%Y-%m-%d")

    if not buy_alerts:

        send_telegram(
            f"📊 [{date_str}] Supertrend 매수 전환 종목 없음"
        )

        return

    lines = [
        f"<b>🎯 Supertrend Buy Signal [{date_str}]</b>",
        ""
    ]

    for item in buy_alerts:

        lines.append(
            f"<b>{item['ticker']}</b>  ${item['price']:.2f}"
        )

    lines.append("")
    lines.append(
        f"총 {len(buy_alerts)} 종목"
    )

    send_telegram(
        "\n".join(lines)
    )

# ==========================
# 실행
# ==========================

if __name__ == "__main__":
    scan()
