import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import time
from datetime import datetime, date
import pytz

# =========================
# 🔐 텔레그램 설정
# =========================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ 텔레그램 토큰 없음 (테스트 모드)")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }, timeout=5)
        print("📨 전송 완료")
    except Exception as e:
        print(f"❌ 전송 실패: {e}")

# =========================
# 📂 신호 중복 방지
# =========================
SIGNALS_FILE = "sent_signals.json"

def load_sent_signals():
    today = str(date.today())
    if os.path.exists(SIGNALS_FILE):
        try:
            with open(SIGNALS_FILE, 'r') as f:
                data = json.load(f)
                if data.get("date") == today:
                    return set(tuple(x) for x in data.get("signals", []))
        except:
            pass
    return set()

def save_sent_signals(signals):
    try:
        with open(SIGNALS_FILE, 'w') as f:
            json.dump({
                "date": str(date.today()),
                "signals": list(signals)
            }, f)
    except:
        pass

# =========================
# 📂 종목 관리
# =========================
UNIVERSE_FILE = 'universe.txt'

# 🔥 확장된 기본 리스트 (비상용)
DEFAULT_TICKERS = [
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA',
    'AMD', 'MU', 'AVGO', 'QQQ', 'SPY', 'IWM', 'SOXX',
    'JPM', 'V', 'WMT', 'PG', 'JNJ', 'UNH', 'HD',
    'DIS', 'MA', 'BAC', 'CVX', 'XOM', 'PFE', 'ABT',
    'NKE', 'COST', 'CRM', 'ADBE', 'NFLX', 'INTC', 'CSCO',
    'PEP', 'KO', 'MRK', 'MCD', 'ACN', 'NOW', 'TXN',
    'QCOM', 'AMAT', 'LRCX', 'KLAC', 'SNPS', 'CDNS'
]

def load_universe_from_wiki():
    try:
        sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
        nasdaq100 = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")[4]
        sp = sp500["Symbol"].tolist()
        nd = nasdaq100.iloc[:, 0].tolist()
        tickers = list(set(sp + nd))
        return [t.replace(".", "-") for t in tickers]
    except Exception as e:
        print(f"❌ 유니버스 로드 실패: {e}")
        return DEFAULT_TICKERS

def select_top_350():
    print("🔄 350개 종목 선정 중...")
    all_tickers = load_universe_from_wiki()
    candidates = []
    batch_size = 50

    for i in range(0, min(len(all_tickers), 500), batch_size):
        batch = all_tickers[i:i+batch_size]
        try:
            data = yf.download(batch, period="2y", progress=False,
                             group_by="ticker", auto_adjust=True)
            for ticker in batch:
                try:
                    df = _get_df(data, ticker, batch)
                    if df is None or len(df) < 250:
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
        except Exception as e:
            print(f"⚠️ 배치 실패: {e}")
            continue
        time.sleep(0.5)

    candidates.sort(key=lambda x: x[1], reverse=True)
    result = [c[0] for c in candidates[:350]]
    
    # 🔥 350개 선정 실패 시 오류 발생 (DEFAULT_TICKERS 방지)
    if len(result) < 50:
        raise ValueError(f"❌ 350개 선정 실패 (선정됨: {len(result)}개). 네트워크/위키피디아를 확인하세요.")
    
    return result

def get_universe():
    """
    universe.txt가 없거나 50개 미만이면 350개 새로 선정
    """
    # 1. 파일 확인
    if os.path.exists(UNIVERSE_FILE):
        with open(UNIVERSE_FILE, 'r') as f:
            tickers = f.read().splitlines()
            if len(tickers) >= 50:
                print(f"📂 파일에서 로드: {len(tickers)}개")
                return tickers
            else:
                print(f"⚠️ 파일에 종목이 {len(tickers)}개뿐 → 재선정")

    # 2. 파일 없거나 부족 → 350개 선정
    print("📁 350개 새로 선정 중...")
    tickers = select_top_350()
    save_universe(tickers)
    return tickers

def save_universe(tickers):
    with open(UNIVERSE_FILE, 'w') as f:
        f.write('\n'.join(tickers))
    print(f"💾 {len(tickers)}개 저장 완료")

# =========================
# 🔧 yfinance 버전 호환 헬퍼
# =========================
def _get_df(data, ticker, batch):
    """yfinance 버전 무관하게 df 추출"""
    try:
        if len(batch) == 1:
            return data.dropna()
        if isinstance(data.columns, pd.MultiIndex):
            if ticker not in data.columns.get_level_values(1):
                return None
            return data.xs(ticker, axis=1, level=1).dropna()
        else:
            if ticker not in data:
                return None
            return data[ticker].dropna()
    except:
        return None

