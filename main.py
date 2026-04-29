"""CTA Dashboard — entry point.

Usage:
    python main.py                          # default: reversal strategy
    python main.py --export                 # also export JSON for multi-agent handoff
    python main.py --strategy momentum      # momentum breakout strategy
    python main.py --strategy breakout      # N-day high breakout strategy
    python main.py --strategy all --export  # run all 3 strategies, export each
"""
import sys
import io
import json
import argparse
from datetime import date

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import config
from config import CACHE_DIR, OUTPUT_DIR, DATA_DIR


STRATEGY_NAMES = {
    "reversal":   "U 型反轉 (RSI/MACD)",
    "momentum":   "動能突破 (MA Breakout)",
    "breakout":   "創新高突破 (60d High)",
}


def _check_deps() -> None:
    missing = []
    for mod in ("yfinance", "pandas", "requests", "numpy"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        print(f"Missing packages: {', '.join(missing)}")
        sys.exit(1)


def _validate_price_freshness(prices: dict, today_str: str, max_stale_pct: float = 10.0) -> None:
    """Verify per-ticker last-bar date is recent enough.

    A ticker is "stale" if its last bar is older than today (or, on weekends,
    older than the previous Friday). Aborts the run if more than ``max_stale_pct``
    percent of tickers are stale — almost always means yfinance batch failed
    or the system clock is wrong.
    """
    from datetime import date as _date, timedelta
    import pandas as _pd

    today = _date.fromisoformat(today_str)
    # Roll back to last weekday for weekend/holiday tolerance
    expected = today
    while expected.weekday() >= 5:  # Sat=5, Sun=6
        expected -= timedelta(days=1)

    stale: list[tuple[str, str]] = []
    fresh = 0
    for ticker, df in prices.items():
        if df is None or len(df) == 0:
            stale.append((ticker, "empty"))
            continue
        last_idx = df.index[-1]
        if isinstance(last_idx, _pd.Timestamp):
            last_date = last_idx.date()
        else:
            last_date = _date.fromisoformat(str(last_idx)[:10])
        if last_date < expected:
            stale.append((ticker, str(last_date)))
        else:
            fresh += 1

    total = len(prices)
    stale_pct = (len(stale) / total * 100) if total else 0
    print(f"  Freshness check: {fresh}/{total} fresh @ ≥ {expected}, "
          f"{len(stale)} stale ({stale_pct:.1f}%)")

    if stale_pct > max_stale_pct:
        print(f"  [ERROR] {stale_pct:.1f}% stale exceeds {max_stale_pct}% threshold")
        print("  Sample stale tickers (first 10):")
        for t, d in stale[:10]:
            print(f"    {t}: last_date={d}")
        print("  Aborting — re-run after the cache refreshes (delete prices_*.pkl if needed).")
        sys.exit(2)
    elif stale:
        print(f"  [WARN] {len(stale)} tickers stale but under {max_stale_pct}% threshold; continuing")


def _detect_signals(strategy: str, df, info: dict, ticker: str) -> dict | None:
    """Route to the correct signal detector."""
    if strategy == "reversal":
        from indicators import calc_rsi, calc_macd
        df = df.copy()
        df["rsi"] = calc_rsi(df["Close"], config.RSI_PERIOD)
        macd, sig, hist = calc_macd(
            df["Close"], config.MACD_FAST, config.MACD_SLOW, config.MACD_SIGNAL)
        df["macd"] = macd
        df["macd_signal"] = sig
        df["macd_hist"] = hist
        from signals import detect_reversal
        return detect_reversal(df)

    elif strategy == "momentum":
        from signals_momentum import detect_momentum
        return detect_momentum(df)

    elif strategy == "breakout":
        from signals_breakout import detect_breakout
        return detect_breakout(df)

    return None


def run_strategy(strategy: str, stocks: list, prices: dict, today: str,
                 export: bool = False) -> list[dict]:
    """Run one strategy across all stocks. Returns results list."""
    ticker_map = {s["yf_ticker"]: s for s in stocks}
    results: list[dict] = []

    for ticker, df in prices.items():
        info = ticker_map.get(ticker, {})
        try:
            signal = _detect_signals(strategy, df, info, ticker)
            if signal is None:
                continue

            close = df["Close"]
            prev_close = close.iloc[-2] if len(close) >= 2 else close.iloc[-1]
            pct = (close.iloc[-1] / prev_close - 1) * 100

            results.append({
                "code": info.get("code", ticker.split(".")[0]),
                "name": info.get("name", ""),
                "market": info.get("market", ""),
                "close": round(float(close.iloc[-1]), 2),
                "pct_change": round(float(pct), 2),
                "recent_prices": [round(float(p), 2) for p in close.iloc[-20:].tolist()],
                **signal,
            })
        except Exception:
            continue

    results.sort(key=lambda r: (-r["stars"], -r["score"]))

    strong = sum(1 for r in results if r["level"] == "strong")
    medium = sum(1 for r in results if r["level"] == "medium")
    watch  = sum(1 for r in results if r["level"] == "watch")
    name = STRATEGY_NAMES.get(strategy, strategy)
    print(f"  [{name}] Signals: {len(results)}  "
          f"(Strong {strong} / Call {medium} / Watch {watch})")

    if export:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        suffix = f"_{strategy}" if strategy != "reversal" else "_latest"
        json_out = DATA_DIR / f"signals{suffix}.json"
        # Also always write signals_latest.json for backward compat
        payload = {
            "date": today,
            "strategy": strategy,
            "strategy_name": name,
            "total_scanned": len(prices),
            "results": results,
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        json_out.write_text(content, encoding="utf-8")
        if strategy == "reversal":
            (DATA_DIR / "signals_latest.json").write_text(content, encoding="utf-8")
        print(f"  JSON exported: {json_out}")

    return results


def main() -> None:
    _check_deps()

    parser = argparse.ArgumentParser(description="CTA Dashboard")
    parser.add_argument("--strategy", type=str, default="all",
                        choices=["reversal", "momentum", "breakout", "all"],
                        help="Signal detection strategy (default: all — runs all 3)")
    parser.add_argument("--export", action="store_true", help="Export JSON")
    args = parser.parse_args()

    from fetch_universe import get_top_stocks, apply_liquidity_filter
    from fetch_prices import fetch_prices

    today = date.today().isoformat()
    strategies = list(STRATEGY_NAMES.keys()) if args.strategy == "all" else [args.strategy]

    print("=" * 60)
    print("  CTA Dashboard — Multi-Strategy Scanner")
    print(f"  台股 capital≥30億 OR mktcap≥150億 composite universe  ·  {today}")
    print(f"  Strategies: {', '.join(strategies)}")
    print("=" * 60)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1/5] Fetching stock universe (Stage 1: capital/mktcap) ...")
    stocks = get_top_stocks()

    print("\n[2/5] Downloading historical prices ...")
    prices = fetch_prices(stocks)

    print("\n[2.5/5] Validating price freshness ...")
    _validate_price_freshness(prices, today)

    print("\n[3/5] Stage 2 liquidity filter (20d + 6m daily value) ...")
    stocks, prices = apply_liquidity_filter(stocks, prices)

    print("\n[4/5] Calculating indicators & signals ...")
    all_results = {}
    for strat in strategies:
        results = run_strategy(strat, stocks, prices, today, export=args.export)
        all_results[strat] = results

    # HTML report (reversal is the primary)
    print("\n[5/5] Generating HTML report ...")
    primary = all_results.get("reversal", list(all_results.values())[0])
    from report import generate_report
    out = generate_report(primary, len(prices), today)
    print(f"\n  >>> {out}")
    print("  Open the file in a browser to view the dashboard.")

    from update_index import main as refresh_index
    refresh_index()


if __name__ == "__main__":
    main()
