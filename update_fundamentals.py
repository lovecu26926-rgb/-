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
    url = f"https://financialmodelingprep.com/stable/income-statement?symbol={t}&limit=2&apikey={API_KEY}"
    try:
        r = requests.get(url, timeout=10).json()
        if not isinstance(r, list) or len(r) < 2:
            return None

        r = sorted(r, key=lambda x: x.get("date", ""), reverse=True)
        now, prev = r[0], r[1]

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
    except:
        return None


# =========================
# 미래 (FWD YoY) - 추가 API 호출 없음
# =========================
def fetch_forward_yoy(t, eps_now, rev_now):
    url = f"https://financialmodelingprep.com/stable/analyst-estimates?symbol={t}&limit=1&apikey={API_KEY}"
    try:
        r = requests.get(url, timeout=10).json()
        if not isinstance(r, list) or len(r) == 0:
            return None

        d = r[0]
        return {
            "eps_fwd_yoy": growth(d.get("estimatedEpsAvg"), eps_now),
            "rev_fwd_yoy": growth(d.get("estimatedRevenueAvg"), rev_now)
        }
    except:
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
