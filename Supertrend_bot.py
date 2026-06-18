import yfinance as yf
import pandas as pd
import requests, time, logging, pytz
from datetime import datetime

# 설정
TOKEN = "8680217169:AAEsF1CloKbbVR40HxkoXtdZ6hLho9o1aGs"
CHAT_ID = "6147329612"
KST = pytz.timezone("Asia/Seoul")

def send_msg(text):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                  json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})

def get_universe():
    # S&P500 + NASDAQ + Russell 2000 티커 합치기
    try:
        # 간단하게 주요 리스트만 관리 (2000개 전체는 타임아웃 위험으로 핵심 종목 위주 권장)
        tickers = ["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "GOOGL", "AMZN", "META", "AVGO", "ADBE"] 
        return tickers
    except: return ["AAPL", "MSFT", "NVDA"]

def check_supertrend(ticker):
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if len(df) < 20: return False
        
        atr = (df['High'] - df['Low']).rolling(10).mean()
        hl2 = (df['High'] + df['Low']) / 2
        
        # 간단한 슈퍼트렌드 조건 (직전 추세 반전)
        upper = hl2 + (3.0 * atr)
        lower = hl2 - (3.0 * atr)
        
        # 조건: 오늘 종가가 lower band를 상향 돌파했는가?
        if df['Close'].iloc[-2] < lower.iloc[-2] and df['Close'].iloc[-1] > lower.iloc[-1]:
            return True
    except: return False
    return False

def run_bot():
    tickers = get_universe()
    signals = []
    
    for t in tickers:
        if check_supertrend(t):
            signals.append(t)
        time.sleep(0.5) # 타임아웃 방지
    
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    if signals:
        send_msg(f"🎯 <b>[{now}] 매수 신호 포착:</b>\n" + ", ".join(signals))
    else:
        send_msg(f"📊 <b>[{now}]</b> 스캔 완료: 매수 신호 종목 없음")

if __name__ == "__main__":
    run_bot()
