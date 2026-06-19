import requests
import os

# GitHub Secrets에서 API 키를 가져옵니다
API_KEY = os.environ.get("FMP_API_KEY")

if not API_KEY:
    print("❌ FMP_API_KEY 환경변수가 없습니다.")
    exit(1)

# 프로필 엔드포인트 테스트 (가장 기본)
url = f"https://financialmodelingprep.com/api/v3/profile/AAPL?apikey={API_KEY}"

try:
    response = requests.get(url, timeout=10)
    print(f"📡 상태 코드: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        if data:
            print("✅ API 키 정상! 프로필 데이터 수신 성공")
            print(f"회사명: {data[0].get('companyName')}")
            print(f"이익률: {data[0].get('profitMargin')}")
        else:
            print("❌ 데이터가 비어있음")
    else:
        print(f"❌ 오류 응답: {response.text}")
except Exception as e:
    print(f"❌ 요청 실패: {e}")
