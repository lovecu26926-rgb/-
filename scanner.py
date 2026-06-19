import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import time
from datetime import datetime, date
import pytz
import warnings

warnings.filterwarnings('ignore')

# 🔐 환경변수 설정
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

ST_CSV_URL = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"
TREND_CSV_URL = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[텔레그램 전송 대기]\n{message}\n")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}, timeout=5)
    except Exception as e:
        print(f"❌ 전송 실패: {e}")

def load_sent_signals():
    today = str(date.today())
    if os.path.exists("sent_signals_action.json"):
        try:
            with open("sent_signals_action.json", 'r') as f:
                data = json.load(f)
                if data.get("date") == today:
                    return set(tuple(x) for x in data.get("signals", []))
        except: pass
    return set()

def save_sent_signals(signals):
    try:
        with open("sent_signals_action.json", 'w') as f:
            json.dump({"date": str(date.today()), "signals": list(signals)}, f)
    except: pass

def load_tickers_from_csv(url):
    try:
        df = pd.read_csv(url)
        return [t.strip().upper() for t in df['Symbol'].dropna().astype(str).tolist() if t.strip()]
    except Exception as e: 
        print(f"⚠️ CSV 로드 실패: {e}")
        return []

def calculate_indicators(df):
    if len(df) < 30: return None
    df = df.copy()
    df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['High_20'] = df['High'].rolling(20).max()
    
    # Supertrend
    atr = df['High'].rolling(10).mean() # 간소화된 지표 계산
    df['Supertrend'] = df['Close'] > df['EMA21']
    return df

if __name__ == "__main__":
    st_tickers = load_tickers_from_csv(ST_CSV_URL)
    trend_tickers = load_tickers_from_csv(TREND_CSV_URL)
    all_tickers = list(set(st_tickers + trend_tickers))
    
    data_cache = {}
    session = yf.shared.get_session()
    
    print("📦 데이터 다운로드 시작...")
    for ticker in all_tickers:
        try:
            df = yf.download(ticker, period="3mo", interval="1d", progress=False, session=session)
            if not df.empty:
                data_cache[ticker] = df
        except:
            continue
        time.sleep(0.4)
    
    print(f"✅ {len(data_cache)}개 종목 데이터 준비 완료. 분석 시작...")
    
    sent_signals = load_sent_signals()
    today = str(date.today())
    
    for ticker in all_tickers:
        df = calculate_indicators(data_cache.get(ticker))
        if df is None: continue
        
        last = df.iloc[-1]
        # 예시 신호 로직
        if ticker in trend_tickers and last['Close'] > last['High_20']:
            key = (ticker, "BREAKOUT", today)
            if key not in sent_signals:
                send_telegram(f"🚀 *[돌파] {ticker}*\n💰 가격: ${last['Close']:.2f}")
                sent_signals.add(key)
    
    save_sent_signals(sent_signals)
    print("✅ 완료")
