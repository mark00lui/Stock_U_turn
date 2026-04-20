"""Mean-reversion signal detection — Bollinger Band bounce + oversold conditions."""
import pandas as pd
import numpy as np
from indicators import calc_bollinger, calc_rsi, calc_volume_ratio, calc_ma


def detect_meanrevert(df: pd.DataFrame) -> dict | None:
    """Score a stock for Bollinger Band mean-reversion signals.

    Conditions:
    1. Price touched or went below lower Bollinger Band (2σ) recently
    2. Price is now bouncing back above lower band
    3. RSI < 35 (oversold confirmation)
    4. Volume increasing on bounce day
    5. Price still below middle band (room to run)

    Returns dict with scoring info, or None if no signal.
    """
    if len(df) < 25:
        return None

    close = df["Close"]
    volume = df["Volume"] if "Volume" in df.columns else None

    mid, upper, lower = calc_bollinger(close, 20, 2.0)
    rsi = calc_rsi(close, 14)

    c = close.iloc[-1]
    mid_now = mid.iloc[-1]
    lower_now = lower.iloc[-1]
    upper_now = upper.iloc[-1]
    rsi_now = rsi.iloc[-1]

    if pd.isna(c) or pd.isna(mid_now) or pd.isna(lower_now) or pd.isna(rsi_now):
        return None

    score = 0.0
    descriptions = []

    # 1. Touched lower band recently (within 5 days)
    recent_close = close.iloc[-6:]
    recent_lower = lower.iloc[-6:]
    touched_lower = False
    for i in range(len(recent_close)):
        rc = recent_close.iloc[i]
        rl = recent_lower.iloc[i]
        if not pd.isna(rc) and not pd.isna(rl) and rc <= rl * 1.005:
            touched_lower = True
            break

    if not touched_lower:
        return None  # Must have touched lower band

    # 2. Now bouncing (current price above lower band)
    if c > lower_now:
        score += 2
        if c <= lower_now * 1.02:
            descriptions.append("布林下軌反彈")
        else:
            descriptions.append("脫離布林下軌")
    else:
        score += 1
        descriptions.append("布林下軌附近")

    # 3. RSI oversold
    if rsi_now < 25:
        score += 2
        descriptions.append(f"RSI{rsi_now:.0f}極度超賣")
    elif rsi_now < 30:
        score += 1.5
        descriptions.append(f"RSI{rsi_now:.0f}超賣")
    elif rsi_now < 35:
        score += 1
        descriptions.append(f"RSI{rsi_now:.0f}低檔")
    elif rsi_now < 45:
        score += 0.5
        descriptions.append(f"RSI{rsi_now:.0f}")

    # 4. Volume on bounce
    if volume is not None:
        vr = calc_volume_ratio(volume, 20)
        vr_now = vr.iloc[-1]
        if not pd.isna(vr_now) and vr_now > 1.5:
            score += 1
            descriptions.append(f"反彈量增{vr_now:.1f}x")

    # 5. Below middle band (room to revert to mean)
    if c < mid_now:
        bb_position = (c - lower_now) / (upper_now - lower_now) * 100 if upper_now != lower_now else 50
        score += 0.5
        descriptions.append(f"BB位置{bb_position:.0f}%")

    # 6. Bounce confirmation: today's close > yesterday's close
    if len(close) >= 2 and c > close.iloc[-2]:
        score += 0.5
        descriptions.append("日K反彈")

    if score < 2 or not descriptions:
        return None

    if score >= 5:
        stars, level = 5, "strong"
    elif score >= 4:
        stars, level = 4, "strong"
    elif score >= 3:
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
        "bb_lower": round(float(lower_now), 2),
        "bb_mid": round(float(mid_now), 2),
        "bb_upper": round(float(upper_now), 2),
    }
