"""Backfill historical momentum + breakout signal JSONs for missed days.

Background — the daily cron silently ran only `--strategy reversal` from
2026-04-22 through 2026-04-29, so signals_momentum.json and signals_breakout.json
sat frozen at 2026-04-22 for a week. This script reconstructs each missed
trading day's signals from the cached price history (yfinance pkl carries
5y of bars, so slicing to any past date is lossless).

Output:
  data/agent_outputs/backfill/signals_momentum_YYYY-MM-DD.json
  data/agent_outputs/backfill/signals_breakout_YYYY-MM-DD.json
  data/agent_outputs/backfill/backfill_summary.md
  data/agent_outputs/backfill/ticker_timeline_3324.md (雙鴻 sanity check)

Usage:
  python backfill_signals.py
"""
from __future__ import annotations

import sys
import io
import json
import pickle
from pathlib import Path

import pandas as pd

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config import CACHE_DIR, DATA_DIR, MIN_DAILY_VALUE_20D, MIN_DAILY_VALUE_6M
from fetch_universe import apply_liquidity_filter
from signals_momentum import detect_momentum
from signals_breakout import detect_breakout


BACKFILL_DATES = [
    "2026-04-22",
    "2026-04-23",   # only included if a cache covers it
    "2026-04-24",
    "2026-04-27",
    "2026-04-28",
    "2026-04-29",
]
TARGET_TICKER = "3324"  # 雙鴻 — sanity-check timeline


def load_latest_cache() -> dict:
    """Load the most recent prices_*.pkl — has 5y of history covering all backfill dates."""
    pkls = sorted(CACHE_DIR.glob("prices_*.pkl"))
    if not pkls:
        raise FileNotFoundError("no prices cache found")
    print(f"  Using cache: {pkls[-1].name}")
    with open(pkls[-1], "rb") as f:
        return pickle.load(f)


def load_universe() -> list[dict]:
    with open(CACHE_DIR / "stock_universe.json", "r", encoding="utf-8") as f:
        return json.load(f)


def slice_prices_to_date(prices: dict, target_date: pd.Timestamp) -> dict:
    """Return a new dict with each df truncated to last bar ≤ target_date.

    Drops tickers whose last available bar is more than 5 calendar days
    before target_date — those rows would represent a delisting or gap.
    """
    sliced: dict = {}
    for ticker, df in prices.items():
        if df is None or len(df) == 0:
            continue
        df_cut = df.loc[df.index <= target_date]
        if len(df_cut) == 0:
            continue
        gap = (target_date - df_cut.index[-1]).days
        if gap > 5:
            continue
        sliced[ticker] = df_cut
    return sliced


def build_results(strategy_fn, stocks: list[dict], prices_sliced: dict) -> list[dict]:
    """Run a signal detector across all stocks, return reformatted result list."""
    rows: list[dict] = []
    ticker_map = {s["yf_ticker"]: s for s in stocks}
    for ticker, df in prices_sliced.items():
        info = ticker_map.get(ticker)
        if info is None:
            continue
        try:
            sig = strategy_fn(df)
        except Exception:
            continue
        if sig is None:
            continue
        close = df["Close"]
        prev = close.iloc[-2] if len(close) >= 2 else close.iloc[-1]
        pct = (close.iloc[-1] / prev - 1) * 100
        rows.append({
            "code": info["code"],
            "name": info["name"],
            "market": info["market"],
            "close": round(float(close.iloc[-1]), 2),
            "pct_change": round(float(pct), 2),
            "recent_prices": [round(float(p), 2) for p in close.iloc[-20:].tolist()],
            **sig,
        })
    rows.sort(key=lambda r: (-r["stars"], -r["score"]))
    return rows


def trace_ticker(prices_sliced: dict, ticker_code: str) -> dict | None:
    """Run momentum & breakout for a single ticker and return summary."""
    target_keys = [f"{ticker_code}.TW", f"{ticker_code}.TWO"]
    for key in target_keys:
        df = prices_sliced.get(key)
        if df is None or len(df) == 0:
            continue
        last_close = float(df["Close"].iloc[-1])
        last_volume = float(df["Volume"].iloc[-1])
        m = detect_momentum(df)
        b = detect_breakout(df)
        return {
            "ticker": key,
            "last_bar": str(df.index[-1].date()),
            "close": last_close,
            "volume": last_volume,
            "momentum_stars": m["stars"] if m else None,
            "momentum_score": m["score"] if m else None,
            "breakout_stars": b["stars"] if b else None,
            "breakout_score": b["score"] if b else None,
        }
    return None


