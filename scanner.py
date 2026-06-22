import pandas as pd
import numpy as np
import yfinance as yf
import requests
import os
import re
import time

# =========================
# 설정 (✅ 파일명 기준 통일)
# =========================
REVERSAL_CSV = "reversal.csv"
SUPERTREND_CSV = "supertrend.csv"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

MAX_PER_CATEGORY = 5

VOL_BREAK_20  = 1.2
VOL_BREAK_50  = 1.3
VOL_BREAK_52W = 1.5
TREND_REVERSAL_MIN_VOL = 1.3

# 파일명 기준 카테고리 (reversal은 추세전환만, supertrend는 돌파/눌림목/골크)
REVERSAL_CATS = {"추세전환"}
SUPERTREND_CATS = {"돌파_52W", "돌파_50", "돌파_20", "눌림목", "골든크로스"}

RS_MIN = {
    "돌파_52W": 0,
    "돌파_50":  0,
    "돌파_20":  0,
    "눌림목":   0,
    "골든크로스": -20,
    "추세전환": None,
}

VOL_FAVORS_HIGH = {
    "돌파_52W": True,
    "돌파_50":  True,
    "돌파_20":  True,
    "눌림목":   False,
    "골든크로스": True,
    "추세전환": True,
}

CATEGORY_WEIGHTS = {
    "돌파_52W": {"rs": 0.5, "vol": 0.5},
    "돌파_50":  {"rs": 0.5, "vol": 0.5},
    "돌파_20":  {"rs": 0.5, "vol": 0.5},
    "눌림목":   {"rs": 0.7, "vol": 0.3},
    "골든크로스": {"rs": 0.6, "vol": 0.4},
    "추세전환": {"rs": 0.7, "vol": 0.3},
}

CATEGORIES = ["돌파_52W", "돌파_50", "돌파_20", "눌림목", "골든크로스", "추세전환"]

# =========================
# 🔥 티커 추출 (대문자+숫자 연속구간만)
# =========================
def extract_ticker(raw_symbol: str) -> str:
    raw_symbol = raw_symbol.strip()
    # 앞부분 연속 대문자+숫자만 추출 (1~6자)
    m = re.match(r'^([A-Z0-9]{1,6})', raw_symbol)
    if m:
        return m.group(1)
    # fallback: 공백 기준 첫 단어
    return raw_symbol.split()[0]

# =========================
# 재무 태깅 엔진
# =========================
def get_growth_tag(yoy, rev, qoq):
    try:
        if yoy is None or rev is None or qoq is None:
            return "📊 데이터부족"
        if yoy >= 25 and rev >= 20 and qoq >= 20:
            return "🔥 초고성장주"
        elif yoy >= 10 and yoy < 25:
            return "📈 성장주"
        elif yoy >= 0 and yoy < 10:
            return "➖ 중립"
        else:
            return "📉 역성장"
    except:
        return "❌ 오류"

def get_momentum_tag(qoq):
    try:
        if qoq is None:
            return "📊 데이터부족"
        if qoq >= 50:
            return "💥 분기 폭발"
        elif qoq >= 20:
            return "🚀 분기 강한가속"
        elif qoq >= 10:
            return "✅ 분기 보통가속"
        elif qoq >= 0:
            return "➖ 분기 정체"
        else:
            return "⚠️ 분기 역성장"
    except:
        return "❌ 오류"

def get_future_tag(fwd, yoy):
    try:
        if fwd is None or yoy is None:
            return "📊 데이터부족"
        if fwd > yoy:
            return "☀️ 미래 상향"
        else:
            return "🌧️ 미래 하향"
    except:
        return "❌ 오류"

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
# SPY 기준
# =========================
def get_spy_return():
    try:
        spy = yf.download("SPY", period="1y", auto_adjust=True, progress=False)
        if spy is None or spy.empty:
            return 0.0
        close = spy["Close"]
        return float((close.iloc[-1].item() / close.iloc[0].item() - 1) * 100)
    except:
        return 0.0

SPY_RET = get_spy_return()

# =========================
# RS 계산
# =========================
def calc_rs(df):
    try:
        close = df["Close"]
        stock_ret = (close.iloc[-1].item() / close.iloc[0].item() - 1) * 100
        return float(stock_ret - SPY_RET)
    except:
        return None

# =========================
# 거래량 비율
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
# 52주 고가 대비 이격율
# =========================
def calc_52w_position(ticker, current_price):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        high52 = info.get('fiftyTwoWeekHigh')
        if high52 is None or high52 <= 0:
            return None
        return float((current_price - high52) / high52 * 100)
    except:
        return None

# =========================
# 20일 모멘텀
# =========================
def momentum_20d(df):
    try:
        return float((df["Close"].iloc[-1].item() / df["Close"].iloc[-20].item() - 1) * 100)
    except:
        return None

