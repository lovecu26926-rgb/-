#!/usr/bin/env python3
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime

# 1. 봇 정보 (주신 토큰을 적용했습니다)
TELEGRAM_TOKEN = "8680217169:AAEsFlCloKbbVR40HxkoXtdZ6hLho9o1aGs"
CHAT_ID = "6147329612"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=20)
        print(f"텔레그램 응답 상태: {res.status_code}")
        print(f"응답 내용: {res.text}")
    except Exception as e:
        print(f"전송 중 오류 발생: {e}")

def run_test():
    # 주식 데이터와 상관없이 봇 연결이 잘 되는지 무조건 테스트
    print("봇 테스트 시작...")
    test_msg = f"🚀 봇 연결 테스트 성공! ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
    send_telegram(test_msg)

if __name__ == "__main__":
    # 일단 연결 테스트부터 진행
    run_test()
