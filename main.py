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
    parser.add_argument("--strategy", type=str, default="reversal",
                        choices=["reversal", "momentum", "breakout", "all"],
                        help="Signal detection strategy")
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