# =========================
# 신호 감지
# =========================
def get_signals(df, vol_ratio):
    try:
        close  = df["Close"]
        high   = df["High"]
        ma20   = close.rolling(20).mean()
        ma50   = close.rolling(50).mean()

        c_last    = close.iloc[-1].item()
        ma20_last = ma20.iloc[-1].item()
        ma50_last = ma50.iloc[-1].item()
        ma20_prev = ma20.iloc[-2].item()
        ma50_prev = ma50.iloc[-2].item()

        high52_prev = high.rolling(252).max().shift(1).iloc[-1].item()
        high50_prev = high.rolling(50).max().shift(1).iloc[-1].item()
        high20_prev = high.rolling(20).max().shift(1).iloc[-1].item()

        signals = []

        if c_last > high52_prev and vol_ratio >= VOL_BREAK_52W:
            signals.append("돌파_52W")
        elif c_last > high50_prev and vol_ratio >= VOL_BREAK_50:
            signals.append("돌파_50")
        elif c_last > high20_prev and vol_ratio >= VOL_BREAK_20:
            signals.append("돌파_20")

        if ma20_last > ma50_last and c_last < ma20_last:
            signals.append("눌림목")

        if ma20_prev <= ma50_prev and ma20_last > ma50_last:
            signals.append("골든크로스")

        if ma20_prev > ma50_prev and ma20_last > ma50_last and c_last > ma20_last:
            signals.append("추세전환")

        return signals
    except:
        return []

# =========================
# RS 필터 통과 여부
# =========================
def rs_pass(cat, rs):
    min_rs = RS_MIN.get(cat)
    if min_rs is None:
        return True
    if rs is None:
        return False
    return rs >= min_rs

# =========================
# 퍼센타일 랭크
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
# 합성 점수
# =========================
def attach_composite_scores(items, category):
    if not items:
        return []

    primaries = [it[1] for it in items]
    vols      = [it[2] for it in items]

    p_rank = percentile_rank(primaries)
    v_rank = percentile_rank(vols)

    favors_high = VOL_FAVORS_HIGH.get(category, True)
    weights     = CATEGORY_WEIGHTS.get(category, {"rs": 0.6, "vol": 0.4})
    rs_w  = weights["rs"]
    vol_w = weights["vol"]

    scored = []
    for i, it in enumerate(items):
        ticker, primary, vol_ratio, price, pos_52w = it
        p_pct = p_rank.get(i, 50.0)
        v_pct = v_rank.get(i, 50.0)
        if not favors_high:
            v_pct = 100.0 - v_pct
        composite = rs_w * p_pct + vol_w * v_pct
        scored.append((ticker, primary, vol_ratio, price, pos_52w, composite))

    scored.sort(key=lambda x: x[5], reverse=True)
    return scored

# =========================
# CSV 클리너
# =========================
def clean_numeric(val):
    if isinstance(val, str):
        val = val.replace('%', '').replace('$', '').replace(',', '').strip()
        val = val.replace('USD', '').replace('usd', '').replace('Usd', '')
        if '#ERROR!' in val or 'N/A' in val or 'ERROR' in val:
            return float('nan')
        val = val.strip()
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
    fund_map = {}
    ticker_source = {}

    sources = [
        (REVERSAL_CSV, "reversal"),
        (SUPERTREND_CSV, "supertrend"),
    ]

    for path, source_label in sources:
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_csv(path, encoding='utf-8-sig', sep=None, engine='python')
            df.columns = df.columns.str.strip()
            if len(df.columns) == 1 and '\t' in df.columns[0]:
                split_cols = df.columns[0].split('\t')
                df = df[df.columns[0]].str.split('\t', expand=True)
                df.columns = split_cols

            if "Symbol" not in df.columns:
                df = df.rename(columns={df.columns[0]: "Symbol"})

            numeric_cols = [
                "EPS_Growth_TTM_YoY", "EPS Growth TTM YoY",
                "Revenue_Growth_TTM_YoY", "Revenue Growth TTM YoY",
                "Reported_EPS_FY", "Reported EPS FY",
                "Estimated_EPS_FY", "Estimated EPS FY",
                "ROE",
                "EPS_Current_Quarter",
                "EPS_Next_Quarter",
            ]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = df[col].apply(clean_numeric)

            for _, row in df.iterrows():
                raw_symbol = str(row["Symbol"]).strip()
                ticker = extract_ticker(raw_symbol)  # 🔥 수정된 티커 추출

                if not ticker:
                    continue
                if ticker not in fund_map:
                    fund_map[ticker] = row.to_dict()
                    ticker_source[ticker] = source_label

        except Exception as e:
            print(f"[WARN] {path} 읽기 실패: {e}")

    if not fund_map:
        print("[WARN] CSV 파일 없음")

    return fund_map, ticker_source

# =========================
# 재무 헬퍼
# =========================
def get_field(f, *keys):
    for k in keys:
        v = f.get(k)
        if v is not None:
            return v
    return None

