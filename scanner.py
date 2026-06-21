import pandas as pd
import yfinance as yf
import requests
import json
import os
import time

# =========================
# 설정
# =========================
TREND_CSV = "trend_universe.csv"            # 추세전환 유니버스 (가벼운 필터, ~10개)
SUPERTREND_CSV = "supertrend_universe.csv"  # 추세추종 유니버스 (빡빡한 필터, ~40개)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FMP_API_KEY = os.getenv("FMP_API_KEY")
FMP_CACHE_FILE = "fundamentals_cache.json"  # 당일 누적 캐시 (GitHub Actions cache가 날짜별로 관리)

def load_fmp_cache():
    if not os.path.exists(FMP_CACHE_FILE):
        return {}
    try:
        with open(FMP_CACHE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_fmp_cache(cache):
    try:
        with open(FMP_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except:
        pass

# =========================
# 텔레그램
# =========================
def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            },
            timeout=10
        )
    except:
        pass

# =========================
# SPY RS
# =========================
def get_spy_return():
    spy = yf.download(
        "SPY", period="1y", auto_adjust=True, progress=False,
        multi_level_index=False
    )
    if spy is None or spy.empty:
        return 0.0
    c = spy["Close"]
    return float((c.iloc[-1] / c.iloc[0] - 1) * 100)

SPY_RET = get_spy_return()

def calc_rs(df):
    if df is None or df.empty:
        return None
    c = df["Close"]
    stock_ret = (c.iloc[-1] / c.iloc[0] - 1) * 100
    return float(stock_ret) - SPY_RET

# =========================
# 거래량
# =========================
def calc_vol_ratio(df):
    try:
        vol = df["Volume"]
        if len(vol) < 21:
            return None
        today = vol.iloc[-1]
        avg20 = vol.iloc[-21:-1].mean()
        if avg20 == 0:
            return None
        return float(today / avg20)
    except:
        return None

