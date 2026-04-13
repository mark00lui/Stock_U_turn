"""CTA Dashboard — entry point.

Usage:
    python main.py              # technical report only
    python main.py --export     # also export JSON for multi-agent handoff
"""
import sys
import io
import json
from datetime import date

# Fix Windows console encoding for CJK output
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import config
from config import CACHE_DIR, OUTPUT_DIR


def _check_deps() -> None:
    missing = []
    for mod in ("yfinance", "pandas", "requests", "numpy"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        print(f"Missing packages: {', '.join(missing)}")
        print(f"  pip install -r requirements.txt")
        sys.exit(1)


def main() -> None:
    _check_deps()

    from fetch_universe import get_top_stocks
    from fetch_prices import fetch_prices
    from indicators import calc_rsi, calc_macd
    from signals import detect_reversal
    from report import generate_report

    today = date.today().isoformat()
    print("=" * 60)
    print("  CTA Dashboard — RSI / MACD 抄底反轉")
    print(f"  台股前 {config.TOP_N} 大  ·  {today}")
    print("=" * 60)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Stock universe
    print("\n[1/4] Fetching stock universe ...")
    stocks = get_top_stocks()

    # 2. Historical prices
    print("\n[2/4] Downloading historical prices ...")
    prices = fetch_prices(stocks)

    # 3. Indicators & signals
    print("\n[3/4] Calculating indicators ...")
    ticker_map = {s["yf_ticker"]: s for s in stocks}
    results: list[dict] = []

    for ticker, df in prices.items():
        info = ticker_map.get(ticker, {})
        try:
            df = df.copy()
            close = df["Close"]

            df["rsi"] = calc_rsi(close, config.RSI_PERIOD)
            macd, sig, hist = calc_macd(
                close, config.MACD_FAST, config.MACD_SLOW, config.MACD_SIGNAL
            )
            df["macd"] = macd
            df["macd_signal"] = sig
            df["macd_hist"] = hist

            signal = detect_reversal(df)
            if signal is None:
                continue

            prev_close = close.iloc[-2] if len(close) >= 2 else close.iloc[-1]
            pct = (close.iloc[-1] / prev_close - 1) * 100

            results.append(
                {
                    "code": info.get("code", ticker.split(".")[0]),
                    "name": info.get("name", ""),
                    "market": info.get("market", ""),
                    "close": round(float(close.iloc[-1]), 2),
                    "pct_change": round(float(pct), 2),
                    "recent_prices": [round(float(p), 2) for p in close.iloc[-20:].tolist()],
                    **signal,
                }
            )
        except Exception:
            continue

    results.sort(key=lambda r: (-r["stars"], -r["score"]))

    strong = sum(1 for r in results if r["level"] == "strong")
    medium = sum(1 for r in results if r["level"] == "medium")
    watch  = sum(1 for r in results if r["level"] == "watch")
    print(f"  Signals found: {len(results)}  "
          f"(Strong {strong} / Call {medium} / Watch {watch})")

    # 4. Export JSON for multi-agent handoff
    export_json = "--export" in sys.argv
    if export_json:
        from config import DATA_DIR
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        json_out = DATA_DIR / "signals_latest.json"
        payload = {
            "date": today,
            "total_scanned": len(prices),
            "results": results,
        }
        json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\n  JSON exported: {json_out}")

    # 5. HTML report
    print("\n[4/4] Generating HTML report ...")
    out = generate_report(results, len(prices), today)
    print(f"\n  >>> {out}")
    print("  Open the file in a browser to view the dashboard.")


if __name__ == "__main__":
    main()
