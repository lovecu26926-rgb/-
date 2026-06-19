import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import time
from datetime import datetime, date
import pytz
import warnings

warnings.filterwarnings('ignore')

# ==========================================
# 🔐 환경변수
# ==========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

ST_CSV_URL = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"
TREND_CSV_URL = "https://raw.githubusercontent.com/lovecu26926-rgb/-/main/trend_universe.csv"

# ==========================================
# 📂 텔레그램 및 유틸리티
# ==========================================
def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[텔레그램 전송 대기]\n{message}\n")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}, timeout=5)
    except Exception as e:
        print(f"❌ 전송 실패: {e}")

SIGNALS_FILE = "sent_signals_action.json"
def load_sent_signals():
    today = str(date.today())
    if os.path.exists(SIGNALS_FILE):
        try:
            with open(SIGNALS_FILE, 'r') as f:
                data =
