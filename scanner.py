import os
import yfinance as yf
import pandas as pd
import requests
import json
import time
from datetime import date
import warnings

warnings.filterwarnings("ignore")

# =========================
# 텔레그램
# =========================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# =========================
# 종목 CSV
# =========================
CSV_URL = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"

# =========================
# 텔레그램 전송
# =========================
def send_telegram(message):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            },
            timeout=10
        )
    except Exception as e:
        print("텔레그램 오류:", e)


# =========================
# 중복 알림 방지
# =========================
def load_sent_signals():

    today = str(date.today())

    if os.path.exists("sent_signals_action.json"):
        try:
            with open("sent_signals_action.json", "r") as f:
                data = json.load(f)

            if data.get("date") == today:
                return set(tuple(x) for x in data.get("signals", []))

        except:
            pass

    return set()


def save_sent_signals(signals):

    try:
        with open("sent_signals_action.json", "w") as f:
            json.dump(
                {
                    "date": str(date.today()),
                    "signals": list(signals)
                },
                f
            )
    except:
        pass


# =========================
# CSV 로드
# =========================
def load_tickers():

    try:
        df = pd.read_csv(CSV_URL)

        return [
            x.strip().upper()
            for x in df["Symbol"].dropna().astype(str)
        ]

    except Exception as e:
        print("CSV 오류:", e)
        return []


# =========================
# 지표 계산
# =========================
def calculate_indicators(df):

    if df is None or len(df) < 30:
        return None

    df = df.copy()

    df["EMA21"] = df["Close"].ewm(
        span=21,
        adjust=False
    ).mean()

    # 오늘 제외 최근20일 최고가
    df["High_20"] = (
        df["High"]
        .shift(1)
        .rolling(20)
        .max()
    )

    return df


# =========================
# 메인
# =========================
if __name__ == "__main__":

    tickers = load_tickers()

    print(f"종목수 : {len(tickers)}")

    data_cache = {}

    print("데이터 다운로드 시작")

    for ticker in tickers:

        try:

            df = yf.download(
                ticker,
                period="3mo",
                interval="1d",
                auto_adjust=True,
                progress=False
            )

            if not df.empty:
                data_cache[ticker] = df

            time.sleep(0.3)

        except Exception as e:
            print(ticker, e)

    print(f"다운로드 완료 : {len(data_cache)}개")

    sent_signals = load_sent_signals()

    today = str(date.today())

    for ticker, raw_df in data_cache.items():

        df = calculate_indicators(raw_df)

        if df is None:
            continue

        last = df.iloc[-1]

        close = float(last["Close"])
        ema21 = float(last["EMA21"])
        high20 = float(last["High_20"])

        # 20일 돌파 + EMA21 위
        breakout = (
            close > high20 and
            close > ema21
        )

        if breakout:

            signal_key = (
                ticker,
                "BREAKOUT",
                today
            )

            if signal_key not in sent_signals:

                msg = (
                    f"🚀 *20일 돌파*\n\n"
                    f"종목 : {ticker}\n"
                    f"종가 : ${close:.2f}\n"
                    f"EMA21 : ${ema21:.2f}\n"
                    f"20일고가 : ${high20:.2f}"
                )

                send_telegram(msg)

                sent_signals.add(signal_key)

    save_sent_signals(sent_signals)

    print("스캔 완료")
