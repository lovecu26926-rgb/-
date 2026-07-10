import yfinance as yf
import pandas as pd

ETF = {
    "SMH": "Semiconductor",
    "XLK": "Technology",
    "QQQ": "Nasdaq",
    "SPY": "Market",
    "IWM": "Small Cap",
    "XLF": "Financial",
    "XLI": "Industrial",
    "XLE": "Energy"
}

# -------------------
# 데이터 다운로드
# -------------------
def get_data(ticker):
    df = yf.download(
        ticker,
        period="6mo",
        auto_adjust=True,
        progress=False
    )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df


# -------------------
# 상대강도
# -------------------
def calc_rs(etf_df, spy_df, days):

    etf_ret = (
        etf_df["Close"].iloc[-1]
        / etf_df["Close"].iloc[-days]
        - 1
    ) * 100

    spy_ret = (
        spy_df["Close"].iloc[-1]
        / spy_df["Close"].iloc[-days]
        - 1
    ) * 100

    return round(etf_ret - spy_ret, 1)


# -------------------
# 시장 상태
# -------------------
def market_stage(spy):

    ma20 = spy["Close"].rolling(20).mean().iloc[-1]
    ma50 = spy["Close"].rolling(50).mean().iloc[-1]
    ma200 = spy["Close"].rolling(200).mean().iloc[-1]

    close = spy["Close"].iloc[-1]

    if close > ma20 > ma50 > ma200:
        return "강세장"

    elif close > ma50:
        return "상승"

    elif close > ma200:
        return "조정"

    else:
        return "약세장"


# -------------------
# 실행
# -------------------
spy = get_data("SPY")

rows = []

for ticker, name in ETF.items():

    df = get_data(ticker)

    rs5 = calc_rs(df, spy, 5)
    rs20 = calc_rs(df, spy, 20)
    rs60 = calc_rs(df, spy, 60)

    rows.append({
        "ETF": ticker,
        "RS_1W": rs5,
        "RS_1M": rs20,
        "RS_3M": rs60
    })

result = pd.DataFrame(rows)

# 1개월 RS 기준 정렬
result = result.sort_values(
    "RS_1M",
    ascending=False
)

print("\n========================")
print("MARKET FLOW")
print("========================")

print(
    f"\n시장상태 : {market_stage(spy)}"
)

print("\nETF 순위\n")

print(result.to_string(index=False))
