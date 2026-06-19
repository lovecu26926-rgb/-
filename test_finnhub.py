import requests
import os

API_KEY = os.environ.get("FINNHUB_API_KEY") or "YOUR_FINNHUB_TOKEN"

tickers = ["AAPL", "NVDA", "MU", "AMD", "TSLA"]

print("📊 Finnhub 성장률 계산 시작\n")


def calc_growth(new, old):
    if new is None or old is None or old == 0:
        return None
    return ((new - old) / abs(old)) * 100


for ticker in tickers:
    print(f"🔹 {ticker}")

    url = f"https://finnhub.io/api/v1/stock/financials-reported?symbol={ticker}&token={API_KEY}"

    try:
        resp = requests.get(url, timeout=10)

        if resp.status_code != 200:
            print("   ❌ API 오류")
            continue

        data = resp.json()

        # 연간 데이터
        reports = data.get("data", [])

        if len(reports) < 2:
            print("   ❌ 데이터 부족")
            continue

        latest = reports[0]
        prev = reports[1]

        # Finnhub 구조 (케이스별 방어)
        def get_val(obj, key):
            try:
                return obj.get("report", {}).get(key, None)
            except:
                return None

        # 🔥 매출 / EPS
        revenue_now = get_val(latest, "revenue")
        revenue_prev = get_val(prev, "revenue")

        eps_now = get_val(latest, "eps")
        eps_prev = get_val(prev, "eps")

        # 성장률 계산
        revenue_growth = calc_growth(revenue_now, revenue_prev)
        eps_growth = calc_growth(eps_now, eps_prev)

        # 출력
        if revenue_growth is not None:
            print(f"   📈 매출 성장: {round(revenue_growth, 2)}%")
        else:
            print("   📈 매출 성장: 없음")

        if eps_growth is not None:
            print(f"   📈 EPS 성장: {round(eps_growth, 2)}%")
        else:
            print("   📈 EPS 성장: 없음")

        print()

    except Exception as e:
        print(f"   ❌ 에러: {e}\n")
