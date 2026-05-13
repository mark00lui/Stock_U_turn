"""One-shot backfill orchestrator — generate a clean CTA dataset for a past
trading day. Mirrors main.py + signals_volatility.py but slices yfinance data
to the target date and labels every artifact with TARGET (not date.today()).

Usage:
    python backfill_cta_daily.py YYYY-MM-DD

Produces (using the target date for cache + JSON dates):
    data/cache/prices_TARGET.pkl
    data/signals_latest.json      (reversal, with "date": TARGET)
    data/signals_momentum.json
    data/signals_breakout.json
    data/signals_volatility.json  (with "date": TARGET)

After this, run normally:
    python backtest.py --signal-type reversal --label reversal ...
    python backtest.py --signal-type momentum --label momentum ...
    python backtest.py --signal-type breakout --label breakout ...
    python generate_daily_md.py TARGET
    python publish.py
"""
from __future__ import annotations

import os
import sys
import io
import json
import pickle
import time
import warnings
from datetime import date

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# yfinance is noisy; suppress benign warnings to keep the backfill log readable.
os.environ.setdefault("CTA_MAX_STALE_PCT", "100")
warnings.filterwarnings("ignore")

import pandas as pd

from config import (
    CACHE_DIR, DATA_DIR, HISTORY_PERIOD, YF_BATCH_SIZE,
    MIN_DATA_POINTS, REQUEST_DELAY,
)
from fetch_universe import get_top_stocks, apply_liquidity_filter


def _validate_date(s: str) -> str:
    date.fromisoformat(s)         # raises if malformed
    return s


def _download_sliced(stocks: list[dict], target_ts: pd.Timestamp
                     ) -> dict[str, pd.DataFrame]:
    """Replay fetch_prices logic but slice every ticker DataFrame to bars
    with index date <= target_ts. Skips tickers that have < MIN_DATA_POINTS
    bars on or before target_ts.
    """
    import yfinance as yf

    tickers = [s["yf_ticker"] for s in stocks]
    total = len(tickers)
    total_batches = (total + YF_BATCH_SIZE - 1) // YF_BATCH_SIZE
    all_data: dict[str, pd.DataFrame] = {}

    for i in range(0, total, YF_BATCH_SIZE):
        batch = tickers[i:i + YF_BATCH_SIZE]
        bn = i // YF_BATCH_SIZE + 1
        print(f"  Batch {bn}/{total_batches} ({len(batch)} tickers) ...")
        try:
            data = yf.download(batch, period=HISTORY_PERIOD, auto_adjust=True,
                               threads=True, progress=False)
            if data.empty:
                continue
            if isinstance(data.columns, pd.MultiIndex):
                for tkr in batch:
                    try:
                        df = data.xs(tkr, level="Ticker", axis=1)
                    except KeyError:
                        continue
                    df = df.dropna(how="all")
                    df = df[df.index <= target_ts]
                    if len(df) >= MIN_DATA_POINTS:
                        all_data[tkr] = df
            else:
                df = data.dropna(how="all")
                df = df[df.index <= target_ts]
                if len(df) >= MIN_DATA_POINTS:
                    all_data[batch[0]] = df
        except Exception as exc:
            print(f"    [WARN] batch {bn} error: {exc}")
        if i + YF_BATCH_SIZE < total:
            time.sleep(REQUEST_DELAY)

    print(f"  Downloaded data for {len(all_data)}/{total} stocks (post-slice)")
    return all_data


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python backfill_cta_daily.py YYYY-MM-DD", file=sys.stderr)
        sys.exit(2)
    target = _validate_date(sys.argv[1])
    target_ts = pd.Timestamp(target)

    print("=" * 60)
    print(f"  CTA Backfill — {target}")
    print("=" * 60)

    # ── Step 1: universe ───────────────────────────────────────────────────
    print("\n[1/5] Fetching universe (Stage 1: market-cap gate) ...")
    stocks = get_top_stocks()

    # ── Step 2: yfinance with slice to target ──────────────────────────────
    print(f"\n[2/5] yfinance download — slicing each ticker to bars <= {target} ...")
    prices = _download_sliced(stocks, target_ts)

    # Cache with the TARGET date so downstream scripts (signals_volatility,
    # backtest) auto-pick this file via sorted glob.
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target_cache = CACHE_DIR / f"prices_{target}.pkl"
    with open(target_cache, "wb") as f:
        pickle.dump(prices, f)
    print(f"  Cached: {target_cache.name}")

    # ── Step 3: liquidity filter ───────────────────────────────────────────
    print("\n[3/5] Stage 2 liquidity filter (20d + 6m daily value) ...")
    stocks, prices = apply_liquidity_filter(stocks, prices)

    # ── Step 4: run 3 strategies (reversal, momentum, breakout) ────────────
    print(f"\n[4/5] Running 3 strategies for {target} ...")
    from main import run_strategy, STRATEGY_NAMES
    for strat in STRATEGY_NAMES.keys():
        run_strategy(strat, stocks, prices, target, export=True)

    # ── Step 5: volatility scan ────────────────────────────────────────────
    print(f"\n[5/5] Volatility scan (200d ∇/∇² + Fib + damped oscillator) ...")
    from signals_volatility import analyze_one, LOOKBACK, FORWARD_HORIZON, FIB
    ticker_map = {s["yf_ticker"]: s for s in stocks}
    vol_results: list[dict] = []
    skipped = 0
    for tkr, df in prices.items():
        try:
            r = analyze_one(df["Close"])
            if r is None:
                skipped += 1
                continue
            info = ticker_map.get(tkr, {})
            vol_results.append({
                "code": info.get("code", tkr.split(".")[0]),
                "name": info.get("name", ""),
                "market": info.get("market", ""),
                **r,
            })
        except Exception:
            skipped += 1
    vol_results.sort(key=lambda r: (-r["score"], r["days_to_local_min"] or 99))
    buys = sum(1 for r in vol_results if r["verdict"] == "BUY_NEAR_MIN")
    exits = sum(1 for r in vol_results if r["verdict"] == "EXIT_NEAR_MAX")
    print(f"  Analysed {len(vol_results)} · BUY_NEAR_MIN {buys} · EXIT_NEAR_MAX {exits} · skipped {skipped}")

    out = DATA_DIR / "signals_volatility.json"
    out.write_text(json.dumps({
        "date": target,
        "method": "savgol+gradient+fib+damped_oscillator",
        "lookback_days": LOOKBACK,
        "horizon_days": FORWARD_HORIZON,
        "fib_zones": list(FIB),
        "total_analysed": len(vol_results),
        "results": vol_results,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"  JSON: {out}")

    print("\n" + "=" * 60)
    print(f"  Backfill complete for {target}")
    print(f"  Next: backtest.py × 3 → generate_daily_md.py {target} → publish.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
