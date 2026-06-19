import os
import yfinance as yf
import pandas as pd
import numpy as np
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

TREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"
SUPERTREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/supertrend_universe.csv"

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=10)
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
            json.dump({"date": str(date.today()), "signals": list(signals)}, f)
    except:
        pass

# =========================
# CSV 로드
# =========================
def load_tickers(csv_url):
    try:
        df = pd.read_csv(csv_url)
        return [x.strip().upper() for x in df["Symbol"].dropna().astype(str)]
    except Exception as e:
        print(f"CSV 오류 ({csv_url}):", e)
        return []

# =========================
# 🔧 yfinance DataFrame 정리 (MultiIndex 제거)
# =========================
def _flatten_df(df):
    """MultiIndex 컬럼을 단일 레벨로 변환"""
    if df is None or df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        # 첫 번째 티커를 선택 (단일 종목이므로 첫 번째 레벨)
        ticker = df.columns.levels[1][0]
        df = df.xs(ticker, axis=1, level=1)
    return df

# =========================
# 📈 Supertrend 계산 (1D 강제)
# =========================
def calculate_supertrend(df, period=10, mult=3):
    high = df["High"].values.astype(float)
    low = df["Low"].values.astype(float)
    close = df["Close"].values.astype(float)
    n = len(df)

    prev_close = np.empty(n)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]

    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
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

    # 🔥 1D 강제 변환 (broadcast 에러 방지)
    trend = trend.flatten()

    df = df.copy()
    df["trend"] = trend
    return df

# =========================
# 🎯 필터 1: 추세추종 (20일 눌림목 OR 전고점 돌파)
# =========================
def check_trend_signal(df):
    if df is None or len(df) < 30:
        return False, None

    df = df.copy()
    # 모든 값은 스칼라로 추출
    close = float(df['Close'].iloc[-1])
    ma20 = float(df['Close'].rolling(20).mean().iloc[-1])
    ma50 = float(df['Close'].rolling(50).mean().iloc[-1])
    high20 = float(df['High'].shift(1).rolling(20).max().iloc[-1])

    # 눌림목 (20>50 + 3% 이내)
    is_uptrend = ma20 > ma50
    near_ma20 = abs(close - ma20) / ma20 < 0.03
    pullback = is_uptrend and near_ma20

    # 돌파
    breakout = close > high20

    is_signal = pullback or breakout
    detail = (
        f"20일선: ${ma20:.2f} (이격: {abs(close-ma20)/ma20*100:.1f}%) | "
        f"50일선: ${ma50:.2f} | "
        f"20일고가: ${high20:.2f} | "
        f"신호: {'눌림목' if pullback else '돌파' if breakout else '없음'}"
    )
    return is_signal, detail

# =========================
# 🎯 필터 2: Supertrend (상승전환 ONLY)
# =========================
def check_supertrend_signal(df):
    if df is None or len(df) < 60:
        return False, None

    df = calculate_supertrend(df)
    # 스칼라 추출
    prev = bool(df["trend"].iloc[-2])
    curr = bool(df["trend"].iloc[-1])
    st_reversal = (not prev) and curr

    is_signal = st_reversal
    detail = f"Supertrend 상승전환: {st_reversal}"
    return is_signal, detail

# =========================
# 🔍 통합 스캔 엔진
# =========================
def scan_universe(csv_url, check_func, mode_name):
    print(f"\n📊 [{mode_name}] 스캔 시작...")

    tickers = load_tickers(csv_url)
    print(f"  종목수: {len(tickers)}개")

    if not tickers:
        print(f"  ⚠️ {mode_name} 리스트 없음")
        return

    sent_signals = load_sent_signals()
    today = str(date.today())
    found = []

    for ticker in tickers:
        try:
            # 데이터 다운로드
            df = yf.download(ticker, period="3mo", interval="1d", auto_adjust=True, progress=False)
            if df.empty:
                continue

            # MultiIndex 처리
            df = _flatten_df(df)
            if df is None or len(df) < 30:
                continue

            # 신호 체크
            is_signal, detail = check_func(df)
            if is_signal:
                key = (ticker, mode_name, today)
                if key not in sent_signals:
                    price = float(df['Close'].iloc[-1])
                    msg = f"🚀 *{mode_name} 신호*\n\n종목: {ticker}\n종가: ${price:.2f}\n{detail}"
                    send_telegram(msg)
                    sent_signals.add(key)
                    found.append(ticker)
                    print(f"  ✅ {ticker} 신호 발견")

            time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠️ {ticker} 오류: {e}")

    save_sent_signals(sent_signals)
    print(f"  📊 [{mode_name}] 총 {len(found)}개 신호 발견")

# =========================
# 🚀 메인
# =========================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 통합 스캐너 (추세추종 + Supertrend)")
    print("=" * 50)

    scan_universe(TREND_CSV, check_trend_signal, "추세추종")
    scan_universe(SUPERTREND_CSV, check_supertrend_signal, "Supertrend")

    print("\n✅ 전체 스캔 완료")
