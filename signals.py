"""Reversal signal detection — RSI oversold bounce + MACD golden cross."""
import math

import pandas as pd

import config


def detect_reversal(df: pd.DataFrame) -> dict | None:
    """Score a single stock for bottom-reversal signals.

    *df* must contain columns: ``Close``, ``rsi``, ``macd``,
    ``macd_signal``, ``macd_hist``.

    Returns a dict with scoring info, or ``None`` if no signal.
    """
    if len(df) < config.LOOKBACK_DAYS + 2:
        return None

    lb = config.LOOKBACK_DAYS

    rsi_now = df["rsi"].iloc[-1]
    macd_now = df["macd"].iloc[-1]
    hist_now = df["macd_hist"].iloc[-1]

    if pd.isna(rsi_now) or pd.isna(hist_now):
        return None

    # ── RSI signals ────────────────────────────────────
    rsi_signals: list[tuple[str, float]] = []

    recent_rsi = df["rsi"].iloc[-(lb + 1) :]
    was_oversold = (recent_rsi.iloc[:-1] < config.RSI_OVERSOLD).any()
    recovering = rsi_now >= config.RSI_OVERSOLD

    if was_oversold and recovering:
        rsi_signals.append(("RSI 超賣反彈", 2))
    elif rsi_now < config.RSI_OVERSOLD:
        rsi_signals.append(("RSI 超賣區", 1))
    elif rsi_now < config.RSI_RECOVERY:
        rsi_signals.append(("RSI 低檔區", 0.5))

    # ── MACD signals ───────────────────────────────────
    macd_signals: list[tuple[str, float]] = []

    recent_hist = df["macd_hist"].iloc[-(lb + 1) :]
    for i in range(1, len(recent_hist)):
        if recent_hist.iloc[i - 1] < 0 and recent_hist.iloc[i] >= 0:
            macd_signals.append(("MACD 金叉", 2))
            break

    if not macd_signals and hist_now < 0:
        hist_prev = df["macd_hist"].iloc[-2]
        if not pd.isna(hist_prev) and hist_now > hist_prev:
            macd_signals.append(("MACD 柱收斂", 1))

    # ── Combine ────────────────────────────────────────
    all_sigs = rsi_signals + macd_signals
    if not all_sigs:
        return None

    score = sum(s[1] for s in all_sigs)
    descriptions = [s[0] for s in all_sigs]

    # bonus for being in bottom territory (MACD < 0)
    if macd_now < 0 and score >= 2:
        score += 0.5
        descriptions.append("底部區域")

    # map to stars
    if score >= 4:
        stars = 5
        level = "strong"
    elif score >= 3:
        stars = 4
        level = "strong"
    elif score >= 2:
        stars = 3
        level = "medium"
    elif score >= 1.5:
        stars = 2
        level = "medium"
    else:
        stars = 1
        level = "watch"

    macd_signal_val = df["macd_signal"].iloc[-1]

    return {
        "score": score,
        "stars": stars,
        "level": level,
        "descriptions": descriptions,
        "rsi": round(float(rsi_now), 1),
        "macd": round(float(macd_now), 4),
        "macd_signal_val": round(float(macd_signal_val), 4),
        "macd_hist": round(float(hist_now), 4),
    }
