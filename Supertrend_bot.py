import requests

# 1. 아까 그 토큰을 여기에 넣으세요
TELEGRAM_TOKEN = "7483920174:AAH_xdfa8273"  
# 2. 챗아이디
CHAT_ID = "6147329612"         

def test_telegram():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": "테스트 메시지입니다. 봇이 정상적으로 작동하고 있습니다! 🚀"
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("성공: 텔레그램으로 메시지를 보냈습니다.")
        else:
            print(f"실패: 서버 응답 코드 {response.status_code}")
            print(f"내용: {response.text}")
    except Exception as e:
        print(f"에러 발생: {e}")

if __name__ == "__main__":
    test_telegram()
