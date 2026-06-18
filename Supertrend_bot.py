import pandas as pd
import yfinance as yf
import time

# =========================
# 1. 거래소 전체 종목 가져오기
# =========================
def get_universe():
    nasdaq = pd.read_csv(
        "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt",
        sep="|"
    )

    nyse = pd.read_csv(
        "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
        sep="|"
    )

    nasdaq = nasdaq[nasdaq["Test Issue"] == "N"]
    nyse = nyse[nyse["Test Issue"] == "N"]

    tickers = set()
    tickers.update(nasdaq["Symbol"].dropna())
    tickers.update(nyse["ACT Symbol"].dropna())

    return list(tickers)


# =========================
# 2. 거래대금 계산
# =========================
def get_dollar_volume(ticker):
    try:
        df = yf.download(ticker, period="1mo", interval="1d", progress=False)

        if df is None or len(df) < 10:
            return None

        price = df["Close"].iloc[-1]

        if price < 1:
            return None

        dollar_vol = (df["Close"] * df["Volume"]).mean()

        return dollar_vol

    except:
        return None


# =========================
# 3. TOP 1000 생성
# =========================
def build_top_1000():
    universe = get_universe()

    results = []

    print(f"Total universe: {len(universe)}")

    for i, t in enumerate(universe):

        vol = get_dollar_volume(t)

        if vol is None:
            continue

        results.append((t, vol))

        # 진행 로그
        if i % 200 == 0:
            print(f"Processed: {i}/{len(universe)}")

        time.sleep(0.1)

    # 거래대금 기준 정렬 (상위 = 유동성 큰 종목)
    results.sort(key=lambda x: x[1], reverse=True)

    top_1000 = [x[0] for x in results[:1000]]

    return top_1000


# =========================
# 4. 실행 + 저장
# =========================
if __name__ == "__main__":

    top = build_top_1000()

    df = pd.DataFrame(top, columns=["ticker"])
    df.to_csv("top1000_universe.csv", index=False)

    print("\n🔥 TOP 1000 GENERATED")
    print(f"Saved: top1000_universe.csv")
