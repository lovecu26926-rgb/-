# ==========================
# 3대 지수 수집 (위키피디아 통합 - 문법 오류 수정본)
# ==========================
def get_integrated_universe():
    tickers = set()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    # 1. S&P 500
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        req = requests.get(url, headers=headers, timeout=15)
        table = pd.read_html(req.text)[0]
        for sym in table['Symbol'].dropna():
            # 문법 오류 수정: regex=False 제거
            symbol = str(sym).strip().replace('.', '-')
            if symbol and not any(c in symbol for c in ['$', '.']):
                tickers.add(symbol)
        logging.info(f"S&P 500 수집 완료 (누적: {len(tickers)}개)")
    except Exception as e:
        logging.error(f"S&P 500 위키 수집 에러: {e}")

    # 2. NASDAQ 100
    try:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        req = requests.get(url, headers=headers, timeout=15)
        tables = pd.read_html(req.text)
        for table in tables:
            if 'Ticker' in table.columns:
                for sym in table['Ticker'].dropna():
                    symbol = str(sym).strip()
                    if symbol and not any(c in symbol for c in ['$', '.']):
                        tickers.add(symbol)
                break
        logging.info(f"NASDAQ 100 수집 완료 (누적: {len(tickers)}개)")
    except Exception as e:
        logging.error(f"NASDAQ 100 위키 수집 에러: {e}")

    # 3. Russell 1000
    try:
        url = "https://en.wikipedia.org/wiki/Russell_1000_Index"
        req = requests.get(url, headers=headers, timeout=15)
        tables = pd.read_html(req.text)
        for table in tables:
            if 'Symbol' in table.columns:
                for sym in table['Symbol'].dropna():
                    # 문법 오류 수정: regex=False 제거
                    symbol = str(sym).strip().replace('.', '-')
                    if symbol and not any(c in symbol for c in ['$', '.']):
                        tickers.add(symbol)
        logging.info(f"Russell 1000 수집 완료 (중복제거 최종 합계: {len(tickers)}개)")
    except Exception as e:
        logging.error(f"Russell 1000 위키 수집 에러: {e}")

    return sorted(list(tickers))
