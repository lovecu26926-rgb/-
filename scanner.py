import pandas as pd
import numpy as np
import yfinance as yf
import requests
import os
import time

# =========================
# 설정
# =========================
TREND_CSV = "trend_universe.csv"
SUPERTREND_CSV = "supertrend_universe.csv"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 카테고리별 거래량 방향
VOL_FAVORS_HIGH = {
    "돌파": True,
    "눌림목": False,
    "골든크로스": True,
    "추세전환": True,
}

# 카테고리별 가중치 (RS/모멘텀 : 거래량)
CATEGORY_WEIGHTS = {
    "돌파":      {"rs": 0.5, "vol": 0.5},
    "눌림목":    {"rs": 0.7, "vol": 0.3},
    "골든크로스": {"rs": 0.6, "vol": 0.4},
    "추세전환":  {"rs": 0.7, "vol": 0.3},
}

# 추세전환 거래량 하드필터 (1.3배 미만 제외)
TREND_REVERSAL_MIN_VOL_RATIO = 1.3

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
# SPY 기준 (1년 수익률)
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
# RS 계산 (SPY 대비 초과 수익률)
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
# 거래량 비율 (당일 / 20일 평균)
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
# 신호 감지 (돌파, 눌림목, 골든크로스, 추세전환)
# =========================
def get_signals(df):
    try:
        close = df["Close"]
        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()
        high20 = df["High"].rolling(20).max().shift(1)

        c_last = close.iloc[-1].item()
        h20_last = high20.iloc[-1].item()
        ma20_last = ma20.iloc[-1].item()
        ma50_last = ma50.iloc[-1].item()
        ma20_prev = ma20.iloc[-2].item()
        ma50_prev = ma50.iloc[-2].item()

        signals = []

        # 돌파
        if c_last > h20_last:
            signals.append("돌파")

        # 눌림목
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
# 20일 모멘텀
# =========================
def momentum_20d(df):
    try:
        return float((df["Close"].iloc[-1].item() / df["Close"].iloc[-20].item() - 1) * 100)
    except:
        return None

# =========================
# 퍼센타일 랭크 (0~100)
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
# 합성 점수 계산
# =========================
def attach_composite_scores(items, category):
    primaries = [it[1] for it in items]
    vols = [it[2] for it in items]

    p_rank = percentile_rank(primaries)
    v_rank = percentile_rank(vols)

    favors_high = VOL_FAVORS_HIGH.get(category, True)
    weights = CATEGORY_WEIGHTS.get(category, {"rs": 0.6, "vol": 0.4})
    rs_w = weights["rs"]
    vol_w = weights["vol"]

    scored = []
    for i, it in enumerate(items):
        ticker, primary, vol_ratio, price = it
        p_pct = p_rank.get(i, 50.0)
        v_pct = v_rank.get(i, 50.0)
        if not favors_high:
            v_pct = 100.0 - v_pct
        composite = rs_w * p_pct + vol_w * v_pct
        scored.append((ticker, primary, vol_ratio, price, composite))

    scored.sort(key=lambda x: x[4], reverse=True)
    return scored

# =========================
# 🔥 CSV 클리너 (%, USD, 쉼표 제거)
# =========================
def clean_numeric(val):
    if isinstance(val, str):
        val = val.replace('%', '').replace(' USD', '').replace(',', '').strip()
        if val == '':
            return float('nan')
        try:
            return float(val)
        except ValueError:
            return float('nan')
    return val

# =========================
# CSV 재무 데이터 로드
# =========================
def load_fundamentals():
    df1 = pd.read_csv(TREND_CSV, encoding='utf-8-sig')
    df2 = pd.read_csv(SUPERTREND_CSV, encoding='utf-8-sig')

    df = pd.concat([df1, df2], ignore_index=True)
    df = df.drop_duplicates(subset=["Symbol"])

    numeric_cols = [
        "EPS Growth TTM YoY",
        "Revenue Growth TTM YoY",
        "Reported EPS FY",
        "Estimated EPS FY",
        "ROE",
        "Target Price 1Y"
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].apply(clean_numeric)

    return df.set_index("Symbol").to_dict("index")

