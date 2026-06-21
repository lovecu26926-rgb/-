import requests
import json
import os
import time
import pandas as pd

API_KEY = os.getenv("FMP_API_KEY")
CACHE_FILE = "fundamentals.json"

TREND_CSV = "trend_universe.csv"
SUPERTREND_CSV = "supertrend_universe.csv"


def load_tickers():
    t1 = pd.read_csv(TREND_CSV)["Symbol"].dropna().tolist()
    t2 = pd.read_csv(SUPERTREND_CSV)["Symbol"].dropna().tolist()
    return list(set(t1 + t2))


def growth(now, prev):
    if now is None or prev is None or prev == 0:
        return None
    return (now - prev) / abs(prev) * 100


# =========================
# 과거 (YoY) + 현재값 (FWD용)
# =========================
def fetch_past(t):
    url = (
        f"https://financialmodelingprep.com/stable/income-statement"
        f"?symbol={t}&period=annual&limit=2&apikey={API_KEY}"
    )
    try:
        r = requests.get(url, timeout=10)

        if r.status_code != 200:
            print(f"  [past 실패] {t} status={r.status_code} body={r.text[:150]}")
            return None

        data = r.json()
        if not isinstance(data, list) or len(data) < 2:
            print(f"  [past 데이터부족] {t} → {data}")
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
            "eps_now": eps_now,   # ← FWD 계산용으로 반환
            "rev_now": rev_now
        }
    except Exception as e:
        print(f"  [past 예외] {t} → {e}")
        return None


# =========================
# 미래 (FWD YoY) - 추가 API 호출 없음
# =========================
def fetch_forward_yoy(t, eps_now, rev_now):
    # FMP 공식 문서 기준 필수 파라미터: symbol, period, page, limit
    # 기존 코드엔 period/page가 빠져 있어서 요청이 실패하고
    # except에 걸려 항상 None을 반환했음 (= FWD 값이 영원히 안 채워짐)
    url = (
        f"https://financialmodelingprep.com/stable/analyst-estimates"
        f"?symbol={t}&period=annual&page=0&limit=1&apikey={API_KEY}"
    )
    try:
        r = requests.get(url, timeout=10)

        if r.status_code != 200:
            print(f"  [fwd 실패] {t} status={r.status_code} body={r.text[:150]}")
            return None

        data = r.json()
        if not isinstance(data, list) or len(data) == 0:
            print(f"  [fwd 데이터없음] {t} → {data}")
            return None

        d = data[0]
        return {
            "eps_fwd_yoy": growth(d.get("estimatedEpsAvg"), eps_now),
            "rev_fwd_yoy": growth(d.get("estimatedRevenueAvg"), rev_now)
        }
    except Exception as e:
        print(f"  [fwd 예외] {t} → {e}")
        return None


# =========================
# build
# =========================
def build():
    tickers = load_tickers()
    data = {}

    print(f"[FUND] {len(tickers)} tickers")

    for i, t in enumerate(tickers, 1):
        past = fetch_past(t)
        time.sleep(0.25)

        if past is None:
            data[t] = {
                "eps_yoy": None,
                "rev_yoy": None,
                "eps_fwd_yoy": None,
                "rev_fwd_yoy": None
            }
            print(i, t, "→ past 없음")
            continue

        fwd = fetch_forward_yoy(t, past["eps_now"], past["rev_now"])
        time.sleep(0.25)

        data[t] = {
            "eps_yoy": past["eps_yoy"],
            "rev_yoy": past["rev_yoy"],
            "eps_fwd_yoy": fwd.get("eps_fwd_yoy") if fwd else None,
            "rev_fwd_yoy": fwd.get("rev_fwd_yoy") if fwd else None
        }
        print(i, t, data[t])

    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"[DONE] {CACHE_FILE} 저장 완료")


if __name__ == "__main__":
    build()
