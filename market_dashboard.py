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
        print("⚠️ 텔레그램 토큰 없음")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        response = requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }, timeout=10)
        if response.status_code == 200:
            print("📨 전송 완료")
        else:
            print(f"⚠️ HTML 실패, 일반 텍스트 재전송")
            requests.post(url, data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "disable_web_page_preview": True
            }, timeout=10)
    except Exception as e:
        print(f"❌ 전송 실패: {e}")

# =========================
# 📈 Supertrend (numpy 최적화)
# =========================
def calculate_supertrend(df, period=10, mult=3):
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

    return trend

# =========================
# 📊 이평선 정배열 + SuperTrend 신호
# =========================
def get_trend_signal(df):
    if len(df) < 250:
        return "데이터 부족", "❌", "", ""

    ma20 = df['Close'].rolling(20).mean().iloc[-1]
    ma50 = df['Close'].rolling(50).mean().iloc[-1]
    ma200 = df['Close'].rolling(200).mean().iloc[-1]

    if ma20 > ma50 > ma200:
        ma_status, ma_emoji = "완전 정배열", "✅"
    elif ma20 > ma50:
        ma_status, ma_emoji = "부분 정배열", "🟡"
    elif ma20 < ma50 < ma200:
        ma_status, ma_emoji = "역배열", "❌"
    else:
        ma_status, ma_emoji = "혼재", "⚪"

    trend = calculate_supertrend(df)

    signal = ""
    signal_emoji = ""
    if len(trend) >= 3:
        if not trend[-2] and trend[-1]:
            signal = "🟢 SuperTrend 상승전환"
            signal_emoji = "🟢"
        elif trend[-2] and not trend[-1]:
            signal = "🔴 SuperTrend 하락전환"
            signal_emoji = "🔴"

    return ma_status, ma_emoji, signal, signal_emoji

# =========================
# 🔧 yfinance 데이터 정제 헬퍼
# =========================
def clean_yf_data(df):
    """yfinance 데이터프레임 정제 (멀티인덱스 + Volume 부재 대응)"""
    if df.empty:
        return None

    # 멀티인덱스 처리
    if isinstance(df.columns, pd.MultiIndex):
        if len(df.columns.levels) > 1:
            ticker = df.columns.levels[1][0]
            df = df.xs(ticker, axis=1, level=1)
        else:
            df = df.droplevel(1, axis=1)

    # 필수 컬럼만 선택 (Volume은 없을 수 있음)
    required_cols = ['Open', 'High', 'Low', 'Close']
    existing_cols = [c for c in required_cols if c in df.columns]
    if 'Volume' in df.columns:
        existing_cols.append('Volume')

    df = df[existing_cols].copy()
    df = df.astype(float)
    return df

# =========================
# 🌏 글로벌 대시보드
# =========================
def get_global_dashboard():
    tickers = {
        # 미국 지수
        'SPY': 'S&P 500',
        'QQQ': '나스닥 100',
        'DIA': '다우존스',
        'IWM': '러셀 2000',
        # 유럽
        'VGK': '유럽 전체',
        'EWU': '영국 FTSE',
        'EWQ': '프랑스 CAC',
        'EWG': '독일 DAX',
        # 아시아
        'EWJ': '일본 닛케이',
        'EWY': '한국 코스피',
        'EWT': '대만 가권',
        # 섹터
        'XLK': '테크 섹터',
        'XLF': '금융 섹터',
        'XLE': '에너지 섹터',
        'XLV': '헬스케어',
        'XLI': '산업 섹터',
        'XLB': '소재 섹터',
        'XLU': '유틸리티',
        'XLY': '소비재',
        'XLP': '필수소비재',
        'XLRE': '리츠',
        # 원자재
        'GLD': '금 (Gold)',
        'SLV': '은 (Silver)',
        'COPX': '구리 (Copper)',
        # 채권 금리
        '^IRX': '미국 3개월물',
        '^FVX': '미국 5년물',
        '^TNX': '미국 10년물',
        '^TYX': '미국 30년물',
        # 거시
        '^VIX': '공포지수 VIX',
        'UUP': '달러 인덱스',
        'TLT': '장기채 ETF',
        'BTC-USD': '비트코인',
    }

    results = {}
    print(f"📊 {len(tickers)}개 데이터 수집 중...")

    for ticker, name in tickers.items():
        try:
            df = yf.download(ticker, period="2y", progress=False, auto_adjust=True)
            df = clean_yf_data(df)

            if df is None or len(df) < 250:
                results[ticker] = {'name': name, 'error': '데이터 부족'}
                continue

            current = df['Close'].iloc[-1]
            prev = df['Close'].iloc[-2]
            change = ((current / prev) - 1) * 100

            ma_status, ma_emoji, signal, signal_emoji = get_trend_signal(df)

            results[ticker] = {
                'name': name,
                'price': current,
                'change': change,
                'ma_status': ma_status,
                'ma_emoji': ma_emoji,
                'signal': signal,
                'signal_emoji': signal_emoji
            }
        except Exception as e:
            results[ticker] = {'name': name, 'error': str(e)[:30]}
        time.sleep(0.15)

    return results

