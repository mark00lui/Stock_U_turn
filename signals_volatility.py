"""Volatility analyst — 200-day derivative, Fibonacci time zone, damped oscillation.

For each stock in the (liquidity-filtered) universe this module:
  1.  Smooths the last 200 trading-day close with a Savitzky-Golay filter.
  2.  Computes the 1st (velocity) and 2nd (acceleration) derivatives.
  3.  Detects historical local extrema via scipy.signal.find_peaks (prominence
      gated by the smoothed series' std).
  4.  Projects Fibonacci time zones (1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144 days)
      forward from the most-recent major swing low and swing high.
  5.  Fits a damped harmonic oscillator  x(t) = A·e^(-γt)·cos(ωt+φ) + c  to
      detrended residuals; predicts the next zero-crossing of the oscillator
      as the next price turning point.
  6.  Ensembles the three methods to estimate "days until next local min" and
      "days until next local max" within a 30-day horizon.
  7.  Scores 0-10 — high = near a local minimum with multi-method agreement.

CLI:
    python signals_volatility.py --export
    → writes data/signals_volatility.json
"""
from __future__ import annotations

import sys
import io
import json
import argparse
import warnings
from datetime import date

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter, find_peaks
from scipy.optimize import curve_fit, OptimizeWarning

import config
from config import DATA_DIR


LOOKBACK = 200                           # trading days analysed per stock
SAVGOL_WINDOW = 21                       # must be odd; ~1 month smoothing
SAVGOL_POLY = 3
FIB = (1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144)
FORWARD_HORIZON = 30                     # projection cap (trading days)
PEAK_DISTANCE = 12                       # min trading days between extrema
PEAK_PROMINENCE_MULT = 0.25              # prominence ≥ 0.25 × residual std


# ── helpers ──────────────────────────────────────────────────────────────────

