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
        requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            },
            timeout=10
        )

    except Exception as e:
        print("텔레그램 오류:", e)


# =========================
# 중복 알림
# =========================

def load_sent_signals():

    today = str(date.today())

    if os.path.exists("sent_signals_action.json"):

        try:

            with open(
                "sent_signals_action.json",
                "r"
            ) as f:

                data = json.load(f)

            if data.get("date") == today:
                return set(tuple(x)
                           for x in data.get("signals", []))

        except:
            pass

    return set()


def save_sent_signals(signals):

    try:

        with open(
            "sent_signals_action.json",
            "w"
        ) as f:

            json.dump(
                {
                    "date": str(date.today()),
                    "signals": list(signals)
                },
                f
            )

    except:
        pass


# =========================
# CSV 로드
# =========================

def load_tickers_with_fundamentals(csv_url):

    try:

        df = pd.read_csv(csv_url)

        tickers = []

        col_map = {}

        for col in df.columns:

            if "Symbol" in col or "Ticker" in col:
                col_map["symbol"] = col

            elif "EPS" in col or "희석" in col:
                col_map["eps"] = col

            elif "매출" in col or "Revenue" in col:
                col_map["rev"] = col

            elif "Margin" in col or "이익률" in col:
                col_map["margin"] = col

        symbol_col = col_map.get(
            "symbol",
            df.columns[0]
        )

        eps_col = col_map.get("eps")
        rev_col = col_map.get("rev")
        margin_col = col_map.get("margin")

        for _, row in df.iterrows():

            ticker = str(
                row[symbol_col]
            ).strip().upper()

            if not ticker:
                continue

            tickers.append({

                "symbol": ticker,

                "eps_growth":
                    float(row[eps_col])
                    if eps_col and pd.notna(row[eps_col])
                    else 0,

                "rev_growth":
                    float(row[rev_col])
                    if rev_col and pd.notna(row[rev_col])
                    else 0,

                "margin":
                    float(row[margin_col])
                    if margin_col and pd.notna(row[margin_col])
                    else 0
            })

        print(f"CSV 로드 완료 : {len(tickers)}")

        return tickers

    except Exception as e:

        print("CSV 오류:", e)

        return []


# =========================
# yfinance 처리
# =========================

def _flatten_df(df):

    if df is None or df.empty:
        return df

    if isinstance(df.columns, pd.MultiIndex):

        ticker = df.columns.levels[1][0]

        df = df.xs(
            ticker,
            axis=1,
            level=1
        )

    return df
    # =========================
# SUPERTREND
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

    atr = pd.Series(tr).ewm(
        alpha=1 / period,
        adjust=False
    ).mean().values

    hl2 = (high + low) / 2

    upper = hl2 + mult * atr
    lower = hl2 - mult * atr

    final_upper = upper.copy()
    final_lower = lower.copy()

    trend = np.ones(
        n,
        dtype=bool
    )

    for i in range(1, n):

        if close[i - 1] <= final_upper[i - 1]:
            final_upper[i] = min(
                upper[i],
                final_upper[i - 1]
            )
        else:
            final_upper[i] = upper[i]

        if close[i - 1] >= final_lower[i - 1]:
            final_lower[i] = max(
                lower[i],
                final_lower[i - 1]
            )
        else:
            final_lower[i] = lower[i]

        if close[i] > final_upper[i - 1]:
            trend[i] = True

        elif close[i] < final_lower[i - 1]:
            trend[i] = False

        else:
            trend[i] = trend[i - 1]

    df = df.copy()

    df["trend"] = trend

    return df


# =========================
# RS 점수
# =========================

def get_rs_score(df):

    if len(df) < 126:
        return 0

    rs = (
        (
            df["Close"].iloc[-1]
            / df["Close"].iloc[-126]
        ) - 1
    ) * 100

    if rs >= 150:
        return 40

    elif rs >= 100:
        return 35

    elif rs >= 70:
        return 30

    elif rs >= 40:
        return 20

    elif rs >= 20:
        return 10

    return 0


# =========================
# 52주 고점 위치
# =========================

