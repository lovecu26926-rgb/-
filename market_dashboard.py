import os
import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime
import pytz

# =========================
# 🔐 텔레그램 설정 (Secrets에서 가져옴)
# =========================
TELEGRAM_TOKEN = ("8680217169:AAEsFlCloKbbVR40HxkoXtdZ6hLho9o1aGs")
TELEGRAM_CHAT_ID = ("61473298612")

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ 텔레그램 토큰 없음")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=5)
        print("📨 텔레그램 전송 완료")
    except Exception as e:
        print(f"❌ 전송 실패: {e}")

# =========================
# 📊 SuperTrend 계산
# =========================
def calculate_supertrend(df, period=10, mult=3):
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
    
    df['trend'] = trend
    return df

# =========================
# 📈 이평선 정배열 + SuperTrend 신호
# =========================
def get_trend_signal(df):
    if len(df) < 200:
        return "데이터 부족", "❌", "", ""
    
    # 이평선
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
    
    # SuperTrend
    df = calculate_supertrend(df)
    
    signal = ""
    signal_emoji = ""
    if len(df) >= 3:
        if df['trend'].iloc[-2] == False and df['trend'].iloc[-1] == True:
            signal = "🟢 SuperTrend 상승전환"
            signal_emoji = "🟢"
        elif df['trend'].iloc[-2] == True and df['trend'].iloc[-1] == False:
            signal = "🔴 SuperTrend 하락전환"
            signal_emoji = "🔴"
    
    return ma_status, ma_emoji, signal, signal_emoji

# =========================
# 🌏 글로벌 대시보드
# =========================
def get_global_dashboard():
    tickers = {
        # 미국
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
        # 채권
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
            df = yf.download(ticker, period="1y", progress=False)
            if len(df) < 50:
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
        time.sleep(0.3)
    
    return results

# =========================
# 📱 대시보드 포맷
# =========================
def format_dashboard(results):
    now = datetime.now(pytz.timezone('US/Eastern'))
    
    msg = "🌏 *글로벌 매크로 대시보드*\n"
    msg += f"⏰ {now.strftime('%Y-%m-%d %H:%M')} EST\n"
    msg += "=" * 30 + "\n\n"
    
    # 미국 지수
    msg += "📈 *미국 주요 지수*\n"
    for t in ['SPY', 'QQQ', 'DIA', 'IWM']:
        r = results.get(t)
        if r and 'error' not in r:
            emoji = "🟢" if r['change'] > 0 else "🔴"
            msg += f"{emoji} {r['name']}: ${r['price']:.2f} "
            msg += f"({'+' if r['change']>0 else ''}{r['change']:.2f}%) "
            msg += f"[{r['ma_emoji']} {r['ma_status']}]"
            if r['signal']:
                msg += f" [{r['signal_emoji']} {r['signal']}]"
            msg += "\n"
    msg += "\n"
    
    # 유럽 지수
    msg += "🌏 *유럽 주요 지수*\n"
    for t in ['VGK', 'EWU', 'EWQ', 'EWG']:
        r = results.get(t)
        if r and 'error' not in r:
            emoji = "🟢" if r['change'] > 0 else "🔴"
            msg += f"{emoji} {r['name']}: ${r['price']:.2f} "
            msg += f"({'+' if r['change']>0 else ''}{r['change']:.2f}%) "
            msg += f"[{r['ma_emoji']} {r['ma_status']}]"
            if r['signal']:
                msg += f" [{r['signal_emoji']} {r['signal']}]"
            msg += "\n"
    msg += "\n"
    
    # 아시아 지수
    msg += "🌏 *아시아 주요 지수*\n"
    for t in ['EWJ', 'EWY', 'EWT']:
        r = results.get(t)
        if r and 'error' not in r:
            emoji = "🟢" if r['change'] > 0 else "🔴"
            msg += f"{emoji} {r['name']}: ${r['price']:.2f} "
            msg += f"({'+' if r['change']>0 else ''}{r['change']:.2f}%) "
            msg += f"[{r['ma_emoji']} {r['ma_status']}]"
            if r['signal']:
                msg += f" [{r['signal_emoji']} {r['signal']}]"
            msg += "\n"
    msg += "\n"
    
    # 섹터
    msg += "🏭 *미국 섹터 흐름*\n"
    sector_list = ['XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLB', 'XLU', 'XLY', 'XLP', 'XLRE']
    for t in sector_list:
        r = results.get(t)
        if r and 'error' not in r:
            emoji = "🟢" if r['change'] > 0 else "🔴"
            msg += f"{emoji} {r['name']}: {r['change']:+.2f}% "
            msg += f"[{r['ma_emoji']} {r['ma_status']}]"
            if r['signal']:
                msg += f" [{r['signal_emoji']} {r['signal']}]"
            msg += "\n"
    msg += "\n"
    
    # 거시
    msg += "🌍 *거시 지표*\n"
    if '^VIX' in results and 'error' not in results['^VIX']:
        vix = results['^VIX']['price']
        status = "😎 낙관" if vix < 15 else "😊 안정" if vix < 20 else "😐 불안" if vix < 25 else "😨 공포"
        msg += f"📊 VIX: {vix:.2f} ({status})\n"
    if 'BTC-USD' in results and 'error' not in results['BTC-USD']:
        r = results['BTC-USD']
        msg += f"₿ 비트코인: ${r['price']:,.0f} ({r['change']:+.2f}%)\n"
    
    # SuperTrend 신호 요약
    msg += "\n" + "=" * 30 + "\n"
    msg += "🚨 *SuperTrend 추세전환 신호*\n"
    
    buy_signals = []
    sell_signals = []
    for t, r in results.items():
        if r and 'error' not in r and r.get('signal'):
            if '상승전환' in r['signal']:
                buy_signals.append(f"🟢 {r['name']}")
            elif '하락전환' in r['signal']:
                sell_signals.append(f"🔴 {r['name']}")
    
    if buy_signals:
        msg += "📈 매수 신호:\n" + "\n".join(buy_signals[:5]) + "\n"
    if sell_signals:
        msg += "📉 매도 신호:\n" + "\n".join(sell_signals[:5]) + "\n"
    
    return msg

# =========================
# 🚀 실행
# =========================
if __name__ == "__main__":
    print("🌏 글로벌 대시보드 생성 중...")
    results = get_global_dashboard()
    msg = format_dashboard(results)
    send_telegram(msg)
    print("✅ 전송 완료")
