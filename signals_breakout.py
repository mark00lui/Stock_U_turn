"""Breakout signal detection — N-day high + 20日主閘/6月地板 volume gate."""
import pandas as pd
import numpy as np
from indicators import calc_highest, calc_volume_ratio, calc_rsi, calc_atr
from config import (
    VOLUME_RATIO_GATE,
    VOLUME_RATIO_6M_FLOOR,
    MIN_DAILY_VALUE_NTD,
    MIN_DAILY_VALUE_MA120,
    MIN_HISTORY_DAYS,
)


def detect_breakout(df: pd.DataFrame) -> dict | None:
    """Score a stock for breakout signals with 20日主閘+6月地板 volume gate.

    Hard gates (fail any → return None):
      A. >= 140 days of history
      B1. today daily value (close × volume) >= NT$1.5億
      B2. MA120 daily value >= NT$1.5億
      C1. today / MA20 volume ratio >= 1.2x (主閘)
      C2. today / MA120 volume ratio >= 0.8x (6月地板)
    """
    if len(df) < MIN_HISTORY_DAYS:
        return None

    close = df["Close"]
    high = df["High"] if "High" in df.columns else close
    low = df["Low"] if "Low" in df.columns else close
    volume = df["Volume"] if "Volume" in df.columns else None
    if volume is None:
        return None

    c_now = close.iloc[-1]
    vol_now = volume.iloc[-1]
    if pd.isna(c_now) or c_now <= 0 or pd.isna(vol_now) or vol_now == 0:
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

    # Gate C2 — 6-month volume floor
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
    rsi = calc_rsi(close, 14)
    rsi_now = rsi.iloc[-1]
    h60 = calc_highest(close, 60)
    h60_now = h60.iloc[-1]

    if pd.isna(h60_now) or pd.isna(rsi_now):
        return None

    score = 0.0
    descriptions = []

    dist_from_high = (c_now / h60_now - 1) * 100
    if dist_from_high >= -1:
        score += 2
        if c_now >= h60_now:
            descriptions.append("創60日新高")
        else:
            descriptions.append("逼近60日高")
    elif dist_from_high >= -3:
        score += 1
        descriptions.append("接近60日高")
    else:
        return None

    vr = calc_volume_ratio(volume, 20)
    vr_now = vr.iloc[-1]
    if not pd.isna(vr_now) and vr_now > 2.0:
        score += 1.5
        descriptions.append(f"量增{vr_now:.1f}x")
    elif not pd.isna(vr_now) and vr_now > 1.3:
        score += 0.5
        descriptions.append(f"微量增{vr_now:.1f}x")

    if rsi_now < 70:
        score += 0.5
        descriptions.append(f"RSI{rsi_now:.0f}未超買")
    elif rsi_now < 80:
        descriptions.append(f"RSI{rsi_now:.0f}")
    else:
        score -= 1
        descriptions.append(f"RSI{rsi_now:.0f}過熱")

    if len(close) >= 4:
        gain_3d = (c_now / close.iloc[-4] - 1) * 100
        if gain_3d > 5:
            score += 1
            descriptions.append(f"3日漲{gain_3d:.1f}%")
        elif gain_3d > 3:
            score += 0.5
            descriptions.append(f"3日漲{gain_3d:.1f}%")

    atr = calc_atr(high, low, close, 14)
    atr_now = atr.iloc[-1]
    atr_prev = atr.iloc[-6] if len(atr) >= 6 else atr_now
    if not pd.isna(atr_now) and not pd.isna(atr_prev) and atr_prev > 0:
        atr_change = (atr_now / atr_prev - 1) * 100
        if atr_change > 20:
            score += 0.5
            descriptions.append("波動擴張")

    if score < 2 or not descriptions:
        return None

    if score >= 4.5:
        stars, level = 5, "strong"
    elif score >= 3.5:
        stars, level = 4, "strong"
    elif score >= 2.5:
        stars, level = 3, "medium"
    elif score >= 2:
        stars, level = 2, "medium"
    else:
        stars, level = 1, "watch"

    return {
        "score": round(score, 1),
        "stars": stars,
        "level": level,
        "descriptions": descriptions,
        "rsi": round(float(rsi_now), 1),
        "high_60d": round(float(h60_now), 2),
        "dist_from_high": round(dist_from_high, 2),
    }
