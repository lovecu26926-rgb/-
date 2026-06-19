import requests
import os

API_KEY = os.environ.get("FINNHUB_API_KEY")

if not API_KEY:
    API_KEY = "YOUR_FINNHUB_TOKEN_HERE"  # 직접 입력

# AAPL로 테스트
url = f"https://finnhub.io/api/v1/stock/metric?symbol=AAPL&metric=all&token={API_KEY}"
resp = requests.get(url)
print(f"상태 코드: {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    if data and 'metric' in data:
        print("✅ Finnhub 정상!")
        print(f"ROE: {data['metric'].get('roe', '없음')}")
        print(f"이익률: {data['metric'].get('netProfitMargin', '없음')}")
    else:
        print("❌ 데이터 구조 이상")
else:
    print(f"❌ 오류: {resp.text}")