# =========================
# 📱 대시보드 포맷 (HTML)
# =========================
def format_dashboard(results):
    now = datetime.now(pytz.timezone('US/Eastern'))

    msg = "🌏 <b>글로벌 매크로 대시보드</b>\n"
    msg += f"⏰ {now.strftime('%Y-%m-%d %H:%M')} EST\n"
    msg += "==============================\n\n"

    sections = [
        ("📈 <b>미국 주요 지수</b>", ['SPY', 'QQQ', 'DIA', 'IWM'], True),
        ("🌏 <b>유럽 주요 지수</b>", ['VGK', 'EWU', 'EWQ', 'EWG'], True),
        ("🌏 <b>아시아 주요 지수</b>", ['EWJ', 'EWY', 'EWT'], True),
        ("🏭 <b>미국 섹터 흐름</b>", ['XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLB', 'XLU', 'XLY', 'XLP', 'XLRE'], False),
    ]

    for title, ticker_list, show_price in sections:
        msg += f"{title}\n"
        for t in ticker_list:
            r = results.get(t)
            if r and 'error' not in r:
                emoji = "🟢" if r['change'] > 0 else "🔴"
                if show_price:
                    msg += f"{emoji} {r['name']}: ${r['price']:.2f} ({r['change']:+.2f}%) [{r['ma_emoji']} {r['ma_status']}]"
                else:
                    msg += f"{emoji} {r['name']}: {r['change']:+.2f}% [{r['ma_emoji']} {r['ma_status']}]"
                if r['signal']:
                    msg += f" [{r['signal_emoji']} {r['signal']}]"
                msg += "\n"
        msg += "\n"

    # 거시 지표
    msg += "🌍 <b>거시 지표</b>\n"
    if '^VIX' in results and 'error' not in results['^VIX']:
        vix = results['^VIX']['price']
        if vix < 15:
            status = "😎 낙관"
        elif vix < 20:
            status = "😊 안정"
        elif vix < 25:
            status = "😐 불안"
        else:
            status = "😨 공포"
        msg += f"📊 VIX: {vix:.2f} ({status})\n"

    if 'BTC-USD' in results and 'error' not in results['BTC-USD']:
        r = results['BTC-USD']
        msg += f"₿ 비트코인: ${r['price']:,.0f} ({r['change']:+.2f}%)\n"

    # SuperTrend 요약
    msg += "\n==============================\n"
    msg += "🚨 <b>SuperTrend 추세전환 신호</b>\n"

    buy_signals = []
    sell_signals = []
    for t, r in results.items():
        if r and 'error' not in r and r.get('signal'):
            if '상승전환' in r['signal']:
                buy_signals.append(f"🟢 {r['name']}")
            elif '하락전환' in r['signal']:
                sell_signals.append(f"🔴 {r['name']}")

    if buy_signals:
        msg += "📈 <b>매수 신호:</b>\n" + "\n".join(buy_signals[:5]) + "\n\n"
    if sell_signals:
        msg += "📉 <b>매도 신호:</b>\n" + "\n".join(sell_signals[:5]) + "\n"
    if not buy_signals and not sell_signals:
        msg += "조회된 추세전환 신호가 없습니다.\n"

    return msg

# =========================
# 🚀 실행
# =========================
if __name__ == "__main__":
    print("=" * 50)
    print("🌏 글로벌 매크로 대시보드 v3.2 (딥시크 최종)")
    print("=" * 50)

    results = get_global_dashboard()
    msg = format_dashboard(results)

    if len(msg) > 4000:
        summary = "📊 <b>대시보드 요약 (글자수 초과)</b>\n"
        summary += "==============================\n\n"

        buy = []
        sell = []
        for t, r in results.items():
            if r and 'error' not in r and r.get('signal'):
                if '상승전환' in r['signal']:
                    buy.append(f"🟢 {r['name']}")
                elif '하락전환' in r['signal']:
                    sell.append(f"🔴 {r['name']}")

        if buy:
            summary += "📈 <b>매수 신호:</b>\n" + "\n".join(buy[:3]) + "\n\n"
        if sell:
            summary += "📉 <b>매도 신호:</b>\n" + "\n".join(sell[:3]) + "\n"

        send_telegram(summary)
    else:
        send_telegram(msg)

    print("✅ 프로세스 완료")
