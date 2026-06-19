import os
import time
import json
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import date

# =========================
# CONFIG
# =========================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FMP_KEY = os.environ.get("FMP_API_KEY")

TREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"
SUPERTREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/supertrend_universe.csv"

FMP_CACHE = "fmp_cache.json"
SENT_FILE = "sent_signals.json"

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(msg)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown"
        }, timeout=10)
    except:
        pass

# =========================
# SENT CACHE
# =========================
def load_sent():
    if os.path.exists(SENT_FILE):
        try:
            with open(SENT_FILE, "r") as f:
                return set(tuple(x) for x in json.load(f))
        except:
            return set()
    return set()

def save_sent(data):
    with open(SENT_FILE, "w") as f:
        json.dump([list(x) for x in data], f)

# =========================
# 🔥 FMP FUNDAMENTALS (수정됨)
# =========================
def get_fmp_data(ticker):
    today = str(date.today())

    # 1. 캐시 확인
    cache = {}
    if os.path.exists(FMP_CACHE):
        try:
            cache = json.load(open(FMP_CACHE))
        except:
            cache = {}

    if ticker in cache and cache[ticker].get("date") == today:
        return cache[ticker]["data"]

    try:
        # 2. 연간 손익계산서 (최근 2년, period=annual 필수!)
        income_url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}?apikey={FMP_KEY}&limit=2&period=annual"
        income_resp = requests.get(income_url, timeout=10)
        income_data = income_resp.json()

        eps_growth = 0
        rev_growth = 0

        if income_data and len(income_data) >= 2:
            latest = income_data[0]
            previous = income_data[1]

            # 매출 성장률 (YoY)
            rev_l = latest.get('revenue', 0)
            rev_p = previous.get('revenue', 1)
            if rev_p > 0:
                rev_growth = ((rev_l - rev_p) / rev_p) * 100

            # EPS 성장률 (YoY)
            eps_l = latest.get('eps', 0)
            eps_p = previous.get('eps', 1)
            if eps_p > 0:
                eps_growth = ((eps_l - eps_p) / eps_p) * 100
            elif eps_p < 0 and eps_l > eps_p:
                # 적자→흑자 전환
                eps_growth = 999.0  # 큰 값으로 표시 (스코어에서 100으로 캡)

        # 3. ROE 가져오기 (프로필)
        profile_url = f"https://financialmodelingprep.com/api/v3/profile/{ticker}?apikey={FMP_KEY}"
        profile_resp = requests.get(profile_url, timeout=10)
        profile_data = profile_resp.json()
        roe = 0
        if profile_data and isinstance(profile_data, list):
            # ROE는 소수점(예: 0.15)이므로 * 100
            roe = profile_data[0].get('roe', 0) * 100

        data = {
            "eps_growth": round(eps_growth, 2),
            "rev_growth": round(rev_growth, 2),
            "roe": round(roe, 2)
        }

        # 캐시 저장
        cache[ticker] = {"date": today, "data": data}
        with open(FMP_CACHE, "w") as f:
            json.dump(cache, f)

        return data

    except Exception as e:
        print(f"⚠️ FMP 오류 ({ticker}): {e}")
        return {"eps_growth": 0, "rev_growth": 0, "roe": 0}

# =========================
# SCORE SYSTEM
# =========================
def growth_score(f):
    eps = f["eps_growth"]
    rev = f["rev_growth"]
    roe = f["roe"]

    # 캡 (최대 100점, 음수는 0점 처리)
    eps_scaled = min(max(eps, 0), 100)
    rev_scaled = min(max(rev, 0), 100)
    roe_scaled = min(max(roe, 0), 100)

    return (
        eps_scaled * 0.5 +
        rev_scaled * 0.3 +
        roe_scaled * 0.2
    )

def tech_score(signal_type):
    if "BREAKOUT" in signal_type:
        return 50
    if "PULLBACK" in signal_type:
        return 35
    return 40

# =========================
# TECH SIGNALS
# =========================
def check_signal(df):
    if len(df) < 50:
        return None

    close = df["Close"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()

    # 전고점 돌파 (전일 기준 20일 최고가)
    high20 = df["High"].rolling(20).max().shift(1)
    breakout = close.iloc[-1] > high20.iloc[-1]

    # 눌림목 (20>50 정배열 + 3% 이내)
    pullback = ma20.iloc[-1] > ma50.iloc[-1] and abs(close.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1] < 0.03

    if breakout:
        return "BREAKOUT"
    if pullback:
        return "PULLBACK"
    return None

# =========================
# SCAN ENGINE
# =========================
def scan(csv_url, name):
    try:
        df_csv = pd.read_csv(csv_url)
        tickers = df_csv["Symbol"].dropna().astype(str).str.strip().str.upper().tolist()
    except Exception as e:
        print(f"CSV 오류 {name}: {e}")
        return

    results = []
    sent = load_sent()
    today = str(date.today())
    print(f"\n🔥 [{name}] 스캔 시작 (종목수: {len(tickers)})")

    for t in tickers:
        try:
            # yfinance 다운로드
            df = yf.download(t, period="3mo", interval="1d", auto_adjust=True, progress=False)
            if df.empty:
                continue

            # MultiIndex 처리 (간소화)
            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs(t, axis=1, level=1)

            sig = check_signal(df)
            if not sig:
                continue

            key = (t, name, today)
            if key in sent:
                continue

            price = float(df["Close"].iloc[-1])

            # FMP 데이터 (캐시)
            fmp = get_fmp_data(t)

            g_score = growth_score(fmp)
            t_score = tech_score(sig)
            total = round(g_score * 0.6 + t_score * 0.4, 2)

            results.append({
                "ticker": t,
                "price": price,
                "signal": sig,
                "growth": g_score,
                "tech": t_score,
                "total": total
            })

            sent.add(key)
            print(f"  ✅ {t} {sig} (G:{g_score:.0f} T:{t_score:.0f} 합:{total:.1f})")

            time.sleep(0.2)

        except Exception as e:
            print(f"  ⚠️ {t} 에러: {e}")
            continue

    save_sent(sent)

    # TOP 20 정렬
    results.sort(key=lambda x: x["total"], reverse=True)

    if not results:
        send_telegram(f"🏆 [{name}] 오늘 신호 없음")
        return

    msg = f"🏆 *[{name}] TOP {min(20, len(results))}*\n\n"
    for i, r in enumerate(results[:20], 1):
        msg += (
            f"{i}. *{r['ticker']}* 总分 {r['total']:.1f}\n"
            f"   성장 {r['growth']:.0f} | 기술 {r['tech']:.0f} | ${r['price']:.2f}\n\n"
        )

    send_telegram(msg)
    print(f"✅ [{name}] 완료 ({len(results)}개 발견)")

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 스캐너 실행 (FMP 연동 완료)")
    print("=" * 50)

    scan(TREND_CSV, "TREND")
    scan(SUPERTREND_CSV, "SUPERTREND")

    print("\n✅ 모든 스캔 완료")
