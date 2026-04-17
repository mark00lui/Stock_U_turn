"""Backtesting engine for CTA RSI/MACD reversal signals.

Applies the same signal rules from signals.py to historical data,
simulates trades with stop-loss / target / time-limit, and generates
a self-contained HTML report.

Usage:
    python backtest.py                  # default parameters
    python backtest.py --min-stars 4    # only strong signals
"""
from __future__ import annotations

import json
import math
import sys
import io
import pickle
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

import config
from config import CACHE_DIR, OUTPUT_DIR, DATA_DIR
from indicators import calc_rsi, calc_macd


# ── Strategy parameters ────────────────────────────────

@dataclass
class Strategy:
    """Trading strategy rules for backtesting."""
    name: str = "CTA 抄底反轉"
    stop_loss_pct: float = -7.0       # stop-loss trigger %
    target_pct: float = 10.0          # take-profit target %
    max_hold_days: int = 20           # time-based exit (trading days)
    min_stars: int = 3                # minimum signal strength to enter
    cooldown_days: int = 5            # min days between entries on same stock
    position_pct: float = 5.0         # % of portfolio per trade
    early_exit_days: int = 0          # if >0: exit early when gain < early_exit_min after N days
    early_exit_min_pct: float = 3.0   # minimum gain% required to stay after early_exit_days


# ── Trade record ───────────────────────────────────────

@dataclass
class Trade:
    code: str
    name: str
    market: str
    entry_date: str
    entry_price: float
    signal_stars: int
    signal_descs: list[str]
    exit_date: str | None = None
    exit_price: float | None = None
    exit_reason: str | None = None     # 停損 / 達標 / 到期 / 持倉中
    pnl_pct: float | None = None
    holding_days: int | None = None


# ── Signal check (inline, fast) ────────────────────────

def _signal_score(rsi_arr, hist_arr, macd_arr, i: int, lb: int) -> float:
    """Return signal score at index *i* (0 = no signal)."""
    if i < lb + 2:
        return 0
    rsi_now = rsi_arr[i]
    if np.isnan(rsi_now):
        return 0

    score = 0.0

    # RSI
    recent_rsi = rsi_arr[i - lb : i]
    was_oversold = np.nanmin(recent_rsi) < config.RSI_OVERSOLD
    if was_oversold and rsi_now >= config.RSI_OVERSOLD:
        score += 2
    elif rsi_now < config.RSI_OVERSOLD:
        score += 1
    elif rsi_now < config.RSI_RECOVERY:
        score += 0.5

    # MACD histogram
    golden = False
    for j in range(max(1, i - lb), i + 1):
        if hist_arr[j - 1] < 0 and hist_arr[j] >= 0:
            score += 2
            golden = True
            break
    if not golden and hist_arr[i] < 0 and i > 0:
        if not np.isnan(hist_arr[i - 1]) and hist_arr[i] > hist_arr[i - 1]:
            score += 1

    # bottom territory bonus
    if macd_arr[i] < 0 and score >= 2:
        score += 0.5

    return score


def _score_to_stars(score: float) -> int:
    if score >= 4:
        return 5
    if score >= 3:
        return 4
    if score >= 2:
        return 3
    if score >= 1.5:
        return 2
    return 1


def _score_to_descs(rsi_arr, hist_arr, macd_arr, i: int, lb: int) -> list[str]:
    """Reconstruct signal descriptions (for the trade log)."""
    descs = []
    rsi_now = rsi_arr[i]
    recent_rsi = rsi_arr[i - lb : i]
    was_oversold = np.nanmin(recent_rsi) < config.RSI_OVERSOLD
    if was_oversold and rsi_now >= config.RSI_OVERSOLD:
        descs.append("RSI 超賣反彈")
    elif rsi_now < config.RSI_OVERSOLD:
        descs.append("RSI 超賣區")

    for j in range(max(1, i - lb), i + 1):
        if hist_arr[j - 1] < 0 and hist_arr[j] >= 0:
            descs.append("MACD 金叉")
            break
    else:
        if hist_arr[i] < 0 and i > 0 and hist_arr[i] > hist_arr[i - 1]:
            descs.append("MACD 柱收斂")

    if macd_arr[i] < 0:
        descs.append("底部區域")
    return descs