def get_position_score(df):

    if len(df) < 252:
        return 0

    high52 = (
        df["High"]
        .rolling(252)
        .max()
        .iloc[-1]
    )

    pos = (
        df["Close"].iloc[-1]
        / high52
    )

    if pos >= 0.95:
        return 20

    elif pos >= 0.90:
        return 15

    elif pos >= 0.80:
        return 10

    return 0


# =========================
# EPS 점수
# =========================

def score_eps(eps):

    if eps >= 200:
        return 20

    elif eps >= 100:
        return 18

    elif eps >= 50:
        return 15

    elif eps >= 20:
        return 10

    return 0


def score_rev(rev):

    if rev >= 50:
        return 10

    elif rev >= 30:
        return 8

    elif rev >= 10:
        return 5

    return 0


def score_margin(margin):

    if margin >= 30:
        return 10

    elif margin >= 20:
        return 8

    elif margin >= 10:
        return 5

    return 0


# =========================
# 성장 점수
# =========================

def get_growth_score(info):

    eps = score_eps(
        info.get("eps_growth", 0)
    )

    rev = score_rev(
        info.get("rev_growth", 0)
    )

    margin = score_margin(
        info.get("margin", 0)
    )

    return eps + rev + margin


# =========================
# 추세추종 신호
# =========================

def check_trend_signal(df):

    if len(df) < 60:
        return False, None

    close = float(
        df["Close"].iloc[-1]
    )

    ma20 = float(
        df["Close"]
        .rolling(20)
        .mean()
        .iloc[-1]
    )

    ma50 = float(
        df["Close"]
        .rolling(50)
        .mean()
        .iloc[-1]
    )

    high20 = float(
        df["High"]
        .shift(1)
        .rolling(20)
        .max()
        .iloc[-1]
    )

    uptrend = ma20 > ma50

    breakout = (
        uptrend
        and close > high20
    )

    pullback = (
        uptrend
        and abs(close - ma20)
        / ma20
        < 0.03
        and not breakout
    )

    if breakout:
        return True, "BREAKOUT"

    if pullback:
        return True, "PULLBACK"

    return False, None


# =========================
# 슈퍼트렌드 전환
# =========================

def check_supertrend_signal(df):

    if len(df) < 80:
        return False

    df = calculate_supertrend(df)

    prev = bool(
        df["trend"].iloc[-2]
    )

    curr = bool(
        df["trend"].iloc[-1]
    )

    return (
        not prev
        and curr
    )
    # =========================
# 점수 계산
# =========================

def calculate_breakout_score(df, info):

    rs_score = get_rs_score(df)
    pos_score = get_position_score(df)

    tech_score = rs_score + pos_score + 10

    growth_score = (
        score_eps(info.get("eps_growth", 0))
        + score_rev(info.get("rev_growth", 0))
    )

    total_score = round(
        (tech_score * 0.7)
        + (growth_score * 0.3),
        1
    )

    return total_score, tech_score, growth_score


def calculate_pullback_score(df, info):

    rs_score = get_rs_score(df)

    tech_score = min(rs_score, 25) + 25

    growth_score = (
        score_eps(info.get("eps_growth", 0))
        + score_rev(info.get("rev_growth", 0))
    )

    total_score = round(
        (tech_score * 0.5)
        + (growth_score * 0.5),
        1
    )

    return total_score, tech_score, growth_score


def calculate_supertrend_score(df, info):

    growth_score = get_growth_score(info)

    rs_score = min(
        get_rs_score(df),
        20
    )

    tech_score = rs_score + 10

    total_score = round(
        (tech_score * 0.3)
        + (growth_score * 0.7),
        1
    )

    return total_score, tech_score, growth_score


# =========================
# 텔레그램 출력
# =========================

def send_top10(title, results):

    if not results:

        send_telegram(
            f"📊 {title}\n신호 없음"
        )

        return

    results = sorted(
        results,
        key=lambda x: x["total_score"],
        reverse=True
    )[:10]

    msg = f"🏆 *{title}*\n\n"

    for i, s in enumerate(results, 1):

        msg += (
            f"{i}. *{s['ticker']}*\n"
            f"총점 {s['total_score']:.1f}\n"
            f"기술 {s['tech_score']:.1f}\n"
            f"성장 {s['growth_score']:.1f}\n"
            f"가격 ${s['price']:.2f}\n"
            f"EPS {s['eps']:.0f}%\n"
            f"매출 {s['rev']:.0f}%\n\n"
        )

    send_telegram(msg)


