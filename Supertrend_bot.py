#!/usr/bin/env python3
import requests
import logging

TOKEN = "8680217169:AAEsF1CloKbbVR40HxkoXtdZ6hLho9o1aGs"
CHAT_ID = "6147329612"

def force_test():
    msg = "🚀 <b>[강제 테스트]</b> 봇이 정상 작동 중입니다."
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    res = requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})
    print(f"텔레그램 응답 상태: {res.status_code}")
    print(f"응답 내용: {res.text}")

if __name__ == "__main__":
    force_test()
