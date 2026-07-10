import pandas as pd
import numpy as np
import yfinance as yf


# -------------------------------------------------
# 이동평균
# -------------------------------------------------
def add_ma(df):
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()
    return df


# -------------------------------------------------
# RS 계산 (SPY 대비)
# -------------------------------------------------
def add_rs(df, spy_df):
    stock_ret = df["Close"].pct_change(252)
    spy_ret = spy_df["Close"].pct_change(252)

    rs = (stock_ret - spy_ret) * 100

    df["RS"] = rs.reindex(df.index)
    return df


# -------------------------------------------------
# 거래량 비율
# -------------------------------------------------
def add_volume_ratio(df):
    df["VOL_RATIO"] = (
        df["Volume"] /
        df["Volume"].rolling(20).mean()
    )
    return df


# -------------------------------------------------
# 돌파
# -------------------------------------------------
def breakout_signal(df):

    high_50 = df["High"].rolling(50).max()

    signal = (
        (df["Close"] >= high_50.shift(1) * 0.995)
        & (df["Volume"] > df["Volume"].rolling(20).mean() * 1.5)
        & (df["EMA20"] > df["EMA50"])
        & (df["EMA50"] > df["EMA200"])
        & (df["RS"] > 0)
    )

    return signal


# -------------------------------------------------
# 20일선 눌림목
# -------------------------------------------------
def pullback20_signal(df):

    dist20 = abs(df["Close"] / df["EMA20"] - 1)

    signal = (
        (df["EMA20"] > df["EMA50"])
        & (df["EMA50"] > df["EMA200"])
        & (dist20 <= 0.03)
        & (df["Close"] > df["EMA20"])
        & (df["RS"] > 0)
    )

    return signal


# -------------------------------------------------
# 50일선 눌림목
# -------------------------------------------------
def pullback50_signal(df):

    dist50 = abs(df["Close"] / df["EMA50"] - 1)

    signal = (
        (df["EMA20"] > df["EMA50"])
        & (df["EMA50"] > df["EMA200"])
        & (dist50 <= 0.05)
        & (df["Close"] > df["EMA50"])
        & (df["RS"] > 0)
    )

    return signal


# -------------------------------------------------
# 카테고리 판정
# -------------------------------------------------
def classify(df):

    b = breakout_signal(df)
    p20 = pullback20_signal(df)
    p50 = pullback50_signal(df)

    latest = len(df) - 1

    if b.iloc[latest]:
        return "돌파"

    if p20.iloc[latest]:
        return "20일선 눌림목"

    if p50.iloc[latest]:
        return "50일선 눌림목"

    return "해당없음"


# -------------------------------------------------
# 분석
# -------------------------------------------------
def analyze_ticker(ticker, spy_df):

    df = yf.download(
        ticker,
        period="1y",
        interval="1d",
        progress=False,
        auto_adjust=True
    )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if len(df) < 220:
        return None

    df = add_ma(df)
    df = add_rs(df, spy_df)
    df = add_volume_ratio(df)

    latest = df.iloc[-1]

    dist20 = (latest["Close"] / latest["EMA20"] - 1) * 100
    dist50 = (latest["Close"] / latest["EMA50"] - 1) * 100

    return {
        "ticker": ticker,
        "category": classify(df),
        "close": round(latest["Close"], 2),
        "dist20": round(dist20, 1),
        "dist50": round(dist50, 1),
        "rs": round(latest["RS"], 1),
        "vol_ratio": round(latest["VOL_RATIO"], 2),
    }


# -------------------------------------------------
# 실행
# -------------------------------------------------
if __name__ == "__main__":

    watchlist = [
        "NVDA",
        "MU",
        "LRCX",
        "KLAC",
        "SOXX",
        "QQQ",
        "IWM",
    ]

    spy_df = yf.download(
        "SPY",
        period="1y",
        interval="1d",
        progress=False,
        auto_adjust=True
    )

    if isinstance(spy_df.columns, pd.MultiIndex):
        spy_df.columns = spy_df.columns.get_level_values(0)

    results = []

    for ticker in watchlist:

        result = analyze_ticker(ticker, spy_df)

        if result:
            results.append(result)

    results = pd.DataFrame(results)

    print(results.sort_values("rs", ascending=False).to_string(index=False))