# =========================
# 결과 저장
# =========================

def build_result(
    ticker,
    price,
    info,
    total_score,
    tech_score,
    growth_score
):

    return {

        "ticker": ticker,

        "price": price,

        "eps": info.get(
            "eps_growth",
            0
        ),

        "rev": info.get(
            "rev_growth",
            0
        ),

        "margin": info.get(
            "margin",
            0
        ),

        "total_score": total_score,

        "tech_score": tech_score,

        "growth_score": growth_score
    }
    # =========================
# 추세추종 스캔
# =========================

def scan_trend():

    print("\n🔥 추세추종 스캔 시작")

    ticker_infos = load_tickers_with_fundamentals(
        TREND_CSV
    )

    breakout_results = []
    pullback_results = []

    sent_signals = load_sent_signals()

    today = str(date.today())

    for info in ticker_infos:

        ticker = info["symbol"]

        try:

            df = yf.download(
                ticker,
                period="1y",
                interval="1d",
                auto_adjust=True,
                progress=False
            )

            if df.empty:
                continue

            df = _flatten_df(df)

            signal, detail = check_trend_signal(df)

            if not signal:
                continue

            key = (
                ticker,
                detail,
                today
            )

            if key in sent_signals:
                continue

            price = float(
                df["Close"].iloc[-1]
            )

            if detail == "BREAKOUT":

                total_score, tech_score, growth_score = (
                    calculate_breakout_score(
                        df,
                        info
                    )
                )

                breakout_results.append(

                    build_result(
                        ticker,
                        price,
                        info,
                        total_score,
                        tech_score,
                        growth_score
                    )
                )

            elif detail == "PULLBACK":

                total_score, tech_score, growth_score = (
                    calculate_pullback_score(
                        df,
                        info
                    )
                )

                pullback_results.append(

                    build_result(
                        ticker,
                        price,
                        info,
                        total_score,
                        tech_score,
                        growth_score
                    )
                )

            sent_signals.add(key)

            print(
                f"{ticker} {detail}"
            )

            time.sleep(0.2)

        except Exception as e:

            print(
                ticker,
                e
            )

    save_sent_signals(
        sent_signals
    )

    send_top10(
        "🔥 BREAKOUT TOP10",
        breakout_results
    )

    send_top10(
        "📉 PULLBACK TOP10",
        pullback_results
    )


# =========================
# 슈퍼트렌드 스캔
# =========================

def scan_supertrend():

    print("\n🔄 Supertrend 스캔 시작")

    ticker_infos = load_tickers_with_fundamentals(
        SUPERTREND_CSV
    )

    supertrend_results = []

    sent_signals = load_sent_signals()

    today = str(date.today())

    for info in ticker_infos:

        ticker = info["symbol"]

        try:

            df = yf.download(
                ticker,
                period="1y",
                interval="1d",
                auto_adjust=True,
                progress=False
            )

            if df.empty:
                continue

            df = _flatten_df(df)

            signal = (
                check_supertrend_signal(df)
            )

            if not signal:
                continue

            key = (
                ticker,
                "SUPERTREND",
                today
            )

            if key in sent_signals:
                continue

            price = float(
                df["Close"].iloc[-1]
            )

            total_score, tech_score, growth_score = (
                calculate_supertrend_score(
                    df,
                    info
                )
            )

            supertrend_results.append(

                build_result(
                    ticker,
                    price,
                    info,
                    total_score,
                    tech_score,
                    growth_score
                )
            )

            sent_signals.add(key)

            print(
                f"{ticker} SUPERTREND"
            )

            time.sleep(0.2)

        except Exception as e:

            print(
                ticker,
                e
            )

    save_sent_signals(
        sent_signals
    )

    send_top10(
        "🔄 SUPERTREND TOP10",
        supertrend_results
    )


# =========================
# MAIN
# =========================

if __name__ == "__main__":

    print("=" * 50)
    print("🚀 Growth Trend Scanner v2")
    print("=" * 50)

    scan_trend()

    scan_supertrend()

    print("\n✅ 완료")
