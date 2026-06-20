import pandas as pd
import numpy as np
import yfinance as yf
import requests
import json
import os
import time

# =========================
# 설정
# =========================
TREND_CSV = "trend_universe.csv"
SUPERTREND_CSV = "supertrend_universe.csv"
FMP_CACHE_FILE = "fundamentals.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 🔥 ROE 필터 (점수엔 미반영, 통과/표시 전용)
# None 이면 필터링 안 함, 숫자면 그 값 미만(ROE 기준) 종목은 결과에서 제외
ROE_MIN_FILTER = 0  # 예: 0 -> ROE가 N/A 이거나 음수면 제외. 끄려면 None으로 변경

# 카테고리별 거래량 방향: True=거래량 높을수록 좋음(돌파 확인), False=낮을수록 좋음(매도세 없음)
VOL_FAVORS_HIGH = {
    "돌파": True,
    "눌림목": False,
    "골든크로스": True,
    "추세전환": True,
}

# 합성 점수 가중치 (RS/모멘텀 : 거래량) - ROE는 점수에 미반영
RS_WEIGHT = 0.6
VOL_WEIGHT = 0.4

# =========================
# 텔레그램
# =========================
def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=10
        )
    except:
        pass

# =========================
# FMP 캐시 로드
# =========================
def load_fmp():
    if not os.path.exists(FMP_CACHE_FILE):
        return {}
    try:
        with open(FMP_CACHE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

fmp_data = load_fmp()

# =========================
# SPY 기준
# =========================
def get_spy_return():
    try:
        spy = yf.download("SPY", period="1y", auto_adjust=True, progress=False)
        if spy is None or spy.empty:
            return 0.0

        close = spy["Close"]
        first = close.iloc[0].item()
        last = close.iloc[-1].item()

        return float((last / first - 1) * 100)
    except:
        return 0.0

SPY_RET = get_spy_return()

# =========================
# RS 계산
# =========================
def calc_rs(df):
    try:
        if df is None or df.empty:
            return None

        close = df["Close"]

        first = close.iloc[0].item()
        last = close.iloc[-1].item()

        stock_ret = (last / first - 1) * 100
        return float(stock_ret - SPY_RET)

    except:
        return None

# =========================
# 거래량 비율 (당일 거래량 / 직전 20일 평균 거래량)
# =========================
def calc_vol_ratio(df):
    try:
        vol = df["Volume"]
        today = vol.iloc[-1].item()
        avg20 = vol.iloc[-21:-1].mean()
        avg20 = avg20.item() if hasattr(avg20, "item") else float(avg20)

        if not avg20:
            return None

        return float(today / avg20)
    except:
        return None

# =========================
# 신호
# =========================
def get_signals(df):
    try:
        close = df["Close"]
        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()
        high20 = df["High"].rolling(20).max().shift(1)

        # yfinance가 단일 티커도 MultiIndex 컬럼을 반환하는 경우가 있어
        # close/high20 등이 1컬럼 DataFrame이 되고 .iloc[-1]이 Series로 나옴.
        # 이를 if문에 바로 넣으면 "truth value of a Series is ambiguous" 에러가 나서
        # 아래 except에 걸려 무조건 빈 리스트가 반환됨 -> 모든 종목이 신호 없음으로 처리되던 버그.
        # .item()으로 스칼라 변환해서 해결.
        c_last = close.iloc[-1].item()
        h20_last = high20.iloc[-1].item()
        ma20_last = ma20.iloc[-1].item()
        ma50_last = ma50.iloc[-1].item()
        ma20_prev = ma20.iloc[-2].item()
        ma50_prev = ma50.iloc[-2].item()

        signals = []

        # 돌파 (완화)
        if c_last > h20_last:
            signals.append("돌파")

        # 눌림목 (완화)
        if ma20_last > ma50_last and c_last < ma20_last:
            signals.append("눌림목")

        # 골든크로스
        if ma20_prev <= ma50_prev and ma20_last > ma50_last:
            signals.append("골든크로스")

        # 추세전환
        if ma20_prev < ma50_prev and ma20_last > ma50_last:
            signals.append("추세전환")

        return signals

    except:
        return []

# =========================
# 모멘텀
# =========================
def momentum_20d(df):
    try:
        return float((df["Close"].iloc[-1].item() / df["Close"].iloc[-20].item() - 1) * 100)
    except:
        return None

# =========================
# 퍼센타일 랭크 (0~100, 높을수록 상위 / None은 제외)
# =========================
def percentile_rank(vals):
    idx_vals = [(i, v) for i, v in enumerate(vals) if v is not None]
    idx_vals.sort(key=lambda x: x[1])
    n = len(idx_vals)
    out = {}
    for rank, (i, v) in enumerate(idx_vals):
        out[i] = (rank / (n - 1) * 100) if n > 1 else 50.0
    return out

# =========================
# 🔥 ROE 필터 통과 여부 (점수에는 미반영, 결과 포함/제외만 결정)
# =========================
def passes_roe_filter(ticker):
    if ROE_MIN_FILTER is None:
        return True

    fund = fmp_data.get(ticker, {})
    roe = fund.get("roe", "N/A")

    if roe == "N/A" or roe is None:
        # 데이터 없는 종목은 필터링하지 않고 통과시킴 (캐시 누락 종목 배제 방지)
        return True

    return roe >= ROE_MIN_FILTER

# =========================
# 합성 점수 (RS/모멘텀 + 거래량 가중) 계산 후 정렬
# ROE는 점수 계산에 포함되지 않음 - 표시/필터 전용
# =========================
def attach_composite_scores(items, category):
    # items: list of [ticker, primary(RS or momentum), vol_ratio]
    primaries = [it[1] for it in items]
    vols = [it[2] for it in items]

    p_rank = percentile_rank(primaries)
    v_rank = percentile_rank(vols)

    favors_high = VOL_FAVORS_HIGH.get(category, True)

    scored = []
    for i, it in enumerate(items):
        ticker, primary, vol_ratio = it
        p_pct = p_rank.get(i, 50.0)
        v_pct = v_rank.get(i, 50.0)
        if not favors_high:
            v_pct = 100.0 - v_pct
        composite = RS_WEIGHT * p_pct + VOL_WEIGHT * v_pct
        scored.append((ticker, primary, vol_ratio, composite))

    scored.sort(key=lambda x: x[3], reverse=True)
    return scored

# =========================
# SCAN
# =========================
def scan():
    trend = pd.read_csv(TREND_CSV)["Symbol"].dropna().tolist()
    supert = pd.read_csv(SUPERTREND_CSV)["Symbol"].dropna().tolist()

    tickers = list(set(trend + supert))

    buckets = {
        "돌파": [],
        "눌림목": [],
        "골든크로스": [],
        "추세전환": []
    }

    print(f"[SCAN] tickers={len(tickers)} | SPY_RS={SPY_RET:.2f}%")
    if ROE_MIN_FILTER is not None:
        print(f"[FILTER] ROE >= {ROE_MIN_FILTER}% 미만 종목 제외 (N/A는 통과)")

    excluded_by_roe = 0

    for t in tickers:
        try:
            # 🔥 ROE 필터 - 신호 계산 전에 먼저 거름 (불필요한 계산 절약)
            if not passes_roe_filter(t):
                excluded_by_roe += 1
                continue

            df = yf.download(t, period="1y", auto_adjust=True, progress=False)

            if df is None or df.empty:
                continue

            rs = calc_rs(df)
            vol_ratio = calc_vol_ratio(df)
            signals = get_signals(df)

            if not signals:
                continue

            for s in signals:
                primary = momentum_20d(df) if s == "추세전환" else rs
                buckets[s].append([t, primary, vol_ratio])

            time.sleep(0.05)

        except:
            continue

    if ROE_MIN_FILTER is not None and excluded_by_roe > 0:
        print(f"[FILTER] ROE 기준 미달로 {excluded_by_roe}개 종목 제외됨")

    # =========================
    # 카테고리별 합성 점수 정렬
    # =========================
    scored_buckets = {}
    for cat in ["돌파", "눌림목", "골든크로스", "추세전환"]:
        scored_buckets[cat] = attach_composite_scores(buckets[cat], cat)

    # =========================
    # 출력
    # =========================
    msg = ""

    for cat in ["돌파", "눌림목", "골든크로스", "추세전환"]:
        msg += f"\n🏆 [{cat}]\n\n"

        items = scored_buckets[cat]

        if not items:
            msg += "없음\n"
            continue

        label = "20D" if cat == "추세전환" else "RS"

        for i, (t, primary, vol_ratio, composite) in enumerate(items, 1):

            fund = fmp_data.get(t, {})
            rev = fund.get("revenue_growth", "N/A")
            eps = fund.get("eps_growth", "N/A")
            roe = fund.get("roe", "N/A")  # 🔥 ROE 표시 추가 (점수엔 미반영)

            vr_str = f"{vol_ratio:.1f}x" if vol_ratio is not None else "N/A"
            primary_str = f"{primary:.1f}" if primary is not None else "N/A"

            msg += (
                f"{i}. {t} | 점수 {composite:.0f} | {label} {primary_str} | 거래량 {vr_str} "
                f"| 매출 {rev} | EPS {eps} | ROE {roe}\n"
            )

    print(msg)
    send_telegram(msg)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    scan()
