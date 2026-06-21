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
# 과거 (YoY)
# =========================
def fetch_past(t):

    url = f"https://financialmodelingprep.com/stable/income-statement?symbol={t}&limit=2&apikey={API_KEY}"

    try:
        r = requests.get(url, timeout=10).json()
        if not isinstance(r, list) or len(r) < 2:
            return None

        r = sorted(r, key=lambda x: x.get("date", ""), reverse=True)

        now, prev = r[0], r[1]

        return {
            "eps_yoy": growth(
                now.get("eps") or now.get("epsdiluted"),
                prev.get("eps") or prev.get("epsdiluted")
            ),
            "rev_yoy": growth(
                now.get("revenue"),
                prev.get("revenue")
            )
        }

    except:
        return None


# =========================
# 미래 (FWD)
# =========================
def fetch_forward_yoy(t):

    url = f"https://financialmodelingprep.com/stable/analyst-estimates?symbol={t}&limit=1&apikey={API_KEY}"

    try:
        r = requests.get(url, timeout=10).json()
        if not isinstance(r, list) or len(r) == 0:
            return None

        d = r[0]

        eps_fwd = d.get("estimatedEpsAvg")
        rev_fwd = d.get("estimatedRevenueAvg")

        # 여기 핵심: "현재 EPS/REV" 필요
        past = fetch_past(t)
        if past is None:
            return None

        # 다시 income 1번 더 (정확한 현재값)
        url2 = f"https://financialmodelingprep.com/stable/income-statement?symbol={t}&limit=1&apikey={API_KEY}"
        r2 = requests.get(url2, timeout=10).json()

        if not isinstance(r2, list) or len(r2) == 0:
            return None

        now = r2[0]

        eps_now = now.get("eps") or now.get("epsdiluted")
        rev_now = now.get("revenue")

        return {
            "eps_fwd_yoy": growth(eps_fwd, eps_now),
            "rev_fwd_yoy": growth(rev_fwd, rev_now)
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
        time.sleep(0.2)

        fwd = fetch_forward_yoy(t)
        time.sleep(0.2)

        if past is None:
            past = {}

        if fwd is None:
            fwd = {}

        data[t] = {
            "eps_yoy": past.get("eps_yoy"),
            "rev_yoy": past.get("rev_yoy"),
            "eps_fwd_yoy": fwd.get("eps_fwd_yoy"),
            "rev_fwd_yoy": fwd.get("rev_fwd_yoy"),
        }

        print(i, t, data[t])

    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    build()
