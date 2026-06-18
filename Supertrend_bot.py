import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime

# =========================
# 🔐 텔레그램 설정
# =========================
TOKEN = "8680217169"
CHAT_ID = "6147329612"

def send_msg(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=5)
    except Exception as e:
        print(f"텔레그램 메시지 전송 실패: {e}")

# =========================
# 📡 유니버스
# =========================
def load_universe():
    df = pd.read_csv("top1000.csv")
    return df["ticker"].dropna().tolist()

# =========================
# 📈 Supertrend (RMA 적용)
# =========================
def supertrend(df, period=10, mult=3):
    high, low, close = df["High"], df["Low"], df["Close"]

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    # 단순 이동평균(SMA) 대신 더 정확한 Wilder's Smoothing(RMA/EMA 방식) 적용
    atr = tr.ewm(alpha=1/period, adjust=False).mean()

    hl2 = (high + low) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr

    trend = [True]

    for i in range(1, len(df)):
        if close.iloc[i] > upper.iloc[i-1]:
            trend.append(True)
        elif close.iloc[i] < lower.iloc[i-1]:
            trend.append(False)
        else:
            trend.append(trend[-1])

    df["trend"] = trend
    return df

# =========================
# 📉 눌림 & 🚀 돌파
# =========================
def pullback(df):
    ma20 = df["Close"].rolling(20).mean()
    ma50 = df["Close"].rolling(50).mean()
    return (
        ma20.iloc[-1] > ma50.iloc[-1]
        and abs(df["Close"].iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1] < 0.03
    )

def breakout(df):
    high20 = df["High"].rolling(20).max()
    return df["Close"].iloc[-1] > high20.iloc[-2]

# =========================
# 🔍 스캔 엔진 (Batch Download)
# =========================
sent = set()

def scan():
    tickers = load_universe()
    chunk_size = 100 # 100개씩 끊어서 서버 부하 및 차단 방지

    for i in range(0, len(tickers), chunk_size):
        batch = tickers[i:i+chunk_size]
        
        try:
            # yfinance 병렬 다운로드 (속도 10배 이상 향상)
            data = yf.download(
                batch, 
                period="3mo", 
                interval="1d", 
                group_by="ticker", 
                threads=True, 
                progress=False
            )
        except Exception as e:
            print(f"데이터 다운로드 에러: {e}")
            continue

        for t in batch:
            try:
                # 티커가 1개일 때와 여러 개일 때 반환되는 데이터 구조 처리
                df = data[t].dropna() if len(batch) > 1 else data.dropna()
                
                if len(df) < 60:
                    continue

                df = supertrend(df)

                # 1. Supertrend 추세전환
                if (t, "ST") not in sent:
                    if df["trend"].iloc[-2] == False and df["trend"].iloc[-1] == True:
                        send_msg(f"{t}\n📌 추세전환 (Supertrend)")
                        sent.add((t, "ST"))

                # 2. 20/50 눌림
                if (t, "PULL") not in sent:
                    if pullback(df):
                        send_msg(f"{t}\n📉 20/50 눌림매수")
                        sent.add((t, "PULL"))

                # 3. 전고 돌파
                if (t, "BREAK") not in sent:
                    if breakout(df):
                        send_msg(f"{t}\n🚀 전고 돌파")
                        sent.add((t, "BREAK"))

            except Exception as e:
                # 에러가 발생해도 다른 종목 스캔이 멈추지 않도록 처리
                continue

        time.sleep(1) # 청크(100개)마다 1초 휴식하여 IP 차단 방지

# =========================
# 🚀 메인 루프 (자동사냥)
# =========================
send_msg("🚀 AUTO SCANNER STARTED V2")
last_run_date = datetime.now().date()

while True:
    now_date = datetime.now().date()
    
    # 🔔 날짜가 바뀌면 sent 세트를 초기화 (매일 새로운 신호를 받기 위함)
    if now_date != last_run_date:
        sent.clear()
        last_run_date = now_date
        send_msg("🔄 날짜 변경: 알림 기록이 초기화되었습니다.")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 스캔 시작...")
    scan()
    print("스캔 완료. 2시간 대기합니다.\n")
    
    time.sleep(7200) # 2시간마다 실행
