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
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
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
# 📂 CSV 로드 (재무 데이터 포함)
# =========================
def load_tickers_with_fundamentals(csv_url):
    """CSV에서 Symbol, EPS, 매출, 이익률 로드"""
    try:
        df = pd.read_csv(csv_url)
        tickers = []
        
        # 컬럼명 매핑 (한글/영문 모두 대응)
        col_map = {}
        for col in df.columns:
            if 'Symbol' in col or 'Ticker' in col:
                col_map['symbol'] = col
            elif 'EPS' in col or '희석' in col or '성장' in col:
                col_map['eps'] = col
            elif '매출' in col or 'Revenue' in col:
                col_map['rev'] = col
            elif '이익률' in col or 'Margin' in col or 'Profit' in col:
                col_map['margin'] = col
        
        # 기본값 설정
        symbol_col = col_map.get('symbol', df.columns[0])
        eps_col = col_map.get('eps', None)
        rev_col = col_map.get('rev', None)
        margin_col = col_map.get('margin', None)
        
        for _, row in df.iterrows():
            ticker = str(row[symbol_col]).strip().upper()
            if not ticker:
                continue
                
            item = {'symbol': ticker}
            
            # EPS 성장률
            if eps_col and pd.notna(row[eps_col]):
                try:
                    item['eps_growth'] = float(row[eps_col])
                except:
                    item['eps_growth'] = 0
            else:
                item['eps_growth'] = 0
            
            # 매출 성장률
            if rev_col and pd.notna(row[rev_col]):
                try:
                    item['rev_growth'] = float(row[rev_col])
                except:
                    item['rev_growth'] = 0
            else:
                item['rev_growth'] = 0
            
            # 이익률
            if margin_col and pd.notna(row[margin_col]):
                try:
                    item['margin'] = float(row[margin_col])
                except:
                    item['margin'] = 0
            else:
                item['margin'] = 0
            
            tickers.append(item)
        
        print(f"  ✅ CSV 로드 완료: {len(tickers)}개 (EPS/매출/이익률 포함)")
        return tickers
    except Exception as e:
        print(f"  ❌ CSV 오류: {e}")
        return []

# =========================
# 📊 성장 점수 계산
# =========================
def calculate_growth_score(eps_growth, rev_growth, margin):
    """EPS 50% + 매출 30% + 이익률 20% (0~100점)"""
    
    # 1. EPS 점수 (50%)
    if eps_growth >= 100:
        eps_score = 100
    elif eps_growth >= 50:
        eps_score = 80
    elif eps_growth >= 20:
        eps_score = 50
    elif eps_growth >= 0:
        eps_score = 20
    else:
        eps_score = 0
    
    # 2. 매출 점수 (30%)
    if rev_growth >= 50:
        rev_score = 100
    elif rev_growth >= 30:
        rev_score = 70
    elif rev_growth >= 10:
        rev_score = 40
    elif rev_growth >= 0:
        rev_score = 20
    else:
        rev_score = 0
    
    # 3. 이익률 점수 (20%)
    if margin >= 30:
        margin_score = 100
    elif margin >= 15:
        margin_score = 70
    elif margin >= 5:
        margin_score = 40
    elif margin >= 0:
        margin_score = 20
    else:
        margin_score = 0
    
    # 가중치 적용
    total = (eps_score * 0.5) + (rev_score * 0.3) + (margin_score * 0.2)
    return round(total, 1)

# =========================
# 🔧 yfinance MultiIndex 처리
# =========================
def _flatten_df(df):
    if df is None or df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
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

    df = df.copy()
    df["trend"] = trend.flatten()
    return df

# =========================
# 🎯 필터 1: 추세추종 (20일 눌림목 OR 전고점 돌파)
# =========================
def check_trend_signal(df):
    if df is None or len(df) < 30:
        return False, None

    close = float(df['Close'].iloc[-1])
    ma20 = float(df['Close'].rolling(20).mean().iloc[-1])
    ma50 = float(df['Close'].rolling(50).mean().iloc[-1])
    high20 = float(df['High'].shift(1).rolling(20).max().iloc[-1])

    is_uptrend = ma20 > ma50
    near_ma20 = abs(close - ma20) / ma20 < 0.03
    pullback = is_uptrend and near_ma20
    breakout = close > high20

    is_signal = pullback or breakout
    detail = f"{'돌파' if breakout else ''}{'눌림목' if pullback else ''}"
    return is_signal, detail

# =========================
# 🎯 필터 2: Supertrend (상승전환 ONLY)
# =========================
def check_supertrend_signal(df):
    if df is None or len(df) < 60:
        return False, None

    df = calculate_supertrend(df)
    prev = bool(df["trend"].iloc[-2])
    curr = bool(df["trend"].iloc[-1])
    st_reversal = (not prev) and curr

    is_signal = st_reversal
    detail = f"Supertrend 상승전환"
    return is_signal, detail

