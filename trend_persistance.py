"""
추세 지속성 스코어링 모듈
- ADX (추세 강도)
- MA 정배열 유지일수 (20/50/150/200)
- Supertrend 유지일수
- 거래량 Up/Down Ratio
- 종합 판단: 초입(브레이크아웃) / 중반(눌림목) / 약화 / 횡보

scanner.py에 import해서 종목별 daily df에 적용하는 방식으로 설계.
"""

import pandas as pd
import numpy as np
import yfinance as yf


# ---------------------------------------------------------
# 1. ADX 계산
# ---------------------------------------------------------
def calc_adx(df, period=14):
    high, low, close = df['High'], df['Low'], df['Close']

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    plus_dm[(plus_dm - minus_dm) < 0] = 0
    minus_dm[(minus_dm - plus_dm) < 0] = 0

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1/period, min_periods=period).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=1/period, min_periods=period).mean()

    df['plus_di'] = plus_di
    df['minus_di'] = minus_di
    df['adx'] = adx
    return df


# ---------------------------------------------------------
# 2. 이동평균 정배열 + 유지일수
# ---------------------------------------------------------
def calc_ma_alignment(df):
    df['ma20'] = df['Close'].rolling(20).mean()
    df['ma50'] = df['Close'].rolling(50).mean()
    df['ma150'] = df['Close'].rolling(150).mean()
    df['ma200'] = df['Close'].rolling(200).mean()

    # 정배열 여부 (상승형): 20>50>150>200
    bullish = (df['ma20'] > df['ma50']) & (df['ma50'] > df['ma150']) & (df['ma150'] > df['ma200'])
    bearish = (df['ma20'] < df['ma50']) & (df['ma50'] < df['ma150']) & (df['ma150'] < df['ma200'])

    df['ma_bullish'] = bullish
    df['ma_bearish'] = bearish

    # 정배열 유지 연속일수 계산
    def streak(series):
        s = series.astype(int)
        grp = (s != s.shift()).cumsum()
        return s.groupby(grp).cumsum()

    df['ma_bullish_streak'] = streak(bullish)
    df['ma_bearish_streak'] = streak(bearish)

    # 20일선 기울기 (5일간 변화율로 근사)
    df['ma20_slope'] = df['ma20'].pct_change(5) * 100
    df['ma50_slope'] = df['ma50'].pct_change(5) * 100
    return df


# ---------------------------------------------------------
# 3. Supertrend 계산 + 유지일수
# ---------------------------------------------------------
def calc_supertrend(df, period=10, multiplier=3):
    high, low, close = df['High'], df['Low'], df['Close']
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    hl2 = (high + low) / 2
    upperband = hl2 + multiplier * atr
    lowerband = hl2 - multiplier * atr

    supertrend = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)  # 1=상승, -1=하락

    for i in range(len(df)):
        if i == 0:
            supertrend.iloc[i] = upperband.iloc[i]
            direction.iloc[i] = 1
            continue

        if close.iloc[i-1] <= supertrend.iloc[i-1]:
            curr_upper = min(upperband.iloc[i], supertrend.iloc[i-1]) if direction.iloc[i-1] == -1 else upperband.iloc[i]
        else:
            curr_upper = upperband.iloc[i]

        if close.iloc[i-1] >= supertrend.iloc[i-1]:
            curr_lower = max(lowerband.iloc[i], supertrend.iloc[i-1]) if direction.iloc[i-1] == 1 else lowerband.iloc[i]
        else:
            curr_lower = lowerband.iloc[i]

        if direction.iloc[i-1] == 1:
            if close.iloc[i] < curr_lower:
                direction.iloc[i] = -1
                supertrend.iloc[i] = curr_upper
            else:
                direction.iloc[i] = 1
                supertrend.iloc[i] = curr_lower
        else:
            if close.iloc[i] > curr_upper:
                direction.iloc[i] = 1
                supertrend.iloc[i] = curr_lower
            else:
                direction.iloc[i] = -1
                supertrend.iloc[i] = curr_upper

    df['supertrend'] = supertrend
    df['st_direction'] = direction

    grp = (direction != direction.shift()).cumsum()
    df['st_streak'] = direction.groupby(grp).cumcount() + 1
    return df


