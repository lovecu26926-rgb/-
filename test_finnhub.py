import requests
import os

API_KEY = os.environ.get("FINNHUB_API_KEY")

if not API_KEY:
    print("❌ FINNHUB_API_KEY 없음")
    exit(1)

# Finnhub 엔드포인트 (꼭 확인!)
url = f"https://finnhub.io/api/v1/stock/metric?symbol=AAPL&metric=all&token={API_KEY}"
resp = requests.get(url, timeout=10)

print(f"📡 상태 코드: {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    if data and 'metric' in data:
        print("✅ Finnhub 정상!")
        print(f"ROE: {data['metric'].get('roe')}")
    else:
        print("❌ 응답 없음")
else:
    print(f"❌ 오류: {resp.text}")