# =========================
# 📈 Supertrend (numpy 최적화 + TR 버그 수정)
# =========================
def supertrend(df, period=10, mult=3):
    high = df["High"].values.astype(float)
    low = df["Low"].values.astype(float)
    close = df["Close"].values.astype(float)
    n = len(df)

    prev_close = np.empty(n)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]

    tr = np.maximum(
        high - low,
        np.maximum(
            np.abs(high - prev_close),
            np.abs(low - prev_close)
        )
    )
    tr[0] = high[0] - low[0]

    atr = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean().values
    hl2 = (high + low) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr

    final_upper = upper.copy()
    final_lower = lower.copy()
    trend = np.ones(n, dtype=bool)

    for i in range(1, n):
        if close[i-1] <= final_upper[i-1]:
            final_upper[i] = min(upper[i], final_upper[i-1])
        else:
            final_upper[i] = upper[i]

        if close[i-1] >= final_lower[i-1]:
            final_lower[i] = max(lower[i], final_lower[i-1])
        else:
            final_lower[i] = lower[i]

        if close[i] > final_upper[i-1]:
            trend[i] = True
        elif close[i] < final_lower[i-1]:
            trend[i] = False
        else:
            trend[i] = trend[i-1]

    df = df.copy()
    df["trend"] = trend
    return df

def check_pullback(df):
    ma20 = df["Close"].rolling(20).mean()
    ma50 = df["Close"].rolling(50).mean()
    is_uptrend = ma20.iloc[-1] > ma50.iloc[-1]
    near_ma20 = abs(df["Close"].iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1] < 0.03
    return is_uptrend and near_ma20

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
# 🔍 스캔
# =========================
def scan(tickers):
    sent_signals = load_sent_signals()
    today = str(date.today())
    print(f"📈 {len(tickers)}개 스캔 중... (오늘: {today})")

    chunk_size = 50
    signals_found = []

    for i in range(0, len(tickers), chunk_size):
        batch = tickers[i:i+chunk_size]

        try:
            data = yf.download(batch, period="3mo", interval="1d",
                             group_by="ticker", auto_adjust=True,
                             threads=True, progress=False)
        except Exception as e:
            print(f"⚠️ 배치 다운로드 실패: {e}")
            continue

        for ticker in batch:
            try:
                df = _get_df(data, ticker, batch)
                if df is None or len(df) < 60:
                    continue

                df = supertrend(df)
                price = float(df['Close'].iloc[-1])
                now_time = get_us_time()

                # 1️⃣ Supertrend 전환
                st_key = (ticker, "ST", today)
                if st_key not in sent_signals:
                    if not df["trend"].iloc[-2] and df["trend"].iloc[-1]:
                        msg = f"🔄 *{ticker}*\n💰 ${price:.2f}\n📈 Supertrend 상승전환\n⏰ {now_time.strftime('%H:%M')} EST"
                        send_telegram(msg)
                        sent_signals.add(st_key)
                        signals_found.append(ticker)
                        print(f"  🔄 {ticker} ST전환 ${price:.2f}")

                # 2️⃣ 눌림목
                pull_key = (ticker, "PULL", today)
                if pull_key not in sent_signals:
                    if check_pullback(df):
                        msg = f"📉 *{ticker}*\n💰 ${price:.2f}\n📈 20일 눌림목\n⏰ {now_time.strftime('%H:%M')} EST"
                        send_telegram(msg)
                        sent_signals.add(pull_key)
                        signals_found.append(ticker)
                        print(f"  📉 {ticker} 눌림목 ${price:.2f}")

                # 3️⃣ 돌파
                break_key = (ticker, "BREAK", today)
                if break_key not in sent_signals:
                    if check_breakout(df):
                        msg = f"🚀 *{ticker}*\n💰 ${price:.2f}\n📈 전고점 돌파\n⏰ {now_time.strftime('%H:%M')} EST"
                        send_telegram(msg)
                        sent_signals.add(break_key)
                        signals_found.append(ticker)
                        print(f"  🚀 {ticker} 돌파 ${price:.2f}")

            except Exception as e:
                continue

        time.sleep(1)

    save_sent_signals(sent_signals)

    unique = len(set(signals_found))
    if unique > 0:
        summary = f"📊 *스캔 완료*\n신호: {unique}개\n⏰ {get_us_time().strftime('%H:%M')} EST"
        send_telegram(summary)
        print(f"  📊 총 {unique}개 신호 발견")
    else:
        print("  📊 신호 없음")

# =========================
# 🚀 메인 (1회 실행)
# =========================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 Supertrend 스캐너 v3.1")
    print("=" * 50)

    try:
        tickers = get_universe()
        now = get_us_time()
        print(f"⏰ 현재 미국 동부 시간: {now.strftime('%Y-%m-%d %H:%M')} EST")

        if is_market_open():
            print("📈 장중 스캔 실행")
            scan(tickers)
        else:
            print("🌙 장마감 - 종목 업데이트")
            new_tickers = select_top_350()
            save_universe(new_tickers)
            send_telegram(f"🌙 내일 스캔 대상 {len(new_tickers)}개 선정 완료")

        print("✅ 완료 - 종료")
    except Exception as e:
        error_msg = f"❌ 에러 발생: {str(e)}"
        print(error_msg)
        send_telegram(error_msg)
