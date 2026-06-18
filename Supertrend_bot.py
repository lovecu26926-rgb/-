#!/usr/bin/env python3
"""
Supertrend Alert Bot - 종목 하드코딩 버전
"""

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import logging
from datetime import datetime
import pytz

TELEGRAM_TOKEN = "8680217169:AAEsFlCloKbbVR40HxkoXtdZ6hLho9o1aGs"
CHAT_ID = "6147329612"

ST_PERIOD = 10
ST_MULTIPLIER = 3.0
MIN_PRICE = 1.0
MIN_ADR = 5.0
MIN_PERF_3M = 0.0
MIN_PERF_6M = 0.0
MIN_PERF_1Y = 0.0
MIN_AVG_VOL_30D = 50_000_000
MIN_TODAY_VOL = 20_000_000
MIN_EPS_GROWTH = 20.0

MARKET_TZ = pytz.timezone("America/New_York")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# S&P500 + NASDAQ100 종목 하드코딩
UNIVERSE = list(set([
    "AAPL","MSFT","NVDA","AMZN","GOOGL","GOOG","META","TSLA","BRK-B","UNH",
    "XOM","JNJ","JPM","V","PG","MA","HD","CVX","MRK","ABBV","PEP","KO","AVGO",
    "COST","LLY","TMO","MCD","ABT","ACN","DHR","CSCO","ADBE","WMT","CRM","NKE",
    "BAC","DIS","NFLX","CMCSA","VZ","INTC","AMD","QCOM","TXN","AMGN","HON",
    "PM","UPS","RTX","LIN","SBUX","MDT","BLK","ISRG","SPGI","CAT","ELV","DE",
    "GILD","BKNG","PLD","SYK","MDLZ","ADP","CB","TJX","MO","REGN","MMC","SO",
    "ZTS","BMY","CI","HCA","AON","DUK","APD","NSC","EMR","ITW","ICE","PYPL",
    "EQIX","CSX","MPC","PGR","EOG","SHW","WM","FCX","MCO","CL","ORLY","EW",
    "CEG","PCAR","PSA","AIG","OXY","MET","AFL","ECL","CTVA","MNST","KLAC",
    "LRCX","MCHP","AMAT","NXPI","ADI","SNPS","CDNS","FTNT","PANW","CRWD",
    "MU","ORCL","NOW","WDAY","TEAM","ZS","DDOG","NET","OKTA","SNOW","PLTR",
    "UBER","ABNB","DASH","RBLX","COIN","SQ","HOOD","SOFI","AFRM","UPST",
    "LCID","RIVN","F","GM","STLA","TM","HMC","RACE","VWAGY",
    "GS","MS","WFC","C","USB","PNC","TFC","COF","AXP","SCHW","BK","STT",
    "AMT","PLD","EQIX","CCI","SBAC","DLR","PSA","EXR","AVB","EQR",
    "LMT","BA","GD","NOC","RTX","L3H","HII","TDG","HEICO","TransDigm",
    "CVS","WBA","MCK","ABC","CAH","HUM","CNC","MOH","WCG",
    "NEE","DUK","SO","AEP","EXC","SRE","PEG","ED","ES","FE",
    "AMZ","SHOP","SE","MELI","PDD","BABA","JD","TCEHY","NTES",
    "SPOT","SNAP","PINS","TWTR","ZM","DOCU","BILL","HUBS","SMAR",
    "SPG","O","VICI","MGM","LVS","WYNN","CZR","PENN","DKNG",
    "DAL","UAL","AAL","LUV","ALK","JBLU","SAVE","HA",
    "CCL","RCL","NCLH","MAR","HLT","H","IHG","WH","CHH",
    "YUM","QSR","DPZ","CMG","JACK","DRI","EAT","TXRH","WING",
    "NKE","VFC","PVH","RL","TPR","HBI","UA","LULU","ONON","CROX",
    "TSCO","LOW","TGT","BBY","ETSY","EBAY","AMZN","W","CHWY",
    "ISRG","BSX","EW","SYK","ZBH","HOLX","IDXX","WAT","A","BIO",
    "LH","DGX","IQV","CRL","CTLT","PKI","QGEN","MTD","BRKR",
    "PFE","LLY","MRK","AZN","GSK","NVO","SNY","RHHBY","BAYRY",
    "MRNA","BNTX","NVAX","VXRT","OCGN","INO","SGEN","ALNY","BMRN",
    "BIIB","VRTX","REGN","ILMN","EXAS","NTRA","GH","PACB","TWST",
    "GE","MMM","HON","ETN","EMR","ROK","PH","IR","AME","ROP",
    "CARR","OTIS","JCI","TT","LEN","DHI","PHM","NVR","TOL","MDC",
    "X","NUE","STLD","CLF","RS","ATI","CMC","WOR","ZEUS","HAYN",
    "FCX","AA","CENX","KALU","ARNC","HBM","TECK","RIO","BHP","VALE",
    "SLB","HAL","BKR","NOV","FTI","RIG","NE","HP","PTEN","PUMP",
    "COP","PXD","DVN","FANG","MRO","APA","OVV","SM","CPE","CDEV",
    "KMI","WMB","OKE","ET","EPD","MMP","PAGP","TRGP","DT","AM",
    "SBUX","DNKN","PEET","BROS","THI","QSR","MCD","WEN","JACK",
    "AAPL","MSFT","GOOG","AMZN","META","TSLA","NVDA","NFLX","ADBE",
    "CRM","NOW","WDAY","VEEV","HUBS","DDOG","SNOW","PLTR","MDB","ESTC",
    "SOXX","QQQ","SPY","IWM","DIA","GLD","SLV","USO","UNG","TLT",
    "MRVL","QCOM","TXN","ADI","MCHP","NXPI","SWKS","QRVO","CRUS","SLAB",
    "AMAT","LRCX","KLAC","ASML","ONTO","COHU","ACLS","FORM","UCTT","ICHR",
    "TSM","INTC","AMD","NVDA","MU","WDC","STX","NTAP","PSTG","VNET",
    "DELL","HPQ","HPE","LNVGY","SMCI","IIVI","II-VI","CIEN","LITE","AAON",
    "GOOGL","GOOG","META","SNAP","PINS","TWTR","MTCH","BMBL","GRND",
    "UBER","LYFT","DASH","CART","ABNB","VRBO","TRIP","EXPE","BKNG",
    "SFM","CASY","WMK","SVU","GO","IMKTA","WFCL","KR","ACI","SWY",
    "COST","WMT","TGT","DLTR","DG","BJ","PSMT","TUES","FIVE","OLLI",
    "CVS","WAG","RAD","ESRX","MHS","CTRX","WMGI","PDCO","HSIC","XRAY",
    "ACM","EME","PWR","MTZ","DY","MYR","PRIM","WLDN","ROAD","MYRG",
    "URI","RSG","WCN","CWST","SRCL","HCCI","ECOL","CLH","CECO","MEG",
    "AYI","ACCO","HNI","KNOLL","SCS","UFI","MLAB","FORM","NATI","TRMB",
    "TDC","NCNO","APPN","APPF","PCTY","PAYC","PAYX","ADP","G","EFX",
    "TRI","VRSK","CLGX","FAF","FNF","STC","ITIC","FNFI","TFSL","ESNT",
    "PB","PPBI","CVBF","WAFD","HOPE","HAFC","BANC","BUSE","NBTB","SRCE",
    "BOKF","IBCP","QCRH","HTLF","FBIZ","FULT","WSBC","CNOB","FNLC","BRKL",
    "INTU","H&R","TRU","EXL","EXLS","EPAM","GLOB","CTSH","IT","ACN",
    "IBM","CSC","DXC","LDOS","SAIC","BAH","CACI","MANT","KEYW","PRGX",
][:600]))

