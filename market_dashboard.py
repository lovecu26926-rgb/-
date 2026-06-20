import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime
import pytz

# =========================
# 🔐 텔레그램 설정
# =========================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ 텔레그램 설정 없음")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        for _ in range(2):
            r = requests.post(url, data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message[:4000],
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }, timeout=10)

            if r.status_code == 200:
                print("📨 전송 성공")
                return
            time.sleep(2)

    except Exception as e:
        print(f"❌ 텔레그램 실패: {e}")

# =========================
# 📥 안전 다운로드
# =========================
def safe_download(ticker):
    try:
        df = yf.download(
            ticker,
            period="2y",
            progress=False,
            auto_adjust=True,
            threads=False,
            timeout=10
        )
        if df is None or df.empty:
            return None
        return clean_yf_data(df)
    except:
        return None

# =========================
# 🧹 데이터 정제
# =========================
def clean_yf_data(df):
    if df is None or df.empty:
        return None

    try:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        required = ['Open', 'High', 'Low', 'Close']
        for c in required:
            if c not in df.columns:
                return None

        df = df[required].dropna().astype(float)

        if len(df) < 200:
            return None

        return df

    except:
        return None

# =========================
# 📊 SuperTrend
# =========================
def calculate_supertrend(df, period=10, mult=3):
    high = df["High"].values
    low = df["Low"].values
    close = df["Close"].values
    n = len(df)

    if n < 50:
        return np.array([True] * n)

    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]

    tr = np.maximum(
        high - low,
        np.maximum(abs(high - prev_close), abs(low - prev_close))
    )

    atr = pd.Series(tr).ewm(alpha=1/period, adjust=False).mean().values

    hl2 = (high + low) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr

    final_upper = upper.copy()
    final_lower = lower.copy()
    trend = np.ones(n, dtype=bool)

    final_upper[0] = upper[0]
    final_lower[0] = lower[0]

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

    return trend

# =========================
# 📈 트렌드 신호
# =========================
def get_trend_signal(df):
    if df is None or len(df) < 220:
        return "데이터 부족", "❌", ""

    try:
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma50 = df['Close'].rolling(50).mean().iloc[-1]
        ma200 = df['Close'].rolling(200).mean().iloc[-1]

        if np.isnan(ma200):
            return "데이터 부족", "❌", ""

        if ma20 > ma50 > ma200:
            ma_status, ma_emoji = "완전 정배열", "✅"
        elif ma20 > ma50:
            ma_status, ma_emoji = "부분 정배열", "🟡"
        elif ma20 < ma50 < ma200:
            ma_status, ma_emoji = "역배열", "❌"
        else:
            ma_status, ma_emoji = "혼재", "⚪️"

        trend = calculate_supertrend(df)

        signal = ""
        if len(trend) > 2:
            if not trend[-2] and trend[-1]:
                signal = "🟢 상승전환"
            elif trend[-2] and not trend[-1]:
                signal = "🔴 하락전환"

        return ma_status, ma_emoji, signal

    except:
        return "에러", "❌", ""

# =========================
# 😨 CNN Fear & Greed
# =========================
def get_fear_greed_index():
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()

        if 'fear_and_greed' not in data:
            return None, None

        return data['fear_and_greed']['score'], data['fear_and_greed']['rating']

    except:
        return None, None

# =========================
# 🌍 글로벌 티커
# =========================
tickers = {
    'SPY': 'S&P 500',
    'QQQ': '나스닥 100',
    'DIA': '다우존스',
    'IWM': '러셀 2000',

    'VGK': '유럽',
    'EWJ': '일본',
    'EWY': '한국 ETF',
    '^KS11': '코스피',

    'XLK': '테크',
    'SMH': '반도체',
    'XLF': '금융',
    'XLE': '에너지',
    'XLV': '헬스케어',

    'UUP': '달러',
    'JPY=X': '달러/엔',

    'GC=F': '금',
    'SI=F': '은',
    'HG=F': '구리',
    'BTC-USD': '비트코인',

    '^TNX': '10년물',
    '^IRX': '2년물',

    'HYG': '하이일드',
    'LQD': '투자등급',
    '^VIX': 'VIX'
}

# =========================
# 📊 데이터 수집
# =========================
def get_global_dashboard():
    results = {}

    for ticker, name in tickers.items():
        df = safe_download(ticker)

        if df is None:
            results[ticker] = {"name": name, "error": "no data"}
            continue

        try:
            current = df['Close'].iloc[-1]
            prev = df['Close'].iloc[-2]
            change = (current / prev - 1) * 100

            ma_status, ma_emoji, signal = get_trend_signal(df)

            results[ticker] = {
                "name": name,
                "price": current,
                "change": change,
                "ma_status": ma_status,
                "ma_emoji": ma_emoji,
                "signal": signal
            }

        except:
            results[ticker] = {"name": name, "error": "calc error"}

        time.sleep(0.3)

    return results

# =========================
# 📱 포맷
# =========================
def format_dashboard(results):
    now = datetime.now(pytz.timezone('US/Eastern'))

    msg = "🌍 <b>GLOBAL MACRO DASHBOARD v5.1</b>\n"
    msg += f"⏰ {now.strftime('%Y-%m-%d %H:%M')}\n"
    msg += "========================\n\n"

    msg += "📊 <b>MARKETS</b>\n"
    for t in ['SPY','QQQ','DIA','IWM']:
        r = results.get(t)
        if r and 'error' not in r:
            emoji = "🟢" if r['change'] > 0 else "🔴"
            msg += f"{emoji} {r['name']}: {r['change']:+.2f}% [{r['ma_emoji']}{r['ma_status']}]\n"

    msg += "\n🌏 <b>GLOBAL</b>\n"
    for t in ['EWJ','EWY','^KS11']:
        r = results.get(t)
        if r and 'error' not in r:
            emoji = "🟢" if r['change'] > 0 else "🔴"
            msg += f"{emoji} {r['name']}: {r['change']:+.2f}%\n"

    msg += "\n🔥 <b>SECTOR</b>\n"
    for t in ['XLK','SMH','XLF','XLE']:
        r = results.get(t)
        if r and 'error' not in r:
            msg += f"{r['name']}: {r['change']:+.2f}%\n"

    msg += "\n💱 <b>FX</b>\n"
    for t in ['UUP','JPY=X']:
        r = results.get(t)
        if r and 'error' not in r:
            msg += f"{r['name']}: {r['price']:.2f}\n"

    msg += "\n🪙 <b>ASSETS</b>\n"
    for t in ['GC=F','BTC-USD','^VIX']:
        r = results.get(t)
        if r and 'error' not in r:
            msg += f"{r['name']}: {r['price']:.2f}\n"

    score, rating = get_fear_greed_index()
    if score:
        msg += f"\n😨 Fear & Greed: {score}/100 ({rating})\n"

    msg += "\n========================"
    return msg

# =========================
# 🚀 RUN
# =========================
if __name__ == "__main__":
    print("🚀 RUNNING DASHBOARD")

    results = get_global_dashboard()
    msg = format_dashboard(results)

    send_telegram(msg)

    print("DONE")
