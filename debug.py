import pandas as pd
import yfinance as yf

print("=" * 50)
print("🔍 디버깅 시작")
print("=" * 50)

# 1. 위키피디아 테스트
try:
    print("\n📌 1. 위키피디아 로드 테스트...")
    sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
    nasdaq100 = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")[4]
    
    print(f"   ✅ S&P500 표 로드 성공: {len(sp500)}개 행")
    print(f"   ✅ NASDAQ100 표 로드 성공: {len(nasdaq100)}개 행")
    print(f"   📋 S&P500 첫 5개: {sp500['Symbol'].head(5).tolist()}")
    
    sp_tickers = sp500["Symbol"].tolist()
    nd_tickers = nasdaq100.iloc[:, 0].tolist()
    all_tickers = list(set(sp_tickers + nd_tickers))
    print(f"   📊 통합 티커 수: {len(all_tickers)}개")
    
except Exception as e:
    print(f"   ❌ 위키피디아 로드 실패: {e}")
    exit()

# 2. yfinance 배치 다운로드 테스트 (첫 50개만)
print("\n📌 2. yfinance 다운로드 테스트 (첫 50개)...")
batch = [t.replace(".", "-") for t in all_tickers[:50]]
try:
    data = yf.download(batch, period="1y", progress=False, group_by="ticker", auto_adjust=True)
    
    # 데이터 타입 확인
    print(f"   📦 데이터 타입: {type(data)}")
    print(f"   📊 데이터 컬럼: {data.columns}")
    
    # 실제로 데이터가 있는지 확인
    valid_count = 0
    for t in batch:
        if t in data:
            df = data[t]
            if not df.empty and len(df) > 200:
                valid_count += 1
    print(f"   ✅ 유효한 종목 수: {valid_count} / {len(batch)}개")
    
    # 첫 번째 종목 샘플 출력
    if valid_count > 0:
        first_ticker = [t for t in batch if t in data and not data[t].empty][0]
        print(f"   📈 예시 ({first_ticker}) 최근 종가: {data[first_ticker]['Close'].iloc[-1]:.2f}")
    else:
        print("   ❌ 유효한 데이터가 하나도 없습니다! (yfinance 차단 또는 네트워크 문제)")
        
except Exception as e:
    print(f"   ❌ yfinance 다운로드 실패: {e}")

# 3. 필터 조건 테스트 (조건 완화)
print("\n📌 3. 필터 조건 테스트 (조건 완화)...")
try:
    df = yf.download("AAPL", period="2y", progress=False, auto_adjust=True)
    print(f"   📊 AAPL 데이터 행 수: {len(df)}")
    print(f"   📈 AAPL 평균 거래량: {df['Volume'].mean():.0f}")
    print(f"   📈 AAPL 현재가: {df['Close'].iloc[-1]:.2f}")
    
    ma50 = df['Close'].rolling(50).mean().iloc[-1]
    ma200 = df['Close'].rolling(200).mean().iloc[-1]
    print(f"   📈 AAPL 50일선: {ma50:.2f}, 200일선: {ma200:.2f}")
    print(f"   📈 50 > 200 * 0.9 조건: {ma50 > ma200 * 0.9}")
    
except Exception as e:
    print(f"   ❌ 개별 종목 테스트 실패: {e}")

print("\n" + "=" * 50)
print("✅ 디버깅 완료")