def main() -> None:
    print("=" * 60)
    print("  Backfill momentum + breakout signal JSONs")
    print("=" * 60)

    out_dir = DATA_DIR / "agent_outputs" / "backfill"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("\n[1/3] Loading latest cache + universe ...")
    prices_full = load_latest_cache()
    stocks_static = load_universe()  # capital/mktcap composite, already Stage 1 filtered
    print(f"  Cache: {len(prices_full)} tickers")
    print(f"  Universe (Stage 1): {len(stocks_static)} stocks")

    summary_rows: list[dict] = []
    timeline: list[dict] = []

    for date_str in BACKFILL_DATES:
        print(f"\n[2/3] Backfilling {date_str} ...")
        target = pd.Timestamp(date_str)
        prices_sliced = slice_prices_to_date(prices_full, target)
        if not prices_sliced:
            print(f"  No data ≤ {date_str}, skipping")
            continue

        # Apply Stage 2 liquidity filter using the sliced view
        stocks_alive, prices_filt = apply_liquidity_filter(stocks_static, prices_sliced)
        if not stocks_alive:
            print(f"  Liquidity filter cut everything, skipping")
            continue

        m_results = build_results(detect_momentum, stocks_alive, prices_filt)
        b_results = build_results(detect_breakout, stocks_alive, prices_filt)

        m_strong = sum(1 for r in m_results if r["stars"] == 5)
        b_strong = sum(1 for r in b_results if r["stars"] == 5)

        m_payload = {
            "date": date_str, "strategy": "momentum",
            "strategy_name": "動能突破 (MA Breakout) — backfilled",
            "total_scanned": len(prices_filt),
            "results": m_results,
        }
        b_payload = {
            "date": date_str, "strategy": "breakout",
            "strategy_name": "創新高突破 (60d High) — backfilled",
            "total_scanned": len(prices_filt),
            "results": b_results,
        }
        (out_dir / f"signals_momentum_{date_str}.json").write_text(
            json.dumps(m_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / f"signals_breakout_{date_str}.json").write_text(
            json.dumps(b_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"  Scanned: {len(prices_filt)} (post-Stage 2)")
        print(f"  Momentum signals: {len(m_results)} (Strong={m_strong})")
        print(f"  Breakout signals: {len(b_results)} (Strong={b_strong})")

        summary_rows.append({
            "date": date_str,
            "scanned": len(prices_filt),
            "m_total": len(m_results), "m_strong": m_strong,
            "b_total": len(b_results), "b_strong": b_strong,
        })

        # Timeline trace for target ticker
        t = trace_ticker(prices_filt, TARGET_TICKER)
        if t is None:
            t = trace_ticker(prices_sliced, TARGET_TICKER)
            if t:
                t["liquidity_filter"] = "cut"
        else:
            t["liquidity_filter"] = "kept"
        if t:
            t["date"] = date_str
            timeline.append(t)

    # Summary report
    print("\n[3/3] Writing summary ...")
    md = ["# Backfill Summary — momentum + breakout signal JSONs",
          "",
          "Reconstructed from cached yfinance history. Each date's JSON lives in",
          "`data/agent_outputs/backfill/signals_{strategy}_{date}.json`.",
          "",
          "| Date | Scanned | Momentum Total / Strong | Breakout Total / Strong |",
          "|------|--------:|------------------------:|------------------------:|"]
    for r in summary_rows:
        md.append(
            f"| {r['date']} | {r['scanned']} | {r['m_total']} / **{r['m_strong']}** "
            f"| {r['b_total']} / **{r['b_strong']}** |"
        )
    md.append("")
    md.append("> Bold = 5★ Strong signals — these were the picks the daily report")
    md.append("> would have surfaced if the cron had used `--strategy all` from day one.")
    (out_dir / "backfill_summary.md").write_text("\n".join(md), encoding="utf-8")

    # Ticker timeline
    if timeline:
        tl = [f"# Ticker timeline — {TARGET_TICKER} 雙鴻",
              "",
              "Sanity-check trace: per-day status across the backfilled window.",
              "",
              "| Date | Last Bar | Close | Volume | Liquidity | Momentum ★ | Score | Breakout ★ | Score |",
              "|------|----------|------:|-------:|-----------|-----------:|------:|-----------:|------:|"]
        for t in timeline:
            tl.append(
                f"| {t['date']} | {t['last_bar']} | {t['close']:.2f} | {t['volume']:.0f} "
                f"| {t.get('liquidity_filter', '?')} "
                f"| {t['momentum_stars'] or '—'} | {t['momentum_score'] or '—'} "
                f"| {t['breakout_stars'] or '—'} | {t['breakout_score'] or '—'} |"
            )
        (out_dir / f"ticker_timeline_{TARGET_TICKER}.md").write_text(
            "\n".join(tl), encoding="utf-8")
        print(f"  Wrote ticker timeline: {len(timeline)} rows")

    print(f"\nDone. Files in: {out_dir}")


if __name__ == "__main__":
    main()
