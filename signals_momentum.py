"""Momentum signal detection — MA breakout + volume gate + trend confirmation."""
import pandas as pd
import numpy as np
from indicators import calc_ma, calc_ma_slope, calc_volume_ratio, calc_rsi, calc_atr
from config import VOLUME_RATIO_GATE, MIN_DAILY_VALUE_NTD, MIN_HISTORY_DAYS


def detect_momentum(df: pd.DataFrame) -> dict | None:
    """Score a stock for momentum breakout signals with volume gate.

    Hard gates (fail any → return None):
      A. >= 60 days of history
      B. 20-day avg daily value >= NT$3億 (liquidity floor)
      C. volume_ratio (today / 20d avg) >= 1.2x (volume confirmation)

    Scoring (after gates pass):
      1. Price above 20MA (+1), fresh breakout (+1.5)
      2. 20MA trending up (+1)
      3. Volume surge bonus (+1 if >=1.5x, +0.5 if >=2.5x)
      4. RSI in momentum zone 50-70 (+0.5); >70 penalty (-0.5)
      5. Above 60MA long-term trend (+0.5)

    Returns dict with scoring info, or None if no signal.
    """
    if len(df) < MIN_HISTORY_DAYS:
        return None  # Gate A — new listing guard

    close = df["Close"]
    volume = df["Volume"] if "Volume" in df.columns else None
    if volume is None:
        return None

    # Gate B + C — volume & liquidity computed first (cheap, short-circuit)
    vol_recent = volume.iloc[-20:].replace(0, np.nan)
    avg_vol = vol_recent.mean()
    if pd.isna(avg_vol) or avg_vol <= 0:
        return None
    vol_now = volume.iloc[-1]
    if pd.isna(vol_now) or vol_now == 0:
        return None
    volume_ratio = vol_now / avg_vol
    if volume_ratio < VOLUME_RATIO_GATE:
        return None  # Gate C — volume confirmation fails

    # 20-day avg daily value (price × volume) in TWD
    price_recent = close.iloc[-20:]
    daily_value_avg = (price_recent * vol_recent).mean()
    if pd.isna(daily_value_avg) or daily_value_avg < MIN_DAILY_VALUE_NTD:
        return None  # Gate B — liquidity floor fails

    ma20 = calc_ma(close, 20)
    ma60 = calc_ma(close, 60)
    slope = calc_ma_slope(ma20, 5)
    rsi = calc_rsi(close, 14)

    c = close.iloc[-1]
    ma20_now = ma20.iloc[-1]
    ma60_now = ma60.iloc[-1] if not pd.isna(ma60.iloc[-1]) else ma20_now
    slope_now = slope.iloc[-1]
    rsi_now = rsi.iloc[-1]

    if pd.isna(c) or pd.isna(ma20_now) or pd.isna(rsi_now):
        return None

    score = 0.0
    descriptions = []

    # 1. Price above 20MA
    if c > ma20_now:
        score += 1
        descriptions.append("站上20MA")

        # Fresh breakout: was below 20MA within last 5 days
        recent_below = (close.iloc[-6:-1] < ma20.iloc[-6:-1]).any()
        if recent_below:
            score += 1.5
            descriptions.append("突破20MA")

    # 2. 20MA trending up
    if not pd.isna(slope_now) and slope_now > 0.5:
        score += 1
        descriptions.append(f"20MA上升({slope_now:+.1f}%)")

    # 3. Volume surge
    if volume is not None:
        vr = calc_volume_ratio(volume, 20)
        vr_now = vr.iloc[-1]
        if not pd.isna(vr_now) and vr_now > 1.5:
            score += 1
            descriptions.append(f"量增{vr_now:.1f}x")
        if not pd.isna(vr_now) and vr_now > 2.5:
            score += 0.5
            descriptions.append("爆量")

    # 4. RSI in momentum zone (50-70)
    if 50 <= rsi_now <= 70:
        score += 0.5
        descriptions.append(f"動能區RSI{rsi_now:.0f}")
    elif rsi_now > 70:
        score -= 0.5  # overbought penalty
        descriptions.append(f"超買RSI{rsi_now:.0f}")

    # 5. Bonus: above 60MA (long-term trend)
    if c > ma60_now and not pd.isna(ma60_now):
        score += 0.5
        descriptions.append("長線多頭")

    if score < 1.5 or not descriptions:
        return None

    # Stars
    if score >= 4.5:
        stars, level = 5, "strong"
    elif score >= 3.5:
        stars, level = 4, "strong"
    elif score >= 2.5:
        stars, level = 3, "medium"
    elif score >= 1.5:
        stars, level = 2, "medium"
    else:
        stars, level = 1, "watch"

    return {
        "score": round(score, 1),
        "stars": stars,
        "level": level,
        "descriptions": descriptions,
        "rsi": round(float(rsi_now), 1),
        "ma20": round(float(ma20_now), 2),
        "ma20_slope": round(float(slope_now), 2) if not pd.isna(slope_now) else 0,
    }