# ---------------------------------------------------------
# 4. 거래량 Up/Down Ratio (최근 20일)
# ---------------------------------------------------------
def calc_volume_ratio(df, window=20):
    price_up = df['Close'] > df['Close'].shift()
    up_vol = df['Volume'].where(price_up, 0).rolling(window).sum()
    down_vol = df['Volume'].where(~price_up, 0).rolling(window).sum()
    df['up_down_vol_ratio'] = up_vol / down_vol.replace(0, np.nan)
    return df


# ---------------------------------------------------------
# 5. 종합 판단
# ---------------------------------------------------------
def classify_trend_stage(row):
    """
    반환: '초입(브레이크아웃)' / '중반(눌림목)' / '약화' / '횡보' / '하락추세'
    """
    adx = row.get('adx', np.nan)
    ma_bull = row.get('ma_bullish', False)
    ma_bull_streak = row.get('ma_bullish_streak', 0)
    st_dir = row.get('st_direction', 0)
    st_streak = row.get('st_streak', 0)
    vol_ratio = row.get('up_down_vol_ratio', np.nan)

    if pd.isna(adx):
        return '데이터부족'

    if row.get('ma_bearish', False) and adx >= 20:
        return '하락추세'

    if not ma_bull:
        return '횡보/미정'

    if adx < 20:
        return '횡보(추세약함)'

    # 여기서부터 ma_bull=True, adx>=20
    strong_confirm = (st_dir == 1) and (st_streak >= 5) and (not pd.isna(vol_ratio) and vol_ratio >= 1.2)

    if ma_bull_streak <= 5 or st_streak <= 5:
        # 정배열/Supertrend 상승 전환 초기 → 초입 국면
        if strong_confirm or (st_dir == 1 and adx >= 25):
            return '초입(브레이크아웃 매수)'
        return '초입_확인필요'
    else:
        # 정배열 5일 이상 유지 = 성숙 단계
        if adx >= 25 and st_dir == 1:
            return '중반(눌림목 매수)'
        elif adx < 25:
            return '중반_약화신호'
        else:
            return '중반(관망)'


def analyze_ticker(ticker, period='1y'):
    df = yf.download(ticker, period=period, interval='1d', progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df.empty or len(df) < 200:
        return None, None

    df = calc_adx(df)
    df = calc_ma_alignment(df)
    df = calc_supertrend(df)
    df = calc_volume_ratio(df)
    df['trend_stage'] = df.apply(classify_trend_stage, axis=1)

    latest = df.iloc[-1]
    summary = {
        'ticker': ticker,
        'close': round(latest['Close'], 2),
        'adx': round(latest['adx'], 1) if not pd.isna(latest['adx']) else None,
        'ma_bullish': bool(latest['ma_bullish']),
        'ma_bullish_streak': int(latest['ma_bullish_streak']),
        'st_direction': int(latest['st_direction']),
        'st_streak': int(latest['st_streak']),
        'up_down_vol_ratio': round(latest['up_down_vol_ratio'], 2) if not pd.isna(latest['up_down_vol_ratio']) else None,
        'trend_stage': latest['trend_stage'],
    }
    return summary, df


if __name__ == '__main__':
    watchlist = ['SOXX', 'SMH', 'MU', 'NVDA', 'QQQ', 'SPY']
    results = []
    for t in watchlist:
        summary, df = analyze_ticker(t)
        if summary:
            results.append(summary)
            print(f"\n{'='*50}")
            print(f"{t}")
            print(f"{'='*50}")
            for k, v in summary.items():
                print(f"  {k}: {v}")

    print("\n\n=== 요약 테이블 ===")
    res_df = pd.DataFrame(results)
    print(res_df.to_string(index=False))