# =========================
# 시그널 - 추세전환 유니버스용 (골든크로스 / 추세전환)
# 두 시그널을 명확히 분리: 이전엔 조건이 사실상 동일해서
# 골든크로스=추세전환 결과가 항상 같이 나오는 버그가 있었음
# =========================
def get_reversal_signals(df):
    close = df["Close"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()

    c = close.iloc[-1]
    sig = []

    # 골든크로스: 구조적 크로스 이벤트 (MA20이 MA50을 오늘 돌파)
    if ma20.iloc[-2] <= ma50.iloc[-2] and ma20.iloc[-1] > ma50.iloc[-1]:
        sig.append("골든크로스")

    # 추세전환: 아직 MA50 아래지만, 가격이 오늘 막 MA20을 돌파 (더 이른 단계 신호)
    if (
        close.iloc[-2] <= ma20.iloc[-2]
        and c > ma20.iloc[-1]
        and c < ma50.iloc[-1]
    ):
        sig.append("추세전환")

    return sig

# =========================
# 시그널 - 추세추종 유니버스용 (돌파 / 눌림목)
# =========================
def get_trend_signals(df):
    close = df["Close"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    high20 = df["High"].rolling(20).max().shift(1)

    c = close.iloc[-1]
    sig = []

    if c > high20.iloc[-1]:
        sig.append("돌파")

    if ma20.iloc[-1] > ma50.iloc[-1] and c < ma20.iloc[-1]:
        sig.append("눌림목")

    return sig

# =========================
# 티커 로드 (유니버스 분리 — 더 이상 합치지 않음)
# =========================
def load_trend_tickers():
    return pd.read_csv(TREND_CSV)["Symbol"].dropna().tolist()

def load_supertrend_tickers():
    return pd.read_csv(SUPERTREND_CSV)["Symbol"].dropna().tolist()

# =========================
# FMP 펀더멘털 — 시그널 통과 종목만 호출
# 1차(TV 스크리너)에서 재무 필터링 이미 끝났으므로
# 여기선 캐싱/대량호출 없이 통과 종목 표시용으로만 라이브 호출
# =========================
def growth(now, prev):
    if now is None or prev is None or prev == 0:
        return None
    return (now - prev) / abs(prev) * 100

def fetch_json(url, retries=1, delay=1.5):
    """공통 GET + 재시도. 실패하면 retries 횟수만큼만 추가 시도 (기본 총 2회)."""
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                return r.json()
        except:
            pass
        if attempt < retries:
            time.sleep(delay)
    return None

def fetch_past(t):
    url = (
        f"https://financialmodelingprep.com/stable/income-statement"
        f"?symbol={t}&period=annual&limit=2&apikey={FMP_API_KEY}"
    )
    data = fetch_json(url)
    if not isinstance(data, list) or len(data) < 2:
        return None
    data = sorted(data, key=lambda x: x.get("date", ""), reverse=True)
    now, prev = data[0], data[1]
    eps_now = now.get("eps") or now.get("epsdiluted")
    eps_prev = prev.get("eps") or prev.get("epsdiluted")
    rev_now = now.get("revenue")
    rev_prev = prev.get("revenue")
    return {
        "eps_yoy": growth(eps_now, eps_prev),
        "rev_yoy": growth(rev_now, rev_prev),
        "eps_now": eps_now,
        "rev_now": rev_now
    }

def fetch_forward_yoy(t, eps_now, rev_now):
    url = (
        f"https://financialmodelingprep.com/stable/analyst-estimates"
        f"?symbol={t}&period=annual&page=0&limit=1&apikey={FMP_API_KEY}"
    )
    data = fetch_json(url)
    if not isinstance(data, list) or len(data) == 0:
        return None
    d = data[0]
    return {
        "eps_fwd_yoy": growth(d.get("estimatedEpsAvg"), eps_now),
        "rev_fwd_yoy": growth(d.get("estimatedRevenueAvg"), rev_now)
    }

def fetch_roe(t):
    url = (
        f"https://financialmodelingprep.com/stable/ratios-ttm"
        f"?symbol={t}&apikey={FMP_API_KEY}"
    )
    data = fetch_json(url)
    if not isinstance(data, list) or len(data) == 0:
        return None
    roe = data[0].get("returnOnEquityTTM")
    if roe is None:
        return None
    return float(roe) * 100  # FMP는 보통 소수(0.15=15%)로 반환 → % 변환

def fetch_fundamentals(t):
    """
    종목당 2콜만 호출 (income-statement + ratios-ttm).

    analyst-estimates(FWD)는 FMP 무료/Starter 플랜에서
    AAPL/TSLA/AMZN 등 87개 대형주 샘플로만 제공됨 — 우리 유니버스의
    중소형주는 거의 항상 빈 응답이라 호출 자체가 낭비라 제외함.
    유료 플랜(Premium 이상)으로 올리면 fetch_forward_yoy 다시 붙이면 됨.
    """
    result = {
        "eps_yoy": None, "rev_yoy": None,
        "eps_fwd_yoy": None, "rev_fwd_yoy": None,
        "roe": None
    }

    past = fetch_past(t)
    time.sleep(0.2)

    if past:
        result["eps_yoy"] = past["eps_yoy"]
        result["rev_yoy"] = past["rev_yoy"]

    result["roe"] = fetch_roe(t)
    time.sleep(0.2)

    return result

# =========================
# SCAN
# =========================
def scan():
    trend_tickers = load_trend_tickers()
    supertrend_tickers = load_supertrend_tickers()

    buckets = {
        "돌파": [],
        "눌림목": [],
        "골든크로스": [],
        "추세전환": []
    }

    print(
        f"[SCAN] 추세전환 유니버스 {len(trend_tickers)}개 | "
        f"추세추종 유니버스 {len(supertrend_tickers)}개 | SPY={SPY_RET:.2f}"
    )

    # 추세전환 유니버스 → 골든크로스 / 추세전환만 체크
    for t in trend_tickers:
        try:
            df = yf.download(
                t, period="1y", auto_adjust=True, progress=False,
                multi_level_index=False
            )
            if df is None or df.empty:
                continue

            sigs = get_reversal_signals(df)
            if not sigs:
                continue

            rs = calc_rs(df)
            vol = calc_vol_ratio(df)
            for s in sigs:
                buckets[s].append((t, rs, vol))

            time.sleep(0.05)
        except:
            continue

    # 추세추종 유니버스 → 돌파 / 눌림목만 체크
    for t in supertrend_tickers:
        try:
            df = yf.download(
                t, period="1y", auto_adjust=True, progress=False,
                multi_level_index=False
            )
            if df is None or df.empty:
                continue

            sigs = get_trend_signals(df)
            if not sigs:
                continue

            rs = calc_rs(df)
            vol = calc_vol_ratio(df)
            for s in sigs:
                buckets[s].append((t, rs, vol))

            time.sleep(0.05)
        except:
            continue

    # =========================
    # 카테고리별 상위 N개로 압축 (RS 기준) — 출력 개수 + FMP 호출량 동시 통제
    # 4개 카테고리 x 5개 = 최대 20개, 목표는 평소 10개 안팎
    # =========================
    MAX_PER_CATEGORY = 5

    for cat in buckets:
        buckets[cat].sort(
            key=lambda x: (x[1] if x[1] is not None else float("-inf")),
            reverse=True
        )
        buckets[cat] = buckets[cat][:MAX_PER_CATEGORY]

    # =========================
    # 시그널 통과 종목만 FMP 호출 (종목당 1회만, 중복 제거)
    # =========================
    signaled_tickers = set()
    for items in buckets.values():
        for t, _, _ in items:
            signaled_tickers.add(t)

    print(f"[FMP] 시그널 통과 {len(signaled_tickers)}개 종목")

    fmp_cache = load_fmp_cache()
    new_calls = 0

    for t in signaled_tickers:
        if t in fmp_cache:
            continue  # 오늘 이미 호출한 종목 → 재사용, 콜 안 씀
        fmp_cache[t] = fetch_fundamentals(t)
        new_calls += 1

    print(f"[FMP] 신규 호출 {new_calls}개 | 캐시 재사용 {len(signaled_tickers) - new_calls}개")

    save_fmp_cache(fmp_cache)

    # =========================
    # OUTPUT
    # =========================
    msg = ""

    for cat in ["돌파", "눌림목", "골든크로스", "추세전환"]:
        msg += f"\n[{cat}]\n\n"
        items = buckets[cat]

        if not items:
            msg += "없음\n"
            continue

        for i, (t, rs, vol) in enumerate(items, 1):
            f = fmp_cache.get(t, {})

            eps_yoy = f.get("eps_yoy")
            rev_yoy = f.get("rev_yoy")
            eps_fwd_yoy = f.get("eps_fwd_yoy")
            rev_fwd_yoy = f.get("rev_fwd_yoy")
            roe = f.get("roe")

            eps_yoy_str = f"{eps_yoy:.1f}%" if isinstance(eps_yoy, (int, float)) else "N/A"
            rev_yoy_str = f"{rev_yoy:.1f}%" if isinstance(rev_yoy, (int, float)) else "N/A"
            eps_fwd_str = f"{eps_fwd_yoy:.1f}%" if isinstance(eps_fwd_yoy, (int, float)) else "N/A"
            rev_fwd_str = f"{rev_fwd_yoy:.1f}%" if isinstance(rev_fwd_yoy, (int, float)) else "N/A"
            roe_str = f"{roe:.1f}%" if isinstance(roe, (int, float)) else "N/A"

            rs_str = f"{rs:.1f}" if rs is not None else "N/A"
            vol_str = f"{vol:.1f}x" if vol is not None else "N/A"

            msg += (
                f"{i}. [{t}](https://www.tradingview.com/symbols/{t}/) | RS {rs_str} | VOL {vol_str}\n"
                f"EPS YoY {eps_yoy_str} | EPS FWD YoY {eps_fwd_str}\n"
                f"REV YoY {rev_yoy_str} | REV FWD YoY {rev_fwd_str} | ROE {roe_str}\n\n"
            )

    print(msg)
    send_telegram(msg)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    scan()