# ── Backtest engine ────────────────────────────────────

class BacktestEngine:
    def __init__(self, strategy: Strategy | None = None):
        self.strat = strategy or Strategy()
        self.trades: list[Trade] = []

    def run(self, stocks: list[dict], prices: dict) -> list[Trade]:
        ticker_map = {s["yf_ticker"]: s for s in stocks}
        total = len(prices)
        done = 0

        for ticker, df in prices.items():
            info = ticker_map.get(ticker, {})
            self._backtest_stock(df, info)
            done += 1
            if done % 200 == 0:
                print(f"    {done}/{total} stocks ...")

        self.trades.sort(key=lambda t: t.entry_date)
        return self.trades

    def _backtest_stock(self, df: pd.DataFrame, info: dict) -> None:
        df = df.copy()
        close = df["Close"].values
        n = len(close)

        warmup = config.MACD_SLOW + 10
        if n < warmup + self.strat.max_hold_days:
            return

        # pre-compute indicators (vectorised)
        rsi_s = calc_rsi(df["Close"], config.RSI_PERIOD)
        macd_s, _, hist_s = calc_macd(
            df["Close"], config.MACD_FAST, config.MACD_SLOW, config.MACD_SIGNAL
        )
        rsi = rsi_s.values
        hist = hist_s.values
        macd = macd_s.values

        dates = df.index
        lb = config.LOOKBACK_DAYS
        code = info.get("code", "")
        name = info.get("name", "")
        market = info.get("market", "")

        last_exit_i = -self.strat.cooldown_days  # allow first trade

        for i in range(warmup, n):
            # skip if in cooldown
            if i - last_exit_i < self.strat.cooldown_days:
                continue

            score = _signal_score(rsi, hist, macd, i, lb)
            stars = _score_to_stars(score)
            if stars < self.strat.min_stars:
                continue

            # ── enter trade at close[i] ────────────────
            entry_price = close[i]
            if entry_price <= 0 or np.isnan(entry_price):
                continue

            descs = _score_to_descs(rsi, hist, macd, i, lb)
            exit_price = None
            exit_reason = None
            exit_j = None

            # scan forward for exit
            for j in range(i + 1, min(i + 1 + self.strat.max_hold_days, n)):
                price = close[j]
                if np.isnan(price) or price <= 0:
                    continue
                pct = (price / entry_price - 1) * 100
                days_held = j - i

                if pct <= self.strat.stop_loss_pct:
                    exit_price = price
                    exit_reason = "停損"
                    exit_j = j
                    break
                elif pct >= self.strat.target_pct:
                    exit_price = price
                    exit_reason = "達標"
                    exit_j = j
                    break
                elif (self.strat.early_exit_days > 0
                      and days_held >= self.strat.early_exit_days
                      and pct < self.strat.early_exit_min_pct):
                    exit_price = price
                    exit_reason = "早期出場"
                    exit_j = j
                    break

            if exit_reason is None:
                # time-based exit or still holding
                end_j = min(i + self.strat.max_hold_days, n - 1)
                exit_price = close[end_j]
                exit_j = end_j
                if end_j >= n - 1:
                    exit_reason = "持倉中"
                else:
                    exit_reason = "到期"

            pnl = round((exit_price / entry_price - 1) * 100, 2)

            self.trades.append(Trade(
                code=code, name=name, market=market,
                entry_date=str(dates[i].date()),
                entry_price=round(float(entry_price), 2),
                signal_stars=stars,
                signal_descs=descs,
                exit_date=str(dates[exit_j].date()),
                exit_price=round(float(exit_price), 2),
                exit_reason=exit_reason,
                pnl_pct=pnl,
                holding_days=exit_j - i,
            ))

            last_exit_i = exit_j  # cooldown from exit