# =========================
# 📱 페이지네이션 전송 (20개씩)
# =========================
def send_paginated_results(signal_results, mode_name, chunk_size=20):
    """점수순 정렬 후 20개씩 페이지로 분할 전송"""
    
    if not signal_results:
        send_telegram(f"📊 [{mode_name}] 오늘 발견된 신호가 없습니다.")
        return
    
    # 점수 기준 정렬 (내림차순)
    signal_results.sort(key=lambda x: x['total_score'], reverse=True)
    total = len(signal_results)
    
    # 페이지 계산
    total_pages = (total + chunk_size - 1) // chunk_size
    
    for page in range(total_pages):
        start = page * chunk_size
        end = min(start + chunk_size, total)
        chunk = signal_results[start:end]
        
        # 헤더
        if total_pages == 1:
            msg = f"🏆 *[{mode_name}] 초고성장주 TOP {total} (점수순)*\n\n"
        else:
            msg = f"🏆 *[{mode_name}] 초고성장주 ({page+1}/{total_pages} 페이지)*\n"
            msg += f"📊 {start+1} ~ {end}위 (총 {total}개)\n\n"
        
        # 종목 목록 (1줄 압축)
        for idx, s in enumerate(chunk, start=start+1):
            icon = "📈" if "돌파" in s['detail'] else "📉" if "눌림목" in s['detail'] else "🔄"
            msg += (
                f"{idx}. *{s['ticker']}* - {s['total_score']:.1f}점 "
                f"| 💰${s['price']:.0f} | {icon}{s['detail']} "
                f"| EPS+{s['eps']:.0f}% 매출+{s['rev']:.0f}%\n"
            )
        
        # 푸터
        msg += "\n" + "=" * 25 + "\n"
        avg_score = sum(s['total_score'] for s in chunk) / len(chunk)
        msg += f"📌 평균: {avg_score:.1f}점"
        
        if page == 0:
            msg += f" | 🔥 1위: {signal_results[0]['ticker']} ({signal_results[0]['total_score']:.1f}점)"
        
        if page < total_pages - 1:
            msg += f"\n📎 나머지 {total - end}개는 다음 메시지에서..."
        else:
            msg += f"\n✅ 모든 종목 전송 완료 (총 {total}개)"
        
        send_telegram(msg)
        time.sleep(0.5)  # 연속 전송 제한 방지

# =========================
# 🔍 통합 스캔 엔진
# =========================
def scan_universe(csv_url, check_func, mode_name):
    print(f"\n📊 [{mode_name}] 스캔 시작...")
    
    ticker_infos = load_tickers_with_fundamentals(csv_url)
    print(f"  종목수: {len(ticker_infos)}개")
    
    if not ticker_infos:
        print(f"  ⚠️ {mode_name} 리스트 없음")
        return
    
    sent_signals = load_sent_signals()
    today = str(date.today())
    signal_results = []  # 점수 포함 결과 저장

    for info in ticker_infos:
        ticker = info['symbol']
        try:
            df = yf.download(ticker, period="3mo", interval="1d", auto_adjust=True, progress=False)
            if df.empty:
                continue
            
            df = _flatten_df(df)
            if df is None or len(df) < 30:
                continue
            
            is_signal, detail = check_func(df)
            if is_signal:
                key = (ticker, mode_name, today)
                if key not in sent_signals:
                    price = float(df['Close'].iloc[-1])
                    
                    # 🔥 성장 점수 계산
                    growth_score = calculate_growth_score(
                        info.get('eps_growth', 0),
                        info.get('rev_growth', 0),
                        info.get('margin', 0)
                    )
                    
                    # 기술 점수 (신호 유형별 가중치)
                    tech_score = 5 if "돌파" in detail else 3 if "눌림목" in detail else 4
                    
                    # 종합 점수 (성장 70% + 기술 30%)
                    total_score = round((growth_score * 0.7) + (tech_score * 0.3), 1)
                    
                    signal_results.append({
                        'ticker': ticker,
                        'price': price,
                        'detail': detail,
                        'eps': info.get('eps_growth', 0),
                        'rev': info.get('rev_growth', 0),
                        'margin': info.get('margin', 0),
                        'growth_score': growth_score,
                        'total_score': total_score
                    })
                    
                    sent_signals.add(key)
                    print(f"  ✅ {ticker} 신호 (점수: {total_score:.1f})")
            
            time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠️ {ticker} 오류: {e}")
    
    save_sent_signals(sent_signals)
    
    # 🔥 페이지네이션 전송
    send_paginated_results(signal_results, mode_name)
    print(f"  📊 [{mode_name}] 총 {len(signal_results)}개 신호 발견")

# =========================
# 🚀 메인
# =========================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 통합 스캐너 (추세추종 + Supertrend + 점수)")
    print("=" * 50)
    
    # 1️⃣ 추세추종 스캔
    scan_universe(TREND_CSV, check_trend_signal, "추세추종")
    
    # 2️⃣ Supertrend 스캔
    scan_universe(SUPERTREND_CSV, check_supertrend_signal, "Supertrend")
    
    print("\n✅ 전체 스캔 완료")
