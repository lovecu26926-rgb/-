import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timedelta
import pytz

# =========================
# 🔐 텔레그램 설정 (여기에 넣으세요!)
# =========================
TELEGRAM_TOKEN = "8680217169"  # @BotFather에서 받은 토큰
TELEGRAM_CHAT_ID = "6147329612"  # @userinfobot으로 확인

def send_telegram(message):
    """텔레그램 메시지 전송"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=5)
        print(f"📨 텔레그램 전송 완료")
    except Exception as e:
        print(f"❌ 텔레그램 전송 실패: {e}")

# =========================
# 📂 파일 관리 (자동)
# =========================
UNIVERSE_FILE = 'universe.txt'

def load_universe():
    """전체 종목 로드 (3000개)"""
    try:
        sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
        nasdaq100 = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")[4]
        russell = pd.read_html("https://en.wikipedia.org/wiki/Russell_2000_Index")[0]
        
        sp = sp500["Symbol"].tolist()
        nd = nasdaq100.iloc[:, 0].tolist()
        ru = russell[russell.columns[0]].tolist()
        
        tickers = list(set(sp + nd + ru))
        return [t.replace(".", "-") for t in tickers]
    except Exception as e:
        print(f"❌ 유니버스 로드 실패: {e}")
        return ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA', 'AMZN', 'META']

def select_top_350():
    """3000개 중 350개 선정"""
    print("🔄 350개 종목 선정 중...")
    all_tickers = load_universe()
    candidates = []
    
    for ticker in all_tickers[:1000]:
        try:
            df = yf.download(ticker, period="1y", progress=False)
            if len(df) < 200:
                continue
            if df['Volume'].mean() < 500000:
                continue
            if df['Close'].iloc[-1] < 5:
                continue
            
            ma50 = df['Close'].rolling(50).mean().iloc[-1]
            ma200 = df['Close'].rolling(200).mean().iloc[-1]
            if ma50 < ma200 * 0.9:
                continue
            
            candidates.append((ticker, df['Volume'].mean()))
        except:
            continue
        time.sleep(0.3)
    
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [c[0] for c in candidates[:350]]

def get_universe():
    """자동으로 350개 로드 or 생성"""
    if os.path.exists(UNIVERSE_FILE):
        with open(UNIVERSE_FILE, 'r') as f:
            tickers = f.read().splitlines()
            print(f"📂 파일에서 350개 로드: {len(tickers)}개")
            return tickers
    
    print("📁 파일 없음 → 새로 선정")
    tickers = select_top_350()
    save_universe(tickers)
    return tickers

def save_universe(tickers):
    with open(UNIVERSE_FILE, 'w') as f:
        f.write('\n'.join(tickers))
    print(f"💾 350개 저장 완료")

# =========================
# 📈 Supertrend
# =========================
def supertrend(df, period=10, mult=3):
    high, low, close = df["High"], df["Low"], df["Close"]
    
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    
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
# 📉 눌림목
# =========================
def check_pullback(df):
    ma20 = df["Close"].rolling(20).mean()
    ma50 = df["Close"].rolling(50).mean()
    
    is_uptrend = ma20.iloc[-1] > ma50.iloc[-1]
    near_ma20 = abs(df["Close"].iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1] < 0.03
    
    return is_uptrend and near_ma20

# =========================
# 🚀 돌파
# =========================
def check_breakout(df):
    high20 = df["High"].rolling(20).max()
    return df["Close"].iloc[-1] > high20.iloc[-2]

# =========================
# ⏰ 시간 체크
# =========================
def get_us_time():
    return datetime.now(pytz.timezone('US/Eastern'))

def is_market_open():
    now = get_us_time()
    if now.weekday() >= 5:
        return False
    open_time = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_time = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_time <= now <= close_time

# =========================
# 🔍 스캔 (텔레그램 알림 포함)
# =========================
sent_signals = set()  # 중복 알림 방지

def scan(tickers):
    """350개 스캔 + 텔레그램 알림"""
    print(f"📈 {len(tickers)}개 스캔 중...")
    
    chunk_size = 50
    signals_found = []
    
    for i in range(0, len(tickers), chunk_size):
        batch = tickers[i:i+chunk_size]
        
        try:
            data = yf.download(
                batch,
                period="3mo",
                interval="1d",
                group_by="ticker",
                threads=True,
                progress=False
            )
        except Exception as e:
            print(f"⚠️ 배치 다운로드 실패: {e}")
            continue
        
        for ticker in batch:
            try:
                if ticker not in data:
                    continue
                
                df = data[ticker].dropna()
                if len(df) < 60:
                    continue
                
                df = supertrend(df)
                price = df['Close'].iloc[-1]
                now = get_us_time()
                
                # ==========================================
                # 1️⃣ Supertrend 추세전환
                # ==========================================
                if (ticker, "ST") not in sent_signals:
                    if df["trend"].iloc[-2] == False and df["trend"].iloc[-1] == True:
                        msg = (
                            f"🔄 *{ticker}*\n"
                            f"💰 ${price:.2f}\n"
                            f"📈 Supertrend 상승전환\n"
                            f"⏰ {now.strftime('%H:%M')} EST"
                        )
                        send_telegram(msg)
                        sent_signals.add((ticker, "ST"))
                        signals_found.append(ticker)
                        print(f"  ✅ {ticker}: Supertrend 상승전환")
                
                # ==========================================
                # 2️⃣ 20일 눌림목
                # ==========================================
                if (ticker, "PULL") not in sent_signals:
                    if check_pullback(df):
                        ma20 = df['Close'].rolling(20).mean().iloc[-1]
                        diff = abs(price - ma20) / ma20 * 100
                        msg = (
                            f"📉 *{ticker}*\n"
                            f"💰 ${price:.2f}\n"
                            f"📈 20일 눌림목\n"
                            f"📊 20일선 이격: {diff:.1f}%\n"
                            f"⏰ {now.strftime('%H:%M')} EST"
                        )
                        send_telegram(msg)
                        sent_signals.add((ticker, "PULL"))
                        signals_found.append(ticker)
                        print(f"  ✅ {ticker}: 20일 눌림목 ({diff:.1f}%)")
                
                # ==========================================
                # 3️⃣ 전고점 돌파
                # ==========================================
                if (ticker, "BREAK") not in sent_signals:
                    if check_breakout(df):
                        high20 = df['High'].rolling(20).max().iloc[-2]
                        msg = (
                            f"🚀 *{ticker}*\n"
                            f"💰 ${price:.2f}\n"
                            f"📈 전고점 돌파\n"
                            f"📊 20일 고가: ${high20:.2f}\n"
                            f"⏰ {now.strftime('%H:%M')} EST"
                        )
                        send_telegram(msg)
                        sent_signals.add((ticker, "BREAK"))
                        signals_found.append(ticker)
                        print(f"  ✅ {ticker}: 전고점 돌파")
                        
            except Exception as e:
                continue
        
        time.sleep(1)
    
    if signals_found:
        print(f"  📊 총 {len(set(signals_found))}개 신호 발견")
    else:
        print("  📊 신호 없음")

# =========================
# 🚀 메인 (완전 자동)
# =========================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 미국 장 기준 자동 스캐너")
    print("=" * 50)
    print("📋 3가지 매매법:")
    print("  1. Supertrend 추세전환")
    print("  2. 20일 눌림목")
    print("  3. 전고점 돌파")
    print("=" * 50)
    
    # 시작 알림
    send_telegram("🚀 *스캐너 시작*\n장중 2시간 간격으로 스캔합니다.")
    
    # 최초 1회: 350개 선정 or 파일 로드
    tickers = get_universe()
    filter_done_today = False
    
    while True:
        try:
            now = get_us_time()
            
            # 주말 체크
            if now.weekday() >= 5:
                print(f"\n😴 주말입니다. ({now.strftime('%A')})")
                time.sleep(3600)
                continue
            
            if is_market_open():
                # 장중: 350개 스캔
                scan(tickers)
                filter_done_today = False
                wait = 7200  # 2시간
                
            else:
                # 장마감: 350개 업데이트 (하루 1번)
                if not filter_done_today:
                    print("🌙 장마감 - 350개 업데이트")
                    tickers = select_top_350()
                    save_universe(tickers)
                    filter_done_today = True
                    send_telegram(f"🌙 내일 스캔 대상 {len(tickers)}개 선정 완료")
                
                # 자정 넘으면 리셋
                if now.hour == 0 and now.minute == 0:
                    filter_done_today = False
                
                wait = 3600  # 1시간
            
            next_time = (now + timedelta(seconds=wait)).strftime('%H:%M')
            print(f"⏰ 다음 실행: {next_time} EST")
            time.sleep(wait)
            
        except KeyboardInterrupt:
            print("\n🛑 사용자에 의해 종료")
            send_telegram("🛑 *스캐너 종료*")
            break
        except Exception as e:
            print(f"\n❌ 에러 발생: {e}")
            send_telegram(f"⚠️ 에러 발생: {str(e)[:100]}")
            time.sleep(300)
