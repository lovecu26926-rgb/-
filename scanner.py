import csv

# ==================== 1. 분류 엔진 ====================
def classify_stock(stock):
    """
    종목 딕셔너리를 받아 태그 추가:
    - growth_tag: 초고성장주 / 성장주 / 중립 / 역성장
    - momentum_tag: 분기 폭발 / 분기 강한가속 / 분기 보통가속 / 분기 정체 / 분기 역성장
    - future_tag: 미래 상향 / 미래 하향
    """
    try:
        yoy = float(stock.get("yoy", 0))
        rev = float(stock.get("rev", 0))
        qoq = float(stock.get("qoq", 0))
        fwd = float(stock.get("fwd", 0))
    except (ValueError, TypeError):
        yoy, rev, qoq, fwd = 0, 0, 0, 0

    # ---------- ① 성장 분류 (EPS YoY 기준) ----------
    if yoy >= 25 and rev >= 20 and qoq >= 20:
        growth_tag = "초고성장주"
    elif 10 <= yoy < 25:
        growth_tag = "성장주"
    elif 0 <= yoy < 10:
        growth_tag = "중립"
    else:
        growth_tag = "역성장"

    # ---------- ② 분기 모멘텀 (QoQ 5단계) ----------
    if qoq >= 50:
        momentum_tag = "분기 폭발"
    elif 20 <= qoq < 50:
        momentum_tag = "분기 강한가속"
    elif 10 <= qoq < 20:
        momentum_tag = "분기 보통가속"
    elif 0 <= qoq < 10:
        momentum_tag = "분기 정체"
    else:
        momentum_tag = "분기 역성장"

    # ---------- ③ 미래 전망 (FWD vs YoY) ----------
    future_tag = "미래 상향" if fwd > yoy else "미래 하향"

    # 원본 데이터에 태그 3개를 추가
    stock["growth_tag"] = growth_tag
    stock["momentum_tag"] = momentum_tag
    stock["future_tag"] = future_tag
    return stock


# ==================== 2. CSV 읽기/쓰기 (매핑 포함) ====================
def read_csv(file_path):
    """CSV를 읽고, 실제 컬럼명을 내부 키로 매핑합니다."""
    data = []
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # ① 내부 키로 매핑 (원본 컬럼 유지 + 계산용 키 추가)
                mapped = {
                    "ticker": row.get("Symbol", "").strip(),
                    "yoy": float(row.get("EPS_Growth_TTM_YoY", 0)),
                    "rev": float(row.get("Revenue_Growth_TTM_YoY", 0)),
                    "roe": float(row.get("ROE", 0)),
                    "fwd": float(row.get("Estimated_EPS_FY", 0)),
                }
                # ② QoQ 계산: (다음분기 / 현재분기) - 1
                current_q = float(row.get("EPS_Current_Quarter", 0))
                next_q = float(row.get("EPS_Next_Quarter", 0))
                if current_q != 0:
                    qoq = (next_q / current_q - 1) * 100
                else:
                    qoq = 0
                mapped["qoq"] = qoq

                # ③ 원본 row에 mapped 값들을 병합 (계산용 키 추가)
                row.update(mapped)
                data.append(row)
        print(f"✅ 파일 읽기 성공: {file_path} (총 {len(data)}개 종목)")
    except FileNotFoundError:
        print(f"❌ 파일을 찾을 수 없습니다: {file_path}")
    return data


def write_csv(file_path, data):
    """분류된 데이터를 CSV로 저장 (원본 컬럼 + 태그 3개)"""
    if not data:
        print(f"⚠️ 저장할 데이터가 없습니다: {file_path}")
        return
    with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    print(f"✅ 분류 완료 저장: {file_path} (총 {len(data)}개 종목)")


# ==================== 3. 스캐너 실행기 ====================
def scan_csv_files(file_list):
    for input_file, output_file in file_list:
        print(f"\n--- 처리 중: {input_file} → {output_file} ---")
        stocks = read_csv(input_file)
        if not stocks:
            continue

        classified = [classify_stock(s) for s in stocks]
        write_csv(output_file, classified)

        # 터미널 미리보기 (상위 5개)
        for i, item in enumerate(classified[:5]):
            ticker = item.get("ticker") or "N/A"
            print(f"  {i+1}. {ticker} | {item['growth_tag']} | {item['momentum_tag']} | {item['future_tag']}")
        if len(classified) > 5:
            print(f"  ... 나머지 {len(classified)-5}개는 파일에서 확인하세요.")


# ==================== 4. 실행 ====================
if __name__ == "__main__":
    file_pairs = [
        ("reversal.csv", "reversal_classified.csv"),
        ("supertrend.csv", "supertrend_classified.csv"),
    ]
    scan_csv_files(file_pairs)
    print("\n🎯 모든 스캔이 완료되었습니다!")
