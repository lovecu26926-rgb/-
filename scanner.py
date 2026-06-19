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

# ==========================================
# 🔐 환경변수 (텔레그램만 시크릿 사용)
# ==========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 🔥 CSV URL 수정 (lovecu26926-rgb / 레포명 -)
ST_CSV_URL = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"
TREND_CSV_URL = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"

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
# 📈 오직 '타점'만을 위한 핵심 지표 계산 (필터 없음)
# ==========================================
def calculate_action_indicators(df):
    if len(df) < 30:
        return None
        
    df = df.copy()
    close_vals = df['Close']
    high_vals = df['High']
    
    df['EMA21'] = close_vals.ewm(span=21, adjust=False).mean()
    df['High_20'] = high_vals.rolling(20).max()
    
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
    
    # 임무 1: ST 리스트 → 슈퍼트렌드 상승 전환
    for ticker in st_tickers:
        df = cache.get(ticker)
        if df is None: continue
        df = calculate_action_indicators(df)
        if df is None: continue
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 슈퍼트렌드 상승 전환 (다른 신호보다 우선)
        if not prev['Supertrend'] and last['Supertrend']:
            key = (ticker, "ST_REVERSAL", today)
            if key not in sent_signals:
                msg = f"🔄 *[추세전환] {ticker}*\n💰 종가: ${last['Close']:.2f}\n✅ 슈퍼트렌드 상승 전환\n⏰ {now_time.strftime('%H:%M')} EST"
                send_telegram(msg)
                sent_signals.add(key)
                signals_found.append(ticker)
                print(f"🎯 [ST 전환] {ticker}")

    # 임무 2 & 3: TREND 리스트 → 돌파 OR 눌림목 (중복 방지, 우선순위: 돌파 > 눌림목)
    for ticker in trend_tickers:
        # ST_REVERSAL 이미 송신한 종목은 TREND 신호 스킵
        if any((ticker, "ST_REVERSAL", today) == sig for sig in sent_signals):
            continue
            
        df = cache.get(ticker)
        if df is None: continue
        df = calculate_action_indicators(df)
        if df is None: continue
        
        last = df.iloc[-1]
        price = last['Close']
        
        # 돌파 우선 (더 강한 신호)
        if price > last['High_20']:
            key = (ticker, "BREAKOUT", today)
            if key not in sent_signals:
                msg = f"🚀 *[돌파] {ticker}*\n💰 종가: ${price:.2f}\n✅ 20일 고점 돌파\n⏰ {now_time.strftime('%H:%M')} EST"
                send_telegram(msg)
                sent_signals.add(key)
                signals_found.append(ticker)
                print(f"🎯 [돌파] {ticker}")
        
        # 눌림목 (돌파 아닐 때만)
        elif abs(price - last['EMA21']) / last['EMA21'] < 0.03:
            key = (ticker, "PULLBACK", today)
            if key not in sent_signals:
                msg = f"📉 *[눌림목] {ticker}*\n💰 종가: ${price:.2f}\n✅ 21일선 부근 지지\n⏰ {now_time.strftime('%H:%M')} EST"
                send_telegram(msg)
                sent_signals.add(key)
                signals_found.append(ticker)
                print(f"🎯 [눌림목] {ticker}")

    save_sent_signals(sent_signals)
    
    if signals_found:
        send_telegram(f"📊 *마감 타점 브리핑 완료*\n총 {len(set(signals_found))}개의 진입 타점이 포착되었습니다.")
    else:
        print("📊 금일 포착된 진입 타점이 없습니다.")

# ==========================================
# ⏰ 메인 실행부
# ==========================================
if __name__ == "__main__":
    print("=" * 60)
    print("🚀 실전 타점 브리핑 봇 (KST 14:00 전용)")
    print("=" * 60)

    kst_now = datetime.now(pytz.timezone('Asia/Seoul'))
    is_kst_2pm = (kst_now.hour == 14 and 0 <= kst_now.minute <= 5)
    is_weekday = (kst_now.weekday() < 5)

    # 🔥 테스트 중에는 아래 2줄을 주석 처리 (항상 실행됨)
    # if not is_weekday: exit(print("🌙 주말 - 스킵"))
    # if not is_kst_2pm: exit(print(f"⏰ 현재 {kst_now.strftime('%H:%M')} - 실행 시간 아님"))

    print("✅ 스케줄 확인 완료. 사용자 종목 리스트 타점 분석 시작...")

    try:
        st_tickers = load_tickers_from_csv(ST_CSV_URL)
        trend_tickers = load_tickers_from_csv(TREND_CSV_URL)
        all_unique_tickers = list(set(st_tickers + trend_tickers))
        
        if not all_unique_tickers:
            exit(print("⚠️ 로드된 종목이 없습니다."))
            
        print(f"🔄 대상 종목 로드 완료: 총 {len(all_unique_tickers)}개")

        print("📦 주가 데이터 다운로드 중 (period='3mo')...")
        data_cache = {}
        chunk_size = 50
        for i in range(0, len(all_unique_tickers), chunk_size):
            batch = all_unique_tickers[i:i+chunk_size]
            try:
                data = yf.download(batch, period="3mo", interval="1d", progress=False, group_by='ticker')
                
                if isinstance(data.columns, pd.MultiIndex):
                    for ticker in batch:
                        try:
                            df = data.xs(ticker, axis=1, level=1).dropna(how='all')
                            if len(df) > 0: data_cache[ticker] = df
                        except:
                            pass
                else:
                    if len(data) > 0: data_cache[batch[0]] = data.dropna(how='all')
            except Exception as e:
                print(f"⚠️ 배치 다운로드 실패: {e}")
            time.sleep(0.5)

        print(f"📦 총 {len(data_cache)}개 종목 데이터 준비 완료!")

        missing_tickers = [t for t in all_unique_tickers if t not in data_cache]
        
        if missing_tickers:
            print(f"❌ 오류 심볼 목록: {missing_tickers}")
            error_msg = (
                f"⚠️ *심볼 오류 감지!*\n"
                f"다음 {len(missing_tickers)}개 종목은 yfinance에서 데이터를 불러올 수 없습니다:\n"
                f"`{', '.join(missing_tickers[:15])}`"
            )
            if len(missing_tickers) > 15:
                error_msg += f"\n... 외 {len(missing_tickers) - 15}개 더 있음 (콘솔 확인)"
            send_telegram(error_msg)
        else:
            print("✅ 모든 심볼이 정상적으로 데이터를 불러왔습니다.")

        scan_action_points(st_tickers, trend_tickers, data_cache)
        print("✅ 마감 브리핑 프로세스 완료")
        
    except Exception as e:
        error_msg = f"❌ 시스템 에러 발생: {str(e)}"
        print(error_msg)
        send_telegram(error_msg)