# ── Metrics ────────────────────────────────────────────

@dataclass
class Metrics:
    total_trades: int = 0
    winners: int = 0
    losers: int = 0
    win_rate: float = 0.0
    avg_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    avg_hold_days: float = 0.0
    max_consec_wins: int = 0
    max_consec_losses: int = 0
    total_return_pct: float = 0.0
    by_reason: dict = field(default_factory=dict)
    by_stars: dict = field(default_factory=dict)
    monthly: dict = field(default_factory=dict)


def compute_metrics(trades: list[Trade], position_pct: float = 5.0) -> Metrics:
    m = Metrics()
    if not trades:
        return m

    closed = [t for t in trades if t.exit_reason != "持倉中"]
    if not closed:
        m.total_trades = len(trades)
        return m

    pnls = [t.pnl_pct for t in closed]
    m.total_trades = len(closed)
    m.winners = sum(1 for p in pnls if p > 0)
    m.losers = sum(1 for p in pnls if p <= 0)
    m.win_rate = round(m.winners / m.total_trades * 100, 1) if m.total_trades else 0
    m.avg_pnl = round(np.mean(pnls), 2)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    m.avg_win = round(np.mean(wins), 2) if wins else 0
    m.avg_loss = round(np.mean(losses), 2) if losses else 0
    total_gain = sum(wins)
    total_loss = abs(sum(losses))
    m.profit_factor = round(total_gain / total_loss, 2) if total_loss > 0 else float("inf")
    m.best_trade = round(max(pnls), 2)
    m.worst_trade = round(min(pnls), 2)
    m.avg_hold_days = round(np.mean([t.holding_days for t in closed]), 1)

    # portfolio-level return: each trade uses position_pct% of capital
    m.total_return_pct = round(sum(p * position_pct / 100 for p in pnls), 2)

    # consecutive
    streak, max_w, max_l = 0, 0, 0
    for p in pnls:
        if p > 0:
            streak = streak + 1 if streak > 0 else 1
            max_w = max(max_w, streak)
        else:
            streak = streak - 1 if streak < 0 else -1
            max_l = max(max_l, abs(streak))
    m.max_consec_wins = max_w
    m.max_consec_losses = max_l

    # by exit reason
    for reason in ("停損", "達標", "到期", "早期出場"):
        subset = [t.pnl_pct for t in closed if t.exit_reason == reason]
        if subset:
            m.by_reason[reason] = {
                "count": len(subset),
                "avg_pnl": round(np.mean(subset), 2),
                "total_pnl": round(sum(subset), 2),
            }

    # by signal stars
    for stars in (3, 4, 5):
        subset = [t.pnl_pct for t in closed if t.signal_stars == stars]
        if subset:
            w = sum(1 for p in subset if p > 0)
            m.by_stars[stars] = {
                "count": len(subset),
                "win_rate": round(w / len(subset) * 100, 1),
                "avg_pnl": round(np.mean(subset), 2),
            }

    # monthly breakdown
    for t in closed:
        month = t.entry_date[:7]
        if month not in m.monthly:
            m.monthly[month] = {"trades": 0, "wins": 0, "total_pnl": 0.0}
        m.monthly[month]["trades"] += 1
        if t.pnl_pct > 0:
            m.monthly[month]["wins"] += 1
        m.monthly[month]["total_pnl"] += t.pnl_pct

    return m


# ── Equity curve ───────────────────────────────────────

