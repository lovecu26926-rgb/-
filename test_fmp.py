import requests
import os

API_KEY = os.environ.get("FMP_API_KEY")

if not API_KEY:
    print("❌ FMP_API_KEY 없음")
    exit(1)

# 1️⃣ stable/profile 테스트
url = f"https://financialmodelingprep.com/stable/profile?symbol=AAPL&apikey={API_KEY}"
response = requests.get(url, timeout=10)

print(f"📡 상태 코드: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    if data:
        print("✅ stable/profile 정상!")
        print(f"회사명: {data[0].get('companyName')}")
        print(f"이익률: {data[0].get('profitMargin')}")
    else:
        print("❌ 데이터 없음")
elif response.status_code == 403:
    print("❌ 403 오류: stable 엔드포인트 접근 권한 없음 (API 키가 유효한지 확인)")
else:
    print(f"❌ 오류 응답: {response.text[:200]}")
