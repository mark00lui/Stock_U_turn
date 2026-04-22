"""Breakout signal detection — N-day high + volume gate + clean breakout."""
import pandas as pd
import numpy as np
from indicators import calc_highest, calc_volume_ratio, calc_rsi, calc_atr
from config import VOLUME_RATIO_GATE, MIN_DAILY_VALUE_NTD, MIN_HISTORY_DAYS


def detect_breakout(df: pd.DataFrame) -> dict | None:
    """Score a stock for breakout signals with volume gate.

    Hard gates (fail any → return None):
      A. >= 60 days of history
      B. 20-day avg daily value >= NT$3億 (liquidity floor)
      C. volume_ratio (today / 20d avg) >= 1.2x (volume confirmation)

    Scoring (after gates pass):
      1. Near 60-day high (+2 within 1%, +1 within 3%)
      2. Volume surge bonus (+1.5 if >=2x, +0.5 if >=1.3x)
      3. RSI < 80 (+0.5 below 70, penalty -1 if >= 80)
      4. 3-day gain > 5% (+1), > 3% (+0.5)
      5. ATR expansion (+0.5)

    Returns dict with scoring info, or None if no signal.
    """
    if len(df) < MIN_HISTORY_DAYS:
        return None  # Gate A — new listing guard

    close = df["Close"]
    high = df["High"] if "High" in df.columns else close
    low = df["Low"] if "Low" in df.columns else close
    volume = df["Volume"] if "Volume" in df.columns else None
    if volume is None:
        return None

    # Gate B + C — volume & liquidity
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

    price_recent = close.iloc[-20:]
    daily_value_avg = (price_recent * vol_recent).mean()
    if pd.isna(daily_value_avg) or daily_value_avg < MIN_DAILY_VALUE_NTD:
        return None  # Gate B — liquidity floor fails

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