def _equity_curve_svg(trades: list[Trade], position_pct: float, w: int = 800, h: int = 200) -> str:
    """SVG equity curve based on cumulative portfolio return."""
    closed = [t for t in trades if t.exit_reason != "持倉中"]
    if len(closed) < 2:
        return ""

    # cumulative portfolio return
    cum = [0.0]
    for t in closed:
        cum.append(cum[-1] + t.pnl_pct * position_pct / 100)

    lo, hi = min(cum), max(cum)
    rng = hi - lo or 1
    n = len(cum)
    pad = 4

    pts = []
    for i, v in enumerate(cum):
        x = round(pad + i / (n - 1) * (w - 2 * pad), 1)
        y = round(h - pad - (v - lo) / rng * (h - 2 * pad), 1)
        pts.append(f"{x},{y}")

    # zero line
    zero_y = round(h - pad - (0 - lo) / rng * (h - 2 * pad), 1)
    color = "#3fb950" if cum[-1] >= 0 else "#f85149"

    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<rect width="{w}" height="{h}" fill="#161b22" rx="8"/>'
        f'<line x1="{pad}" y1="{zero_y}" x2="{w-pad}" y2="{zero_y}" '
        f'stroke="#30363d" stroke-width="1" stroke-dasharray="4,4"/>'
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" '
        f'stroke-width="2" stroke-linejoin="round"/>'
        f'<circle cx="{pts[-1].split(",")[0]}" cy="{pts[-1].split(",")[1]}" '
        f'r="3" fill="{color}"/>'
        f'<text x="{w-pad}" y="{float(pts[-1].split(",")[1])-8}" '
        f'text-anchor="end" fill="{color}" font-size="12" font-weight="600">'
        f'{cum[-1]:+.1f}%</text>'
        f"</svg>"
    )


# ── Bar chart SVG ──────────────────────────────────────