def calc_qoq(cur_q, next_q):
    try:
        if cur_q is None or next_q is None:
            return None
        if pd.isna(cur_q) or pd.isna(next_q):
            return None
        if cur_q == 0:
            return None
        return float((next_q - cur_q) / abs(cur_q) * 100)
    except:
        return None

# =========================
# SCAN
# =========================
def scan():
    fund_map, ticker_source = load_fundamentals()
    if not fund_map:
        print("[ERROR] 종목 없음")
        return

    tickers = list(fund_map.keys())
    buckets = {cat: [] for cat in CATEGORIES}

    print(f"[SCAN] tickers={len(tickers)} | SPY={SPY_RET:.2f}%")

    for t in tickers:
        try:
            df = yf.download(t, period="1y", auto_adjust=True, progress=False)
            if df is None or df.empty:
                continue

            rs            = calc_rs(df)
            vol_ratio     = calc_vol_ratio(df) or 1.0
            current_price = float(df["Close"].iloc[-1])
            pos_52w       = calc_52w_position(t, current_price)
            signals       = get_signals(df, vol_ratio)
            source        = ticker_source.get(t, "reversal")

            if not signals:
                continue

            for s in signals:
                if source == "reversal" and s not in REVERSAL_CATS:
                    continue
                if source == "supertrend" and s not in SUPERTREND_CATS:
                    continue

                if not rs_pass(s, rs):
                    continue

                if s == "추세전환" and vol_ratio < TREND_REVERSAL_MIN_VOL:
                    continue

                primary = momentum_20d(df) if s == "추세전환" else rs
                buckets[s].append((t, primary, vol_ratio, current_price, pos_52w))

            time.sleep(0.2)

        except:
            continue

    scored_buckets = {cat: attach_composite_scores(buckets[cat], cat) for cat in CATEGORIES}

    cat_labels = {
        "돌파_52W": "🏆 [돌파] 52주 신고가 🔥",
        "돌파_50":  "🏆 [돌파] 50일 고가",
        "돌파_20":  "🏆 [돌파] 20일 고가",
        "눌림목":   "🏆 [눌림목]",
        "골든크로스": "🏆 [골든크로스]",
        "추세전환": "🏆 [추세전환]",
    }

    msg = ""

    for cat in CATEGORIES:
        items = scored_buckets[cat][:MAX_PER_CATEGORY]
        msg += f"\n{cat_labels[cat]}\n\n"

        if not items:
            msg += "없음\n"
            continue

        for i, (t, primary, vol_ratio, current_price, pos_52w, composite) in enumerate(items, 1):
            f = fund_map.get(t, {})

            eps_yoy = get_field(f, "EPS_Growth_TTM_YoY", "EPS Growth TTM YoY")
            rev_yoy = get_field(f, "Revenue_Growth_TTM_YoY", "Revenue Growth TTM YoY")
            rep_eps = get_field(f, "Reported_EPS_FY", "Reported EPS FY")
            est_eps = get_field(f, "Estimated_EPS_FY", "Estimated EPS FY")
            roe     = get_field(f, "ROE")
            cur_q   = get_field(f, "EPS_Current_Quarter")
            next_q  = get_field(f, "EPS_Next_Quarter")

            qoq = calc_qoq(cur_q, next_q)

            eps_fwd = None
            if rep_eps and est_eps and not pd.isna(rep_eps) and not pd.isna(est_eps) and rep_eps != 0:
                eps_fwd = ((est_eps - rep_eps) / abs(rep_eps)) * 100

            growth_tag_new   = get_growth_tag(eps_yoy, rev_yoy, qoq)
            momentum_tag_new = get_momentum_tag(qoq)
            future_tag_new   = get_future_tag(eps_fwd, eps_yoy)

            rs_str  = f"{primary:.1f}" if primary is not None else "N/A"
            vol_str = f"{vol_ratio:.1f}x"
            pos_str = f"{pos_52w:+.1f}%" if pos_52w is not None else "N/A"
            eps_str = f"{eps_yoy:.1f}%" if isinstance(eps_yoy, float) and not pd.isna(eps_yoy) else "N/A"
            fwd_str = f"{eps_fwd:.1f}%" if eps_fwd is not None else "N/A"
            qoq_str = f"{qoq:+.1f}%" if qoq is not None else "N/A"
            rev_str = f"{rev_yoy:.1f}%" if isinstance(rev_yoy, float) and not pd.isna(rev_yoy) else "N/A"
            roe_str = f"{roe:.1f}%" if isinstance(roe, float) and not pd.isna(roe) else "N/A"

            msg += (
                f"{i}. {t} ${current_price:.1f} | 52W {pos_str}\n"
                f"RS {rs_str} | VOL {vol_str}\n"
                f"YoY {eps_str} | QoQ {qoq_str} | FWD {fwd_str}\n"
                f"REV {rev_str} | ROE {roe_str}\n"
                f"🏷️ {growth_tag_new} | {momentum_tag_new} | {future_tag_new}\n\n"
            )

    print(msg)
    send_telegram(msg)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    scan()