# =========================
# SCAN
# =========================
def scan():
    fund_map = load_fundamentals()

    trend = pd.read_csv(TREND_CSV, encoding='utf-8-sig')["Symbol"].dropna().tolist()
    supert = pd.read_csv(SUPERTREND_CSV, encoding='utf-8-sig')["Symbol"].dropna().tolist()

    tickers = list(set(trend + supert))

    buckets = {
        "돌파": [],
        "눌림목": [],
        "골든크로스": [],
        "추세전환": []
    }

    print(f"[SCAN] tickers={len(tickers)} | SPY_RS={SPY_RET:.2f}%")

    for t in tickers:
        try:
            df = yf.download(t, period="1y", auto_adjust=True, progress=False)
            if df is None or df.empty:
                continue

            rs = calc_rs(df)
            vol_ratio = calc_vol_ratio(df)
            signals = get_signals(df)

            if not signals:
                continue

            current_price = float(df["Close"].iloc[-1])

            for s in signals:
                primary = momentum_20d(df) if s == "추세전환" else rs

                if s == "추세전환":
                    if vol_ratio is None or vol_ratio < TREND_REVERSAL_MIN_VOL_RATIO:
                        continue

                buckets[s].append((t, primary, vol_ratio, current_price))

            time.sleep(0.2)

        except Exception as e:
            continue

    print(f"[FILTER] 추세전환 거래량 < {TREND_REVERSAL_MIN_VOL_RATIO}x 제외")

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

        for i, (t, primary, vol_ratio, current_price, composite) in enumerate(items, 1):
            f = fund_map.get(t, {})

            eps_yoy = f.get("EPS Growth TTM YoY")
            rev_yoy = f.get("Revenue Growth TTM YoY")
            reported_eps = f.get("Reported EPS FY")
            estimated_eps = f.get("Estimated EPS FY")
            roe = f.get("ROE")
            target_price = f.get("Target Price 1Y")

            # EPS Forward 계산
            eps_fwd = None
            if (
                pd.notna(reported_eps)
                and pd.notna(estimated_eps)
                and reported_eps != 0
            ):
                eps_fwd = ((estimated_eps - reported_eps) / abs(reported_eps)) * 100

            # TP 상승률 계산
            tp = None
            if (
                pd.notna(target_price)
                and current_price > 0
            ):
                tp = ((target_price - current_price) / current_price) * 100

            # 성장 태그
            growth_tag = ""
            if isinstance(eps_yoy, (int, float)) and eps_yoy > 200:
                growth_tag = "🔥"
            elif (
                isinstance(eps_yoy, (int, float))
                and isinstance(eps_fwd, (int, float))
                and eps_yoy >= 10
                and eps_fwd >= 10
            ):
                accel = eps_fwd / eps_yoy
                if accel >= 1.3:
                    growth_tag = "🚀"
                elif accel < 0.8:
                    growth_tag = "⚠️"
                else:
                    growth_tag = "➡️"

            # 매출 검증 태그
            rev_tag = ""
            if isinstance(rev_yoy, (int, float)):
                rev_tag = "✅" if rev_yoy >= 10 else "⚠️"

            # 문자열 변환
            rs_str = f"{primary:.1f}" if primary is not None else "N/A"
            vol_str = f"{vol_ratio:.1f}x" if vol_ratio is not None else "N/A"
            eps_str = f"{eps_yoy:.1f}%" if pd.notna(eps_yoy) else "N/A"
            rev_str = f"{rev_yoy:.1f}%" if pd.notna(rev_yoy) else "N/A"
            roe_str = f"{roe:.1f}%" if pd.notna(roe) else "N/A"
            eps_fwd_str = f"{eps_fwd:.1f}%" if eps_fwd is not None else "N/A"
            tp_str = f"{tp:.1f}%" if tp is not None else "N/A"

            msg += (
                f"{i}. [{t}](https://www.tradingview.com/symbols/{t}/)\n"
                f"RS {rs_str} | VOL {vol_str}\n\n"
                f"EPS {eps_str}\n"
                f"FWD {eps_fwd_str} {growth_tag}\n\n"
                f"REV {rev_str} {rev_tag}\n"
                f"ROE {roe_str}\n"
                f"TP {tp_str}\n\n"
            )

    print(msg)
    send_telegram(msg)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    scan()
