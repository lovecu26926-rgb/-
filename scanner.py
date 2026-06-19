```python
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

warnings.filterwarnings('ignore') # pandas 경고 무시

# ==========================================
# 🔐 환경변수 (설정값)
# ==========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
# 사용자님이 선정한 종목 리스트 (CSV 링크)
ST_CSV_URL = os.environ.get("ST_CSV_URL")       # 슈퍼트렌드 전환용 종목들
TREND_CSV_URL = os.environ.get("TREND_CSV_URL") # 추세추종 (눌림/돌파)용 종목들

# ==========================================
# 📂 텔레그램 전송 및 중복 방지
# ==========================================
def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[텔레그램 전송 대기]\n{message}\n")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}, timeout=5)
    except Exception as e:
        print(f"❌ 전송 실패: {e}")

SIGNALS_FILE = "sent_signals_action.json"
def load_sent_signals():
    today = str(date.today())
    if os.path.exists(SIGNALS_FILE):
        try:
            with open(SIGNALS_FILE, 'r') as f:
                data = json.load(f)
                if data.get("date") == today:
                    return set(tuple(x) for x in data.get("signals", []))
        except: pass
    return set()

def save_sent_signals(signals):
    try:
        with open(SIGNALS_FILE, 'w') as f:
            json.dump({"date": str(date.today()), "signals": list(signals)}, f)
    except: pass

def load_tickers_from_csv(url):
    """사용자님이 선정한 종목 리스트를 불러옵니다."""
    if not url: return []
    try:
        df = pd.read_csv(url)
        return [t.strip().upper() for t in df['Symbol'].dropna().astype(str).tolist() if t.strip()]
    except Exception as e: 
        print(f"⚠️ CSV 로드 실패: {e}")
        return []

def get_us_time():
    return datetime.now(pytz.timezone('US/Eastern'))

# ==========================================
# 📈 오직 '타점'만을 위한 핵심 지표 계산
# ==========================================
def calculate_action_indicators(df):
    if len(df) < 30: # 20일선 등을 계산하기 위한 최소한의 데이터 (약 1.5개월)
        return None
        
    df = df.copy()
    close_vals = df['Close']
    high_vals = df['High']
    
    # 1. 눌림목 포착용: 21일 지수이동평균 (EMA 21)
    df['EMA21'] = close_vals.ewm(span=21, adjust=False).mean()
    
    # 2. 돌파 포착용: 20일간의 최고가 (최근 고점)
    df['High_20'] = high_vals.rolling(20).max()
    
    # 3. 추세전환 포착용: 슈퍼트렌드 (10, 3)
    period = 10; mult = 3
    high, low, c_val = df["High"].values, df["Low"].values, close_vals.values
    tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(c_val, 1)), np.abs(low - np.roll(c_val, 1))))
    tr[0] = high[0] - low[0]
    atr = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean().values
    hl2 = (high + low) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    
    f_up, f_dn = upper.copy(), lower.copy()
    trend = np.ones(len(df), dtype=bool)
    
    for i in range(1, len(df)):
        f_up[i] = min(upper[i], f_up[i-1]) if c_val[i-1] <= f_up[i-1] else upper[i]
        f_dn[i] = max(lower[i], f_dn[i-1]) if c_val[i-1] >= f_dn[i-1] else lower[i]
        if c_val[i] > f_up[i-1]: trend[i] = True
        elif c_val[i] < f_dn[i-1]: trend[i] = False
        else: trend[i] = trend[i-1]
        
    df['Supertrend'] = trend
    
    return df

# ==========================================
# 🎯 타점 스캔 & 텔레그램 송출
# ==========================================
def scan_action_points(st_tickers, trend_tickers, cache):
    sent_signals = load_sent_signals()
    today = str(date.today())
    now_time = get_us_time()
    
    signals_found = []
    
    # -------------------------------------------------
    # 임무 1: 추세전환 포착 (슈퍼트렌드 상승 전환 첫날)
    # -------------------------------------------------
    for ticker in st_tickers:
        df = cache.get(ticker)
        if df is None: continue
        
        df = calculate_action_indicators(df)
        if df is None: continue
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 어제는 하락(False)이었는데, 오늘 상승(True)으로 바뀐 종목
        if not prev['Supertrend'] and last['Supertrend']:
            key = (ticker, "ST_REVERSAL", today)
            if key not in sent_signals:
                msg = f"🔄 *[추세전환 포착] {ticker}*\n💰 종가: ${last['Close']:.2f}\n✅ 슈퍼트렌드 상승 전환\n⏰ {now_time.strftime('%H:%M')} EST"
                send_telegram(msg)
                sent_signals.add(key)
                signals_found.append(ticker)
                print(f"🎯 [ST 전환] {ticker}")

    # -------------------------------------------------
    # 임무 2 & 3: 추세추종 리스트 내의 '눌림' 및 '돌파' 포착
    # -------------------------------------------------
    for ticker in trend_tickers:
        df = cache.get(ticker)
        if df is None: continue
        
        df = calculate_action_indicators(df)
        if df is None: continue
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = last['Close']
        
        # 임무 2: 눌림목 포착 (현재가가 21일선 근처 3% 이내로 내려왔을 때)
        if abs(price - last['EMA21']) / last['EMA21'] < 0.03:
            key = (ticker, "PULLBACK", today)
            if key not in sent_signals:
                msg = f"📉 *[눌림목 포착] {ticker}*\n💰 종가: ${price:.2f}\n✅ 21일선 부근 지지 확인\n⏰ {now_time.strftime('%H:%M')} EST"
                send_telegram(msg)
                sent_signals.add(key)
                signals_found.append(ticker)
                print(f"🎯 [눌림목] {ticker}")

        # 임무 3: 돌파 포착 (어제 기준 최근 20일의 가장 높은 가격을 오늘 뚫었을 때)
        if price > prev['High_20']:
            key = (ticker, "BREAKOUT", today)
            if key not in sent_signals:
                msg = f"🚀 *[신고가 돌파 포착] {ticker}*\n💰 종가: ${price:.2f}\n✅ 20일 고점 돌파\n⏰ {now_time.strftime('%H:%M')} EST"
                send_telegram(msg)
                sent_signals.add(key)
                signals_found.append(ticker)
                print(f"🎯 [돌파] {ticker}")

    # 발송된 신호 저장 (중복 알림 방지)
    save_sent_signals(sent_signals)
    
    # 전체 요약 브리핑
    if signals_found:
        summary_msg = f"📊 *마감 타점 브리핑 완료*\n제공해주신 종목 중 총 {len(set(signals_found))}개의 진입 타점이 포착되었습니다."
        send_telegram(summary_msg)
        print(summary_msg)
    else:
        print("📊 금일 포착된 진입 타점이 없습니다.")

# ==========================================
# ⏰ 메인 실행부 (정해진 시간에만 작동)
# ==========================================
if __name__ == "__main__":
    print("=" * 60)
    print("🚀 실전 타점 브리핑 봇 (KST 14:00 전용)")
    print("=" * 60)

    # 1. 정해진 시간 확인 (한국 시간 기준 평일 오후 2시)
    kst_now = datetime.now(pytz.timezone('Asia/Seoul'))
    is_kst_2pm = (kst_now.hour == 14 and 0 <= kst_now.minute <= 5) # 오후 2시 0분 ~ 5분 사이
    is_weekday = (kst_now.weekday() < 5) # 월(0) ~ 금(4)

    # 시간에 구애받지 않고 당장 테스트하고 싶으시다면 아래 두 줄 앞에 # 을 붙여 주석처리 하세요.
    if not is_weekday: exit(print("🌙 주말 - 스캔을 스킵합니다."))
    if not is_kst_2pm: exit(print(f"⏰ 현재 {kst_now.strftime('%H:%M')} - 정해진 스케줄(14:00)이 아닙니다."))

    print("✅ 스케줄 확인 완료. 사용자 종목 리스트 타점 분석 시작...")

    try:
        # 2. 사용자 제공 리스트 다운로드
        st_tickers = load_tickers_from_csv(ST_CSV_URL)
        trend_tickers = load_tickers_from_csv(TREND_CSV_URL)
        all_unique_tickers = list(set(st_tickers + trend_tickers))
        
        if not all_unique_tickers:
            exit(print("⚠️ 로드된 종목이 없습니다. CSV URL 또는 환경변수를 확인해주세요."))
            
        print(f"🔄 대상 종목 로드 완료: 총 {len(all_unique_tickers)}개")

        # 3. 초고속 주가 데이터 다운로드 (최소한의 기간인 3개월치만 다운로드)
        print("📦 주가 데이터 다운로드 중 (period='3mo')...")
        data_cache = {}
        chunk_size = 50
        for i in range(0, len(all_unique_tickers), chunk_size):
            batch = all_unique_tickers[i:i+chunk_size]
            try:
                data = yf.download(batch, period="3mo", interval="1d", progress=False, group_by='ticker')
                
                if isinstance(data.columns, pd.MultiIndex):
                    for ticker in batch:
                        if ticker in data.columns.get_level_values(0):
                            df = data[ticker].dropna(how='all')
                            if len(df) > 0: data_cache[ticker] = df
                        elif ticker in data.columns.get_level_values(1):
                            df = data.xs(ticker, axis=1, level=1).dropna(how='all')
                            if len(df) > 0: data_cache[ticker] = df
                else: 
                    if len(data) > 0: data_cache[batch[0]] = data.dropna(how='all')
            except Exception as e:
                print(f"⚠️ 데이터 다운로드 실패: {e}")
            time.sleep(0.1) 

        # 4. 포착 및 송출 실행
        scan_action_points(st_tickers, trend_tickers, data_cache)

        print("✅ 마감 브리핑 송출 프로세스 완료")
        
    except Exception as e:
        print(f"❌ 시스템 에러 발생: {str(e)}")

```
