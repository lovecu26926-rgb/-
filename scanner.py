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
    print(f"[INFO] ROE 필터는 TradingView 스크리너에서 이미 처리됨 (Python은 중복 제거)")

    for t in tickers:
        try:
            # 🔥 ROE 필터링 코드 완전 삭제!
            # 스크리너에서 이미 걸러줬으므로 신호만 체크하면 됨

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

                # 추세전환은 거래량 동반 필터 (유지)
                if s == "추세전환":
                    if vol_ratio is None or vol_ratio < TREND_REVERSAL_MIN_VOL_RATIO:
                        continue

                buckets[s].append([t, primary, vol_ratio])

            time.sleep(0.05)

        except Exception as e:
            continue

    print(f"[FILTER] 추세전환은 거래량 비율 >= {TREND_REVERSAL_MIN_VOL_RATIO}x 미만 시 자동 제외됨")

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
            roe = fund.get("roe", "N/A")  # 🔥 표시만 하고 필터링 안 함

            vr_str = f"{vol_ratio:.1f}x" if vol_ratio is not None else "N/A"
            primary_str = f"{primary:.1f}" if primary is not None else "N/A"

            msg += (
                f"{i}. {t} | 점수 {composite:.0f} | {label} {primary_str} | 거래량 {vr_str} "
                f"| 매출 {rev} | EPS {eps} | ROE {roe}\n"
            )

    print(msg)
    send_telegram(msg)
