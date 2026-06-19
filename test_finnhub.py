import requests
import os
import json

# API 키 입력
API_KEY = os.environ.get("FINNHUB_API_KEY")

if not API_KEY:
    API_KEY = "YOUR_FINNHUB_TOKEN_HERE"  # 직접 입력해도 됨

# 대표 종목 5개 테스트
tickers = ["AAPL", "NVDA", "MU", "AMD", "TSLA"]

print("📊 Finnhub API 테스트 시작\n")

for ticker in tickers:
    url = f"https://finnhub.io/api/v1/stock/metric?symbol={ticker}&metric=all&token={API_KEY}"
    
    try:
        resp = requests.get(url, timeout=10)
        print(f"🔹 {ticker} → 상태 코드: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            if data and 'metric' in data:
                metric = data['metric']
                
                # Finnhub는 보통 소수점(0.15)으로 오면 ×100, 이미 퍼센트(15.0)로 오면 그대로
                def get_val(key):
                    val = metric.get(key, None)
                    if val is None:
                        return "없음"
                    if isinstance(val, (int, float)):
                        if -1 < val < 1:
                            return f"{round(val * 100, 2)}%"
                        else:
                            return f"{round(val, 2)}%"
                    return str(val)
                
                rev = get_val('revenueGrowth')
                eps = get_val('epsGrowth')
                
                print(f"   📈 매출 성장: {rev}")
                print(f"   📈 EPS 성장: {eps}")
                print(f"   📦 metric 키 개수: {len(metric)}개")
                print()
            else:
                print("   ❌ 'metric' 필드 없음\n")
        else:
            print(f"   ❌ 오류 응답: {resp.text[:100]}\n")
            
    except Exception as e:
        print(f"   ❌ 예외 발생: {e}\n")
