"""Momentum signal detection — MA breakout + 20日主閘/6月地板 volume gate."""
import pandas as pd
import numpy as np
from indicators import calc_ma, calc_ma_slope, calc_volume_ratio, calc_rsi, calc_atr
from config import (
    VOLUME_RATIO_GATE,
    VOLUME_RATIO_6M_FLOOR,
    MIN_DAILY_VALUE_NTD,
    MIN_DAILY_VALUE_MA120,
    MIN_HISTORY_DAYS,
)


def detect_momentum(df: pd.DataFrame) -> dict | None:
    """Score a stock for momentum breakout signals with 20日主閘+6月地板 volume gate.

    Hard gates (fail any → return None):
      A. >= 140 days of history
      B1. today daily value (close × volume) >= NT$1.5億
      B2. MA120 daily value >= NT$1.5億
      C1. today / MA20 volume ratio >= 1.2x (主閘，保即時性)
      C2. today / MA120 volume ratio >= 0.8x (6月絕對量地板)

    Scoring (after gates pass):
      1. Price above 20MA (+1), fresh breakout (+1.5)
      2. 20MA trending up (+1)
      3. Volume surge bonus (+1 if >=1.5x, +0.5 if >=2.5x)
      4. RSI in momentum zone 50-70 (+0.5); >70 penalty (-0.5)
      5. Above 60MA long-term trend (+0.5)
    """
    if len(df) < MIN_HISTORY_DAYS:
        return None  # Gate A

    close = df["Close"]
    volume = df["Volume"] if "Volume" in df.columns else None
    if volume is None:
        return None

    vol_now = volume.iloc[-1]
    c_now = close.iloc[-1]
    if pd.isna(vol_now) or vol_now == 0 or pd.isna(c_now):
        return None

    # Gate B1 — today daily value floor
    if (c_now * vol_now) < MIN_DAILY_VALUE_NTD:
        return None

    # Gate C1 — 20d volume ratio (primary)
    vol_20 = volume.iloc[-20:].replace(0, np.nan)
    ma20_vol = vol_20.mean()
    if pd.isna(ma20_vol) or ma20_vol <= 0:
        return None
    if (vol_now / ma20_vol) < VOLUME_RATIO_GATE:
        return None

    # Gate C2 — 6-month volume floor (absolute量地板)
    vol_120 = volume.iloc[-120:].replace(0, np.nan)
    ma120_vol = vol_120.mean()
    if pd.isna(ma120_vol) or ma120_vol <= 0:
        return None
    if vol_now < ma120_vol * VOLUME_RATIO_6M_FLOOR:
        return None

    # Gate B2 — MA120 daily value floor
    dv_120 = (close.iloc[-120:] * vol_120).mean()
    if pd.isna(dv_120) or dv_120 < MIN_DAILY_VALUE_MA120:
        return None

    # ── Scoring ──────────────────────────────
    ma20 = calc_ma(close, 20)
    ma60 = calc_ma(close, 60)
    slope = calc_ma_slope(ma20, 5)
    rsi = calc_rsi(close, 14)

    ma20_now = ma20.iloc[-1]
    ma60_now = ma60.iloc[-1] if not pd.isna(ma60.iloc[-1]) else ma20_now
    slope_now = slope.iloc[-1]
    rsi_now = rsi.iloc[-1]

    if pd.isna(ma20_now) or pd.isna(rsi_now):
        return None

    score = 0.0
    descriptions = []

    # 1. Price above 20MA
    if c_now > ma20_now:
        score += 1
        descriptions.append("站上20MA")
        recent_below = (close.iloc[-6:-1] < ma20.iloc[-6:-1]).any()
        if recent_below:
            score += 1.5
            descriptions.append("突破20MA")

    # 2. 20MA trending up
    if not pd.isna(slope_now) and slope_now > 0.5:
        score += 1
        descriptions.append(f"20MA上升({slope_now:+.1f}%)")

    # 3. Volume surge bonus
    vr = calc_volume_ratio(volume, 20)
    vr_now = vr.iloc[-1]
    if not pd.isna(vr_now) and vr_now > 1.5:
        score += 1
        descriptions.append(f"量增{vr_now:.1f}x")
    if not pd.isna(vr_now) and vr_now > 2.5:
        score += 0.5
        descriptions.append("爆量")

    # 4. RSI momentum zone
    if 50 <= rsi_now <= 70:
        score += 0.5
        descriptions.append(f"動能區RSI{rsi_now:.0f}")
    elif rsi_now > 70:
        score -= 0.5
        descriptions.append(f"超買RSI{rsi_now:.0f}")

    # 5. Long-term trend above 60MA
    if c_now > ma60_now and not pd.isna(ma60_now):
        score += 0.5
        descriptions.append("長線多頭")

    if score < 1.5 or not descriptions:
        return None

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