def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calc_atr(high, low, close, period):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def calc_supertrend(high, low, close, period=10, multiplier=3.0):
    atr = calc_atr(high, low, close, period)
    hl2 = (high + low) / 2
    
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr
    
    upper = basic_upper.copy()
    lower = basic_lower.copy()
    direction = pd.Series(0, index=close.index)
    
    for i in range(1, len(close)):
        upper.iloc[i] = basic_upper.iloc[i] if basic_upper.iloc[i] < upper.iloc[i-1] or close.iloc[i-1] > upper.iloc[i-1] else upper.iloc[i-1]
        lower.iloc[i] = basic_lower.iloc[i] if basic_lower.iloc[i] > lower.iloc[i-1] or close.iloc[i-1] < lower.iloc[i-1] else lower.iloc[i-1]
        
        if direction.iloc[i-1] == 1:
            direction.iloc[i] = 1 if close.iloc[i] > lower.iloc[i] else -1
        else:
            direction.iloc[i] = -1 if close.iloc[i] < upper.iloc[i] else 1
    
    return direction

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
        logging.info("텔레그램 전송 성공" if r.status_code == 200 else f"오류: {r.text}")
    except Exception as e:
        logging.error(f"텔레그램 예외: {e}")

def check_ticker(ticker):
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="1y", interval="1d")
        if hist is None or len(hist) < 70:
            return None

        close = hist["Close"]
        volume = hist["Volume"]
        high = hist["High"]
        low = hist["Low"]
        price = close.iloc[-1]

        if price < MIN_PRICE: return None

        adr = ((high.tail(5) - low.tail(5)) / low.tail(5) * 100).mean()
        if adr < MIN_ADR: return None

        def perf(days):
            idx = max(0, len(close) - days)
            past = close.iloc[idx]
            return (price - past) / past * 100 if past > 0 else -999

        if perf(63) < MIN_PERF_3M: return None
        if perf(126) < MIN_PERF_6M: return None
        if perf(252) < MIN_PERF_1Y: return None

        ema8  = calc_ema(close, 8)
        ema21 = calc_ema(close, 21)
        ema60 = calc_ema(close, 60)
        if ema8.iloc[-1] <= ema21.iloc[-1]: return None
        if price <= ema60.iloc[-1]: return None

        avg_dv = (close.tail(30) * volume.tail(30)).mean()
        today_dv = price * volume.iloc[-1]
        if avg_dv < MIN_AVG_VOL_30D: return None
        if today_dv < MIN_TODAY_VOL: return None

        info = tk.info
        eps_g = info.get("earningsQuarterlyGrowth") or info.get("earningsGrowth")
        if eps_g is None or eps_g * 100 < MIN_EPS_GROWTH: return None

        direction = calc_supertrend(high, low, close, ST_PERIOD, ST_MULTIPLIER)
        if len(direction) < 2: return None

        curr = int(direction.iloc[-1])
        prev = int(direction.iloc[-2])
        if curr == prev: return None
        if curr != 1: return None  # 1 = 상승 전환

        return {
            "ticker": ticker,
            "price": price,
            "adr": round(adr, 1),
            "eps_growth": round(eps_g * 100, 1),
            "perf_3m": round(perf(63), 1),
        }

    except Exception as e:
        logging.debug(f"{ticker} 오류: {e}")
        return None