def _bar_chart_svg(data: dict, w: int = 400, h: int = 160, label_key: str = "") -> str:
    """Simple horizontal bar chart."""
    if not data:
        return ""
    items = list(data.items())
    n = len(items)
    bar_h = min(28, (h - 20) // n)
    max_val = max(abs(v) for _, v in items) or 1

    bars = []
    for i, (label, val) in enumerate(items):
        y = 10 + i * (bar_h + 4)
        bar_w = abs(val) / max_val * (w * 0.5)
        color = "#3fb950" if val >= 0 else "#f85149"
        x_start = w * 0.35
        bars.append(
            f'<text x="{x_start - 8}" y="{y + bar_h * 0.7}" text-anchor="end" '
            f'fill="#8b949e" font-size="12">{label}</text>'
            f'<rect x="{x_start}" y="{y}" width="{bar_w:.0f}" height="{bar_h}" '
            f'fill="{color}" rx="3" opacity="0.8"/>'
            f'<text x="{x_start + bar_w + 6}" y="{y + bar_h * 0.7}" '
            f'fill="#e6edf3" font-size="11">{val:+.1f}%</text>'
        )

    total_h = 10 + n * (bar_h + 4) + 10
    return (
        f'<svg width="{w}" height="{total_h}" viewBox="0 0 {w} {total_h}">'
        + "".join(bars)
        + "</svg>"
    )


# ── HTML report generation ─────────────────────────────

def generate_backtest_report(
    trades: list[Trade],
    metrics: Metrics,
    strategy: Strategy,
    date_str: str,
    trader_commentary: str = "",
) -> Path:
    closed = [t for t in trades if t.exit_reason != "持倉中"]
    holding = [t for t in trades if t.exit_reason == "持倉中"]

    # equity curve
    eq_svg = _equity_curve_svg(closed, strategy.position_pct)

    # monthly P&L bar chart
    monthly_data = {}
    for month, info in sorted(metrics.monthly.items()):
        monthly_data[month] = round(info["total_pnl"], 1)
    monthly_svg = _bar_chart_svg(monthly_data)

    # by-stars bar chart
    stars_data = {}
    for s in (3, 4, 5):
        if s in metrics.by_stars:
            label = "★" * s
            stars_data[label] = metrics.by_stars[s]["avg_pnl"]
    stars_svg = _bar_chart_svg(stars_data)

    # reason pie (as text, since SVG pie is complex)
    reason_rows = ""
    for reason in ("達標", "停損", "到期"):
        if reason in metrics.by_reason:
            r = metrics.by_reason[reason]
            reason_rows += (
                f'<tr><td>{reason}</td>'
                f'<td class="n">{r["count"]}</td>'
                f'<td class="n">{r["avg_pnl"]:+.2f}%</td>'
                f'<td class="n">{r["total_pnl"]:+.1f}%</td></tr>'
            )

    # trade log rows
    log_rows = ""
    for i, t in enumerate(closed, 1):
        cls = "gr" if t.pnl_pct > 0 else "rd"
        sigs = ", ".join(t.signal_descs)
        log_rows += (
            f'<tr>'
            f'<td class="c">{i}</td>'
            f'<td class="code">{t.code}</td>'
            f'<td>{t.name}</td>'
            f'<td class="c">{"★" * t.signal_stars}</td>'
            f'<td>{t.entry_date}</td>'
            f'<td class="n">{t.entry_price:.2f}</td>'
            f'<td>{t.exit_date}</td>'
            f'<td class="n">{t.exit_price:.2f}</td>'
            f'<td class="c">{t.exit_reason}</td>'
            f'<td class="n {cls}">{t.pnl_pct:+.2f}%</td>'
            f'<td class="c">{t.holding_days}d</td>'
            f'</tr>'
        )

    # commentary HTML
    from report import _md
    commentary_html = _md(trader_commentary) if trader_commentary else ""

    pf_display = f"{metrics.profit_factor:.2f}" if metrics.profit_factor != float("inf") else "∞"

    # pre-compute colour classes (avoid nested braces in template)
    wr_cls = "gr" if metrics.win_rate >= 50 else "yw"
    pnl_cls = "gr" if metrics.avg_pnl >= 0 else "rd"
    pf_cls = "gr" if metrics.profit_factor > 1 else "rd"
    ret_cls = "gr" if metrics.total_return_pct >= 0 else "rd"
    show_commentary = "block" if commentary_html else "none"

    html = _BT_TEMPLATE.format(
        date=date_str,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        strat_name=strategy.name,
        stop_loss=strategy.stop_loss_pct,
        target=strategy.target_pct,
        max_hold=strategy.max_hold_days,
        min_stars=strategy.min_stars,
        position_pct=strategy.position_pct,
        wr_cls=wr_cls, pnl_cls=pnl_cls, pf_cls=pf_cls, ret_cls=ret_cls,
        show_commentary=show_commentary,
        total_trades=metrics.total_trades,
        win_rate=metrics.win_rate,
        avg_pnl=metrics.avg_pnl,
        profit_factor=pf_display,
        total_return=metrics.total_return_pct,
        avg_win=metrics.avg_win,
        avg_loss=metrics.avg_loss,
        best=metrics.best_trade,
        worst=metrics.worst_trade,
        avg_hold=metrics.avg_hold_days,
        max_w=metrics.max_consec_wins,
        max_l=metrics.max_consec_losses,
        winners=metrics.winners,
        losers=metrics.losers,
        holding_count=len(holding),
        eq_svg=eq_svg,
        monthly_svg=monthly_svg,
        stars_svg=stars_svg,
        reason_rows=reason_rows,
        log_rows=log_rows,
        commentary=commentary_html,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"cta_backtest_{date_str}.html"
    out.write_text(html, encoding="utf-8")
    return out


# ── Main ───────────────────────────────────────────────

def main() -> tuple[list[Trade], Metrics, Strategy]:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-stars", type=int, default=3)
    parser.add_argument("--stop-loss", type=float, default=-7.0)
    parser.add_argument("--target", type=float, default=10.0)
    parser.add_argument("--max-hold", type=int, default=20)
    parser.add_argument("--position", type=float, default=5.0)
    parser.add_argument("--early-exit-days", type=int, default=0)
    parser.add_argument("--early-exit-min", type=float, default=3.0)
    parser.add_argument("--label", type=str, default="",
                        help="Label for output files (e.g. 'momentum', 'manual')")
    args = parser.parse_args()

    strat = Strategy(
        stop_loss_pct=args.stop_loss,
        target_pct=args.target,
        max_hold_days=args.max_hold,
        min_stars=args.min_stars,
        position_pct=args.position,
        early_exit_days=args.early_exit_days,
        early_exit_min_pct=args.early_exit_min,
    )
    label = args.label

    today = date.today().isoformat()
    print("=" * 60)
    print(f"  CTA Backtest — {strat.name}")
    print(f"  停損 {strat.stop_loss_pct}% / 目標 {strat.target_pct}% / "
          f"持有 {strat.max_hold_days}d / 最低 {strat.min_stars}★")
    print("=" * 60)

    # load cached data
    print("\n[1/3] Loading data ...")
    cache_file = CACHE_DIR / "stock_universe.json"
    if not cache_file.exists():
        print("  No cached data. Run  python main.py  first.")
        sys.exit(1)
    stocks = json.loads(cache_file.read_text(encoding="utf-8"))

    # find latest price cache
    price_files = sorted(CACHE_DIR.glob("prices_*.pkl"), reverse=True)
    if not price_files:
        print("  No cached prices. Run  python main.py  first.")
        sys.exit(1)
    with open(price_files[0], "rb") as f:
        prices = pickle.load(f)
    print(f"  {len(stocks)} stocks, {len(prices)} with price data")

    # run backtest
    print(f"\n[2/3] Running backtest ...")
    engine = BacktestEngine(strat)
    trades = engine.run(stocks, prices)

    metrics = compute_metrics(trades, strat.position_pct)
    closed = [t for t in trades if t.exit_reason != "持倉中"]

    print(f"  Total closed trades: {metrics.total_trades}")
    print(f"  Win rate: {metrics.win_rate}%")
    print(f"  Avg P&L: {metrics.avg_pnl:+.2f}%")
    print(f"  Profit factor: {metrics.profit_factor}")
    print(f"  Portfolio return: {metrics.total_return_pct:+.2f}%")

    # generate report (without commentary — will be added later)
    print(f"\n[3/3] Generating report ...")
    out = generate_backtest_report(trades, metrics, strat, today)
    print(f"\n  >>> {out}")

    # refresh landing index
    from update_index import main as refresh_index
    refresh_index()

    # also export JSON for agent analysis
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{label}" if label else "_latest"
    bt_json = DATA_DIR / f"backtest{suffix}.json"
    export = {
        "date": today,
        "label": label,
        "strategy": asdict(strat),
        "metrics": {
            "total_trades": metrics.total_trades,
            "win_rate": metrics.win_rate,
            "avg_pnl": metrics.avg_pnl,
            "avg_win": metrics.avg_win,
            "avg_loss": metrics.avg_loss,
            "profit_factor": metrics.profit_factor,
            "total_return_pct": metrics.total_return_pct,
            "best_trade": metrics.best_trade,
            "worst_trade": metrics.worst_trade,
            "avg_hold_days": metrics.avg_hold_days,
            "max_consec_wins": metrics.max_consec_wins,
            "max_consec_losses": metrics.max_consec_losses,
            "by_reason": metrics.by_reason,
            "by_stars": metrics.by_stars,
            "monthly": {k: round(v["total_pnl"], 2) for k, v in metrics.monthly.items()},
        },
        "trades": [asdict(t) for t in trades],
    }
    bt_json.write_text(json.dumps(export, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    return trades, metrics, strat


# ── HTML template ──────────────────────────────────────

_BT_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CTA Backtest Report — {date}</title>
<style>
:root{{--bg:#0d1117;--sf:#161b22;--sf2:#21262d;--bd:#30363d;
  --t1:#e6edf3;--t2:#8b949e;--gr:#3fb950;--rd:#f85149;--yw:#d29922;--bl:#58a6ff}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--t1);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  font-size:14px;line-height:1.6}}
.wrap{{max-width:1400px;margin:0 auto;padding:24px}}
header{{text-align:center;margin-bottom:32px;padding-bottom:24px;border-bottom:1px solid var(--bd)}}
header h1{{font-size:28px;font-weight:700;
  background:linear-gradient(135deg,#f97583,var(--bl));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.sub{{color:var(--t2);font-size:14px;margin-top:6px}}
.strat{{display:inline-block;background:var(--sf2);border:1px solid var(--bd);
  border-radius:8px;padding:8px 16px;margin-top:12px;font-size:13px;color:var(--t2)}}
.strat b{{color:var(--t1)}}

/* cards */
.cards{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:24px}}
.cd{{background:var(--sf);border:1px solid var(--bd);border-radius:12px;padding:16px;text-align:center}}
.cd-n{{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums}}
.cd-l{{color:var(--t2);font-size:12px;margin-top:2px}}
.cd .gr{{color:var(--gr)}}.cd .rd{{color:var(--rd)}}.cd .bl{{color:var(--bl)}}.cd .yw{{color:var(--yw)}}

/* sections */
.sec{{background:var(--sf);border:1px solid var(--bd);border-radius:12px;padding:20px;margin-bottom:20px}}
.sec h2{{font-size:16px;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--bd)}}
.sec h2 .tag{{font-size:11px;background:var(--sf2);color:var(--t2);
  padding:2px 8px;border-radius:8px;margin-left:8px;font-weight:400}}

/* grid layout */
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.grid3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px}}

/* tables */
table{{width:100%;border-collapse:collapse}}
th{{background:var(--sf2);color:var(--t2);font-weight:600;font-size:12px;
  text-transform:uppercase;padding:10px 12px;text-align:left;border-bottom:1px solid var(--bd)}}
td{{padding:8px 12px;border-bottom:1px solid var(--bd)}}
.c{{text-align:center}}.n{{text-align:right;font-variant-numeric:tabular-nums}}
.code{{font-weight:600;color:var(--bl)}}
.gr{{color:var(--gr)}}.rd{{color:var(--rd)}}

/* trade log */
.tw{{overflow-x:auto;border:1px solid var(--bd);border-radius:12px;max-height:600px;overflow-y:auto}}
.tw table thead{{position:sticky;top:0}}

/* commentary */
.commentary{{color:var(--t1);line-height:1.7}}
.commentary h3{{color:var(--bl);margin:14px 0 6px}}.commentary h4{{color:var(--gr);margin:12px 0 4px}}
.commentary strong{{color:var(--t1)}}.commentary li{{margin-left:20px;list-style:disc;margin-bottom:4px}}
.commentary hr{{border:none;border-top:1px solid var(--bd);margin:14px 0}}
.commentary .md-tbl{{width:100%;border-collapse:collapse;margin:10px 0}}
.commentary .md-tbl th,.commentary .md-tbl td{{border:1px solid var(--bd);padding:6px 10px;font-size:13px}}
.commentary .md-tbl th{{background:var(--sf2)}}

footer{{text-align:center;color:var(--t2);font-size:12px;margin-top:24px;
  padding-top:16px;border-top:1px solid var(--bd)}}
@media(max-width:768px){{.cards{{grid-template-columns:repeat(2,1fr)}}.grid2,.grid3{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="wrap">

<header>
  <h1>CTA Backtest Report</h1>
  <p class="sub">RSI / MACD 抄底反轉策略回測 &middot; {date}</p>
  <div class="strat">
    <b>{strat_name}</b> &nbsp;|&nbsp;
    停損 <b>{stop_loss}%</b> &nbsp;|&nbsp;
    目標 <b>+{target}%</b> &nbsp;|&nbsp;
    最長持有 <b>{max_hold}天</b> &nbsp;|&nbsp;
    最低訊號 <b>{min_stars}★</b> &nbsp;|&nbsp;
    單筆倉位 <b>{position_pct}%</b>
  </div>
</header>

<!-- Summary cards -->
<div class="cards">
  <div class="cd"><div class="cd-n bl">{total_trades}</div><div class="cd-l">Total Trades</div></div>
  <div class="cd"><div class="cd-n {wr_cls}">{win_rate}%</div><div class="cd-l">Win Rate</div></div>
  <div class="cd"><div class="cd-n {pnl_cls}">{avg_pnl:+.2f}%</div><div class="cd-l">Avg P&L per Trade</div></div>
  <div class="cd"><div class="cd-n {pf_cls}">{profit_factor}</div><div class="cd-l">Profit Factor</div></div>
  <div class="cd"><div class="cd-n {ret_cls}">{total_return:+.1f}%</div><div class="cd-l">Portfolio Return</div></div>
</div>

<!-- Equity curve -->
<div class="sec">
  <h2>Equity Curve <span class="tag">cumulative portfolio return</span></h2>
  {eq_svg}
</div>

<!-- Detailed metrics + charts -->
<div class="grid2">
  <div class="sec">
    <h2>Performance Metrics</h2>
    <table>
      <tr><td>Winning trades</td><td class="n gr">{winners}</td></tr>
      <tr><td>Losing trades</td><td class="n rd">{losers}</td></tr>
      <tr><td>Avg winner</td><td class="n gr">{avg_win:+.2f}%</td></tr>
      <tr><td>Avg loser</td><td class="n rd">{avg_loss:+.2f}%</td></tr>
      <tr><td>Best trade</td><td class="n gr">{best:+.2f}%</td></tr>
      <tr><td>Worst trade</td><td class="n rd">{worst:+.2f}%</td></tr>
      <tr><td>Avg holding period</td><td class="n">{avg_hold} days</td></tr>
      <tr><td>Max consecutive wins</td><td class="n gr">{max_w}</td></tr>
      <tr><td>Max consecutive losses</td><td class="n rd">{max_l}</td></tr>
      <tr><td>Still holding</td><td class="n">{holding_count}</td></tr>
    </table>
  </div>
  <div class="sec">
    <h2>Exit Reason Breakdown</h2>
    <table>
      <thead><tr><th>Reason</th><th>Count</th><th>Avg P&L</th><th>Total P&L</th></tr></thead>
      <tbody>{reason_rows}</tbody>
    </table>
  </div>
</div>

<div class="grid2">
  <div class="sec">
    <h2>Monthly P&L</h2>
    {monthly_svg}
  </div>
  <div class="sec">
    <h2>Avg P&L by Signal Strength</h2>
    {stars_svg}
  </div>
</div>

<!-- Trader commentary -->
<div class="sec" style="display:{show_commentary}">
  <h2>Trader Commentary <span class="tag">Stock Trader Agent</span></h2>
  <div class="commentary">{commentary}</div>
</div>

<!-- Trade log -->
<div class="sec">
  <h2>Trade Log <span class="tag">{total_trades} trades</span></h2>
  <div class="tw">
  <table>
    <thead><tr>
      <th class="c">#</th><th>Code</th><th>Name</th><th class="c">Signal</th>
      <th>Entry Date</th><th>Entry</th><th>Exit Date</th><th>Exit</th>
      <th class="c">Reason</th><th>P&L</th><th class="c">Days</th>
    </tr></thead>
    <tbody>{log_rows}</tbody>
  </table>
  </div>
</div>

<footer>Generated {now} &middot; CTA Backtest v1.0</footer>
</div>
</body>
</html>"""


if __name__ == "__main__":
    main()
