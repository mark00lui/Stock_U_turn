"""Breakout signal detection — N-day high + volume surge + clean breakout."""
import pandas as pd
import numpy as np
from indicators import calc_highest, calc_volume_ratio, calc_rsi, calc_atr


def detect_breakout(df: pd.DataFrame) -> dict | None:
    """Score a stock for breakout signals.

    Conditions:
    1. Price at or near 60-day high (within 2%)
    2. Volume > 2x 20-day average (breakout confirmation)
    3. RSI < 80 (not extremely overbought)
    4. ATR expanding (volatility breakout)
    5. Price gained > 3% in last 3 days (momentum)

    Returns dict with scoring info, or None if no signal.
    """
    if len(df) < 65:
        return None

    close = df["Close"]
    high = df["High"] if "High" in df.columns else close
    low = df["Low"] if "Low" in df.columns else close
    volume = df["Volume"] if "Volume" in df.columns else None

    c = close.iloc[-1]
    rsi = calc_rsi(close, 14)
    rsi_now = rsi.iloc[-1]
    h60 = calc_highest(close, 60)
    h60_now = h60.iloc[-1]

    if pd.isna(c) or pd.isna(h60_now) or pd.isna(rsi_now) or c <= 0:
        return None

    score = 0.0
    descriptions = []

    # 1. Near 60-day high
    dist_from_high = (c / h60_now - 1) * 100
    if dist_from_high >= -1:  # within 1% of 60d high
        score += 2
        if c >= h60_now:
            descriptions.append("創60日新高")
        else:
            descriptions.append("逼近60日高")
    elif dist_from_high >= -3:
        score += 1
        descriptions.append("接近60日高")
    else:
        return None  # too far from high, not a breakout

    # 2. Volume surge
    if volume is not None:
        vr = calc_volume_ratio(volume, 20)
        vr_now = vr.iloc[-1]
        if not pd.isna(vr_now) and vr_now > 2.0:
            score += 1.5
            descriptions.append(f"量增{vr_now:.1f}x")
        elif not pd.isna(vr_now) and vr_now > 1.3:
            score += 0.5
            descriptions.append(f"微量增{vr_now:.1f}x")

    # 3. RSI check
    if rsi_now < 70:
        score += 0.5
        descriptions.append(f"RSI{rsi_now:.0f}未超買")
    elif rsi_now < 80:
        descriptions.append(f"RSI{rsi_now:.0f}")
    else:
        score -= 1
        descriptions.append(f"RSI{rsi_now:.0f}過熱")

    # 4. Recent momentum (3-day gain)
    if len(close) >= 4:
        gain_3d = (c / close.iloc[-4] - 1) * 100
        if gain_3d > 5:
            score += 1
            descriptions.append(f"3日漲{gain_3d:.1f}%")
        elif gain_3d > 3:
            score += 0.5
            descriptions.append(f"3日漲{gain_3d:.1f}%")

    # 5. ATR expansion
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