def scan():
    now_et = datetime.now(MARKET_TZ)
    logging.info(f"=== 스캔 시작 {now_et.strftime('%Y-%m-%d %H:%M ET')} ===")

    if now_et.weekday() >= 5:
        logging.info("주말 스킵")
        return

    universe = [t for t in UNIVERSE if t and len(t) <= 5 and t.isalpha() or "-" in t]
    logging.info(f"총 {len(universe)}개 종목 스캔")

    buy_alerts = []
    for i, ticker in enumerate(universe):
        result = check_ticker(ticker)
        if result:
            buy_alerts.append(result)
            logging.info(f"매수 후보: {ticker}")
        if i % 50 == 0:
            logging.info(f"진행: {i}/{len(universe)}")
        time.sleep(0.1)

    date_str = now_et.strftime("%m/%d")
    if buy_alerts:
        lines = [f"<b>📊 슈퍼트렌드 매수 후보 [{date_str}]</b>\n"]
        for a in buy_alerts:
            lines.append(
                f"<b>{a['ticker']}</b>  ${a['price']:.2f}\n"
                f"🟢 상승 전환\n"
                f"ADR {a['adr']}%  EPS {a['eps_growth']}%  3M {a['perf_3m']}%\n"
            )
        send_telegram("\n".join(lines))
    else:
        send_telegram(f"📊 [{date_str}] 오늘 매수 후보 없음")

    logging.info(f"=== 완료. 매수 후보 {len(buy_alerts)}개 ===")

if __name__ == "__main__":
    scan()