def _smooth(close: np.ndarray) -> np.ndarray:
    window = min(SAVGOL_WINDOW, len(close) // 2 * 2 - 1)
    if window < 5:
        return close.copy()
    return savgol_filter(close, window_length=window, polyorder=SAVGOL_POLY)


def _detect_extrema(smooth: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (low_indices, high_indices) of historical local extrema."""
    rng = float(np.nanmax(smooth) - np.nanmin(smooth))
    prom = max(rng * 0.02, np.nanstd(smooth) * PEAK_PROMINENCE_MULT)
    highs, _ = find_peaks(smooth, distance=PEAK_DISTANCE, prominence=prom)
    lows, _ = find_peaks(-smooth, distance=PEAK_DISTANCE, prominence=prom)
    return lows, highs


def _classify_regime(d1: float, d2: float) -> str:
    if d1 >= 0 and d2 >= 0:
        return "accelerating_up"
    if d1 >= 0 and d2 < 0:
        return "decelerating_up"        # approaching local max
    if d1 < 0 and d2 < 0:
        return "accelerating_down"
    return "decelerating_down"           # approaching local min


def _derivative_extrapolation(d1: float, d2: float) -> tuple[int | None, int | None]:
    """Linear time-to-zero estimate for the 1st derivative.

    If d1 < 0 and d2 > 0  → next zero crossing is a local min.
    If d1 > 0 and d2 < 0  → next zero crossing is a local max.
    Other regimes return None for that direction.
    """
    days_to_min: int | None = None
    days_to_max: int | None = None
    if d1 < 0 < d2:
        days_to_min = int(round(-d1 / d2))
    elif d1 > 0 > d2:
        days_to_max = int(round(-d1 / d2))
    if days_to_min is not None and not (1 <= days_to_min <= FORWARD_HORIZON):
        days_to_min = None
    if days_to_max is not None and not (1 <= days_to_max <= FORWARD_HORIZON):
        days_to_max = None
    return days_to_min, days_to_max


def _fibonacci_projection(lows: np.ndarray, highs: np.ndarray, t_now: int
                          ) -> tuple[list[int], list[int], list[int]]:
    """Project Fib time zones forward from the most-recent major low and high.

    Returns (min_days, max_days, all_pivot_days):
      min_days   — forward offsets projected from last major HIGH (a high tends
                   to cycle into the next low).
      max_days   — forward offsets projected from last major LOW.
      pivot_days — union of the two (unsigned pivot day candidates).
    """
    min_days: list[int] = []
    max_days: list[int] = []
    if len(highs):
        last_high = int(highs[-1])
        for f in FIB:
            offset = last_high + f - t_now
            if 1 <= offset <= FORWARD_HORIZON:
                min_days.append(offset)
    if len(lows):
        last_low = int(lows[-1])
        for f in FIB:
            offset = last_low + f - t_now
            if 1 <= offset <= FORWARD_HORIZON:
                max_days.append(offset)
    pivots = sorted(set(min_days + max_days))
    return min_days, max_days, pivots


def _damped_oscillator(t: np.ndarray, A: float, gamma: float,
                       omega: float, phi: float, c: float) -> np.ndarray:
    return A * np.exp(-gamma * t) * np.cos(omega * t + phi) + c


def _fit_damped(smooth: np.ndarray) -> dict | None:
    """Fit damped harmonic oscillator to detrended residuals.

    Returns dict with amplitude, damping, period_days, days_to_next_extremum,
    next_extremum_type ('min' or 'max'), and r2 — or None if the fit fails
    or the period is unphysical.
    """
    n = len(smooth)
    t = np.arange(n, dtype=float)
    trend_coef = np.polyfit(t, smooth, 2)
    residual = smooth - np.polyval(trend_coef, t)

    if np.nanstd(residual) == 0:
        return None

    # Crude period seed from the dominant FFT bin (DC excluded).
    fft = np.abs(np.fft.rfft(residual - residual.mean()))
    freqs = np.fft.rfftfreq(n)
    if len(fft) < 3:
        return None
    bin_idx = int(np.argmax(fft[1:]) + 1)
    f0 = max(freqs[bin_idx], 1.0 / n)
    omega0 = 2 * np.pi * f0
    p0 = [np.nanstd(residual), 0.005, omega0, 0.0, 0.0]
    bounds = (
        [0.0,                 0.0,    omega0 * 0.3, -np.pi, -abs(residual).max()],
        [abs(residual).max()*3, 0.05, omega0 * 3.0,  np.pi,  abs(residual).max()],
    )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", OptimizeWarning)
            warnings.simplefilter("ignore", RuntimeWarning)
            popt, _ = curve_fit(_damped_oscillator, t, residual, p0=p0,
                                bounds=bounds, maxfev=2000)
    except Exception:
        return None

    A, gamma, omega, phi, c = popt
    if omega <= 0 or not np.isfinite(omega):
        return None
    period = 2 * np.pi / omega
    if period < 6 or period > 200:
        return None

    pred = _damped_oscillator(t, *popt)
    ss_res = float(np.sum((residual - pred) ** 2))
    ss_tot = float(np.sum((residual - residual.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # next extremum of A·cos(ωt+φ) occurs when ωt+φ = kπ. We want the smallest
    # k such that t > t_now = n-1.
    t_now = float(n - 1)
    phase_now = omega * t_now + phi
    k_now = phase_now / np.pi
    k_next = int(np.ceil(k_now))
    if abs(k_next - k_now) < 1e-6:
        k_next += 1
    t_next = (k_next * np.pi - phi) / omega
    days_next = int(round(t_next - t_now))
    if days_next < 1 or days_next > FORWARD_HORIZON:
        return {
            "amplitude": float(A),
            "damping": float(gamma),
            "period_days": float(period),
            "r2": float(r2),
            "next_type": None,
            "next_days": None,
        }

    # cos(kπ) = +1 (k even) → max; cos(kπ) = -1 (k odd) → min.
    # Sign of price residual at the extremum is sign(A)·cos(kπ).
    sign_of_A = 1 if A >= 0 else -1
    cos_val = 1 if k_next % 2 == 0 else -1
    is_max = sign_of_A * cos_val > 0
    return {
        "amplitude": float(A),
        "damping": float(gamma),
        "period_days": float(period),
        "r2": float(r2),
        "next_type": "max" if is_max else "min",
        "next_days": days_next,
    }


def _ensemble(d_min: int | None, d_max: int | None,
              fib_min: list[int], fib_max: list[int],
              damped: dict | None) -> tuple[int | None, int | None, int]:
    """Return (days_to_min, days_to_max, methods_agreeing).

    methods_agreeing counts how many of {deriv, fib, damped} contribute a
    plausible forward estimate (1-3).
    """
    min_candidates: list[int] = []
    max_candidates: list[int] = []
    methods_min = 0
    methods_max = 0

    if d_min is not None:
        min_candidates.append(d_min); methods_min += 1
    if d_max is not None:
        max_candidates.append(d_max); methods_max += 1

    if fib_min:
        min_candidates.append(min(fib_min)); methods_min += 1
    if fib_max:
        max_candidates.append(min(fib_max)); methods_max += 1

    if damped and damped.get("next_type") == "min" and damped.get("next_days"):
        min_candidates.append(int(damped["next_days"])); methods_min += 1
    if damped and damped.get("next_type") == "max" and damped.get("next_days"):
        max_candidates.append(int(damped["next_days"])); methods_max += 1

    days_to_min = int(round(float(np.mean(min_candidates)))) if min_candidates else None
    days_to_max = int(round(float(np.mean(max_candidates)))) if max_candidates else None
    return days_to_min, days_to_max, max(methods_min, methods_max)


def _score(regime: str, days_to_min: int | None,
           days_to_max: int | None, methods: int) -> tuple[float, str]:
    # Regime base score (0-4)
    base = {
        "decelerating_down": 4.0,        # near local min — entry zone
        "accelerating_down": 2.0,        # downtrend, wait
        "accelerating_up":   2.0,        # uptrend, late entry
        "decelerating_up":   0.0,        # near local max — exit zone
    }.get(regime, 1.0)

    # Proximity to local min (0-3)
    if days_to_min is None:
        proxim = 0.0
    elif days_to_min <= 5:
        proxim = 3.0
    elif days_to_min <= 15:
        proxim = 2.0
    elif days_to_min <= 30:
        proxim = 1.0
    else:
        proxim = 0.0

    # Method-agreement bonus (0-3)
    agree = float(max(0, min(3, methods)))

    # Penalty if local max is imminent (high≤5 days)
    penalty = 1.5 if days_to_max is not None and days_to_max <= 5 else 0.0

    score = max(0.0, min(10.0, base + proxim + agree - penalty))
    if score >= 7.0:
        verdict = "BUY_NEAR_MIN"
    elif score >= 5.0:
        verdict = "WATCH"
    elif score >= 3.0:
        verdict = "NEUTRAL"
    else:
        verdict = "EXIT_NEAR_MAX"
    return round(score, 2), verdict


def analyze_one(close: pd.Series) -> dict | None:
    """Run the full pipeline on a single Close series. Returns None if too short."""
    if len(close) < 60:
        return None
    series = close.iloc[-LOOKBACK:].astype(float).values
    n = len(series)
    smooth = _smooth(series)
    d1 = np.gradient(smooth)
    d2 = np.gradient(d1)

    d1_now = float(d1[-1])
    d2_now = float(d2[-1])
    regime = _classify_regime(d1_now, d2_now)

    lows, highs = _detect_extrema(smooth)
    t_now = n - 1
    d_min, d_max = _derivative_extrapolation(d1_now, d2_now)
    fib_min, fib_max, fib_pivots = _fibonacci_projection(lows, highs, t_now)
    damped = _fit_damped(smooth)

    days_to_min, days_to_max, methods = _ensemble(
        d_min, d_max, fib_min, fib_max, damped
    )
    score, verdict = _score(regime, days_to_min, days_to_max, methods)

    last_low_idx = int(lows[-1]) if len(lows) else None
    last_high_idx = int(highs[-1]) if len(highs) else None

    return {
        "close": round(float(series[-1]), 2),
        "smoothed_close": round(float(smooth[-1]), 2),
        "d1": round(d1_now, 4),
        "d2": round(d2_now, 4),
        "regime": regime,
        "historical_lows": int(len(lows)),
        "historical_highs": int(len(highs)),
        "days_since_last_low": (t_now - last_low_idx) if last_low_idx is not None else None,
        "days_since_last_high": (t_now - last_high_idx) if last_high_idx is not None else None,
        "fib_pivots_ahead": fib_pivots,
        "damped": damped,
        "days_to_local_min": days_to_min,
        "days_to_local_max": days_to_max,
        "methods_agreeing": methods,
        "score": score,
        "verdict": verdict,
    }


# ── orchestration ────────────────────────────────────────────────────────────

def _load_latest_universe():
    """Replay main.py's universe + liquidity filter using today's cache."""
    from fetch_universe import get_top_stocks, apply_liquidity_filter
    from fetch_prices import fetch_prices
    stocks = get_top_stocks()
    prices = fetch_prices(stocks)
    stocks, prices = apply_liquidity_filter(stocks, prices)
    return stocks, prices


def run(export: bool = False) -> list[dict]:
    print("=" * 60)
    print("  Volatility Analyst — 200d derivative / Fib / damped oscillator")
    print("=" * 60)
    stocks, prices = _load_latest_universe()
    ticker_map = {s["yf_ticker"]: s for s in stocks}

    results: list[dict] = []
    skipped = 0
    for ticker, df in prices.items():
        try:
            r = analyze_one(df["Close"])
            if r is None:
                skipped += 1
                continue
            info = ticker_map.get(ticker, {})
            results.append({
                "code": info.get("code", ticker.split(".")[0]),
                "name": info.get("name", ""),
                "market": info.get("market", ""),
                **r,
            })
        except Exception as exc:
            skipped += 1
            continue

    results.sort(key=lambda r: (-r["score"], r["days_to_local_min"] or 99))

    buy = sum(1 for r in results if r["verdict"] == "BUY_NEAR_MIN")
    watch = sum(1 for r in results if r["verdict"] == "WATCH")
    neutral = sum(1 for r in results if r["verdict"] == "NEUTRAL")
    exit_ = sum(1 for r in results if r["verdict"] == "EXIT_NEAR_MAX")
    print(f"  Analysed: {len(results)}   skipped: {skipped}")
    print(f"  BUY_NEAR_MIN: {buy}   WATCH: {watch}   NEUTRAL: {neutral}   EXIT_NEAR_MAX: {exit_}")

    if export:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out = DATA_DIR / "signals_volatility.json"
        payload = {
            "date": date.today().isoformat(),
            "method": "savgol+gradient+fib+damped_oscillator",
            "lookback_days": LOOKBACK,
            "horizon_days": FORWARD_HORIZON,
            "fib_zones": list(FIB),
            "total_analysed": len(results),
            "results": results,
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                  default=str), encoding="utf-8")
        print(f"  JSON exported: {out}")

    return results


def main() -> None:
    ap = argparse.ArgumentParser(description="Volatility analyst")
    ap.add_argument("--export", action="store_true",
                    help="Write data/signals_volatility.json")
    args = ap.parse_args()
    run(export=args.export)


if __name__ == "__main__":
    main()
