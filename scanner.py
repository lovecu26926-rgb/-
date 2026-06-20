import pandas as pd
import yfinance as yf
import requests
import time

# =========================
# 데이터 소스
# =========================
TREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"
SUPERTREND_CSV = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/supertrend_universe.csv"

# =========================
# 텔레그램
# =========================
TELEGRAM_TOKEN = "YOUR_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"

def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=10
        )
    except Exception as e:
        print("Telegram error:", e)

# =========================
# RS (1년 수익률)
# =========================
def calc_rs(df):
    try:
        return (df["Close"].iloc[-1] / df["Close"].iloc[0] - 1) * 100
    except:
        return 0

# =========================
# 추세 신호
# =========================
def get_signals(df):
    close = df["Close"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    high20 = df["High"].rolling(20).max().shift(1)

    signals = []

    # 돌파
    if close.iloc[-1] > high20.iloc[-1] * 1.01:
        signals.append("돌파")

    # 눌림목
    if ma20.iloc[-1] > ma50.iloc[-1] and close.iloc[-1] < ma20.iloc[-1]:
        signals.append("눌림목")

    # 골든크로스
    if ma20.iloc[-2] <= ma50.iloc[-2] and ma20.iloc[-1] > ma50.iloc[-1]:
        signals.append("골든크로스")

    # 추세전환 (조건 완화: 구조 변화만)
    if ma20.iloc[-2] < ma50.iloc[-2] and ma20.iloc[-1] > ma50.iloc[-1]:
        signals.append("추세전환")

    return signals

# =========================
# 20일 반등 (추세전환용)
# =========================
def momentum_20d(df):
    try:
        return (df["Close"].iloc[-1] / df["Close"].iloc[-20] - 1) * 100
    except:
        return 0

# =========================
# 실행
# =========================
def scan():
    trend = pd.read_csv(TREND_CSV)["Symbol"].dropna().tolist()
    supert = pd.read_csv(SUPERTREND_CSV)["Symbol"].dropna().tolist()
    tickers = list(set(trend + supert))

    buckets = {
        "돌파": [],
        "눌림목": [],
        "골든크로스": [],
        "추세전환": []
    }

    print(f"[SCAN] 종목 수: {len(tickers)}")

    for t in tickers:
        try:
            df = yf.download(t, period="1y", interval="1d", auto_adjust=True, progress=False)
            if df.empty:
                continue

            rs = calc_rs(df)
            signals = get_signals(df)

            if not signals:
                continue

            for s in signals:
                if s == "추세전환":
                    buckets[s].append((t, momentum_20d(df)))
                else:
                    buckets[s].append((t, rs))

            time.sleep(0.1)

        except:
            continue

    # =========================
    # 정렬
    # =========================
    for k in ["돌파", "눌림목", "골든크로스"]:
        buckets[k].sort(key=lambda x: x[1], reverse=True)

    buckets["추세전환"].sort(key=lambda x: x[1], reverse=True)

    # =========================
    # 출력
    # =========================
    msg = ""

    for cat in ["돌파", "눌림목", "골든크로스", "추세전환"]:
        msg += f"\n🏆 [{cat}]\n\n"

        items = buckets[cat][:10]

        if not items:
            msg += "없음\n"
            continue

        for i, (t, val) in enumerate(items, 1):

            try:
                df = yf.download(t, period="1y", interval="1d", auto_adjust=True, progress=False)

                rev = 0
                eps = 0

                if cat == "추세전환":
                    msg += f"{i}. {t} | 20일 {val:.1f}% | 매출 {rev} | EPS {eps}\n"
                else:
                    msg += f"{i}. {t} | RS {val:.1f}% | 매출 {rev} | EPS {eps}\n"

            except:
                continue

    print(msg)
    send_telegram(msg)

# =========================
# 실행
# =========================
if __name__ == "__main__":
    scan()
