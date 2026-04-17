"""Generate a single combined daily Markdown report — GitHub-friendly.

Compiles into one .md file:
  1. Signal summary + top-15 table
  2. Fundamental analysis (Revenue Analyst)
  3. Industry analysis (Industry Analyst)
  4. Chief Strategist synthesis
  5. Trader action list
  6. Backtest validation metrics

Usage:
    python generate_daily_md.py              # today's date
    python generate_daily_md.py 2026-04-15   # specific date
"""
from __future__ import annotations

import json
import sys
import io
from datetime import datetime, date
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config import DATA_DIR, OUTPUT_DIR


# ── Helpers ────────────────────────────────────────────

def _read_md(name: str) -> str:
    p = DATA_DIR / "agent_outputs" / f"{name}.md"
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def _top_signals_table(results: list[dict], limit: int = 15) -> str:
    top = [r for r in results if r.get("stars", 0) >= 3][:limit]
    if not top:
        return "_今日無 ★3+ 反轉訊號_"
    lines = [
        "| # | 代號 | 名稱 | 市場 | 收盤 | 漲跌% | RSI | MACD | 星等 | 訊號描述 |",
        "|---|------|------|------|------|-------|-----|------|------|----------|",
    ]
    for i, r in enumerate(top, 1):
        sigs = " / ".join(r["descriptions"])
        chg = r["pct_change"]
        chg_str = f"🟢 +{chg:.1f}%" if chg >= 0 else f"🔴 {chg:.1f}%"
        stars = "★" * r["stars"]
        lines.append(
            f'| {i} | `{r["code"]}` | {r["name"]} | {r["market"]} | '
            f'{r["close"]:.1f} | {chg_str} | '
            f'{r["rsi"]:.1f} | {r["macd"]:.2f} | {stars} | {sigs} |'
        )
    return "\n".join(lines)


def _backtest_section(bt: dict | None, title: str = "") -> str:
    if not bt:
        return "_尚無回測資料。執行 `python backtest.py` 產生。_"

    m = bt["metrics"]
    s = bt["strategy"]

    win_emoji = "✅" if m["win_rate"] >= 50 else "⚠️"
    pf_emoji = "✅" if m["profit_factor"] > 1 else "❌"
    ret_emoji = "📈" if m["total_return_pct"] >= 0 else "📉"

    out: list[str] = []

    if title:
        out.append(f"### {title}")
        out.append("")

    out.append("#### 📋 策略參數")
    out.append("")
    out.append(f"- **停損**: `{s['stop_loss_pct']}%`")
    out.append(f"- **目標**: `+{s['target_pct']}%`")
    out.append(f"- **最長持有**: `{s['max_hold_days']} 交易日`")
    if s.get("early_exit_days", 0) > 0:
        out.append(
            f"- **早期出場**: `{s['early_exit_days']} 日內漲幅 < "
            f"+{s['early_exit_min_pct']}%` 提前出場"
        )
    out.append(f"- **單筆倉位**: `{s['position_pct']}%` of portfolio")
    out.append(f"- **最低訊號強度**: `{s['min_stars']}★`")
    out.append("")

    out.append("#### 🎯 績效指標")
    out.append("")
    out.append("| 指標 | 數值 |")
    out.append("|------|------|")
    out.append(f"| 總交易數 | **{m['total_trades']}** |")
    out.append(f"| 勝率 | {win_emoji} **{m['win_rate']}%** |")
    out.append(f"| 平均單筆盈虧 | **{m['avg_pnl']:+.2f}%** |")
    out.append(f"| 平均獲利 | {m['avg_win']:+.2f}% |")
    out.append(f"| 平均虧損 | {m['avg_loss']:+.2f}% |")
    pf_str = f"{m['profit_factor']:.2f}" if m['profit_factor'] != float('inf') else "∞"
    out.append(f"| Profit Factor | {pf_emoji} **{pf_str}** |")
    out.append(f"| 組合累計報酬 | {ret_emoji} **{m['total_return_pct']:+.2f}%** |")
    out.append(f"| 最佳單筆 | +{m['best_trade']:.2f}% |")
    out.append(f"| 最差單筆 | {m['worst_trade']:.2f}% |")
    out.append(f"| 平均持有天數 | {m['avg_hold_days']} 天 |")
    out.append(f"| 最多連勝 | {m['max_consec_wins']} 次 |")
    out.append(f"| 最多連敗 | {m['max_consec_losses']} 次 |")
    out.append("")

    if m.get("by_reason"):
        out.append("#### 📊 出場原因分解")
        out.append("")
        out.append("| 出場原因 | 筆數 | 平均盈虧 | 累計盈虧 |")
        out.append("|----------|------|----------|----------|")
        for reason, r in m["by_reason"].items():
            out.append(
                f'| {reason} | {r["count"]} | '
                f'{r["avg_pnl"]:+.2f}% | {r["total_pnl"]:+.1f}% |'
            )
        out.append("")

    if m.get("by_stars"):
        out.append("#### ⭐ 訊號強度表現")
        out.append("")
        out.append("| 星等 | 筆數 | 勝率 | 平均盈虧 |")
        out.append("|------|------|------|----------|")
        for stars in sorted(m["by_stars"].keys()):
            d = m["by_stars"][stars]
            out.append(
                f'| {"★" * int(stars)} | {d["count"]} | '
                f'{d["win_rate"]}% | {d["avg_pnl"]:+.2f}% |'
            )
        out.append("")

    if m.get("monthly"):
        out.append("#### 📅 月度累計 P&L")
        out.append("")
        out.append("| 月份 | 累計盈虧 |")
        out.append("|------|----------|")
        for month in sorted(m["monthly"].keys()):
            pnl = m["monthly"][month]
            emoji = "🟢" if pnl >= 0 else "🔴"
            out.append(f"| {month} | {emoji} {pnl:+.1f}% |")
        out.append("")

    return "\n".join(out)


def _trade_log_section(bt: dict | None, title: str = "", recent_n: int = 30) -> str:
    """Render trade log table: all open positions + last N closed trades."""
    if not bt or not bt.get("trades"):
        return ""

    all_trades = bt["trades"]
    holding = [t for t in all_trades if t.get("exit_reason") == "持倉中"]
    closed = [t for t in all_trades if t.get("exit_reason") != "持倉中"]
    recent_closed = closed[-recent_n:] if len(closed) > recent_n else closed

    out: list[str] = []
    if title:
        out.append(f"### {title}")
        out.append("")

    # Open positions first
    if holding:
        out.append(f"#### 持倉中 ({len(holding)} 筆)")
        out.append("")
        out.append("| 代號 | 名稱 | 星等 | 進場日 | 進場價 | 現價 | 損益% | 持有天數 | 訊號描述 |")
        out.append("|------|------|------|--------|--------|------|-------|----------|----------|")
        for t in holding:
            stars = "★" * t.get("signal_stars", 0)
            pnl = t.get("pnl_pct", 0)
            pnl_str = f"🟢 {pnl:+.2f}%" if pnl >= 0 else f"🔴 {pnl:+.2f}%"
            sigs = " / ".join(t.get("signal_descs", []))
            out.append(
                f'| `{t["code"]}` | {t["name"]} | {stars} | '
                f'{t["entry_date"]} | {t["entry_price"]:.2f} | '
                f'{t.get("exit_price", 0):.2f} | {pnl_str} | '
                f'{t.get("holding_days", 0)}d | {sigs} |'
            )
        out.append("")

    # Recent closed trades
    if recent_closed:
        out.append(f"#### 近期已平倉 (最近 {len(recent_closed)} 筆 / 共 {len(closed)} 筆)")
        out.append("")
        out.append("| 代號 | 名稱 | 星等 | 進場日 | 進場價 | 出場日 | 出場價 | 損益% | 天數 | 原因 |")
        out.append("|------|------|------|--------|--------|--------|--------|-------|------|------|")
        for t in recent_closed:
            stars = "★" * t.get("signal_stars", 0)
            pnl = t.get("pnl_pct", 0)
            pnl_str = f"🟢 {pnl:+.2f}%" if pnl >= 0 else f"🔴 {pnl:+.2f}%"
            out.append(
                f'| `{t["code"]}` | {t["name"]} | {stars} | '
                f'{t["entry_date"]} | {t["entry_price"]:.2f} | '
                f'{t.get("exit_date", "")} | {t.get("exit_price", 0):.2f} | '
                f'{pnl_str} | {t.get("holding_days", 0)}d | {t.get("exit_reason", "")} |'
            )
        out.append("")

    return "\n".join(out)


# ── Main generator ─────────────────────────────────────

def generate(date_str: str) -> Path:
    signals_file = DATA_DIR / "signals_latest.json"
    if not signals_file.exists():
        raise FileNotFoundError(
            f"{signals_file} not found. Run  python main.py --export  first."
        )
    signals = json.loads(signals_file.read_text(encoding="utf-8"))
    results = signals["results"]
    total_scanned = signals["total_scanned"]

    strong = sum(1 for r in results if r["level"] == "strong")
    medium = sum(1 for r in results if r["level"] == "medium")
    watch  = sum(1 for r in results if r["level"] == "watch")

    fundamentals = _read_md("fundamentals")
    industry     = _read_md("industry")
    strategy     = _read_md("strategy")
    trades       = _read_md("trades")
    bt_comment   = _read_md("backtest_commentary")

    bt_file = DATA_DIR / "backtest_latest.json"
    bt = json.loads(bt_file.read_text(encoding="utf-8")) if bt_file.exists() else None

    bt_mom_file = DATA_DIR / "backtest_momentum.json"
    bt_mom = json.loads(bt_mom_file.read_text(encoding="utf-8")) if bt_mom_file.exists() else None

    bt_man_file = DATA_DIR / "backtest_manual.json"
    bt_man = json.loads(bt_man_file.read_text(encoding="utf-8")) if bt_man_file.exists() else None

    bt_ofc_file = DATA_DIR / "backtest_office.json"
    bt_ofc = json.loads(bt_ofc_file.read_text(encoding="utf-8")) if bt_ofc_file.exists() else None

    has_multi = bt_mom is not None or bt_man is not None or bt_ofc is not None

    # ── Compose ───────────────────────────────────────
    p: list[str] = []

    p.append(f"# 📊 CTA Daily Report — {date_str}")
    p.append("")
    p.append(
        "> 台股前 1000 大 · RSI(14) / MACD(12,26,9) 抄底反轉 · 6-Agent AI 分析  "
    )
    p.append(
        "> 📁 [GitHub Repo](https://github.com/mark00lui/Stock_U_turn) · "
        "🌐 [Live Dashboard](https://mark00lui.github.io/Stock_U_turn/) · "
        "🤖 Powered by Claude Code"
    )
    p.append("")
    p.append("---")
    p.append("")

    # Executive summary
    p.append("## 🎯 執行摘要")
    p.append("")
    p.append("| 項目 | 數值 |")
    p.append("|------|------|")
    p.append(f"| 📅 分析日期 | `{date_str}` |")
    p.append(f"| 🔍 掃描標的 | `{total_scanned}` 檔 |")
    p.append(
        f"| 📡 反轉訊號 | **{len(results)}** 檔  "
        f"(🔥 Strong {strong} / ⚡ Call {medium} / 👁 Watch {watch}) |"
    )
    p.append(f"| 🏆 Top 推薦 | 見下方第 3 節 |")
    p.append(f"| 📈 策略回測 | 見下方第 7 節 |")
    p.append("")
    p.append("---")
    p.append("")

    p.append("## 📡 今日 Top 15 反轉訊號")
    p.append("")
    p.append(_top_signals_table(results, 15))
    p.append("")
    p.append("---")
    p.append("")

    p.append("## 🔍 基本面分析")
    p.append("")
    p.append("> *by Revenue & Earnings Analyst (月營收 + 季財報)*")
    p.append("")
    p.append(fundamentals if fundamentals else "_今日未產出_")
    p.append("")
    p.append("---")
    p.append("")

    p.append("## 🏭 行業分析")
    p.append("")
    p.append("> *by AI Industry Analyst (產業趨勢 + 景氣循環)*")
    p.append("")
    p.append(industry if industry else "_今日未產出_")
    p.append("")
    p.append("---")
    p.append("")

    p.append("## 🧠 總策略師判讀")
    p.append("")
    p.append("> *by Chief Strategist (技術 40% + 基本面 30% + 行業 30%)*")
    p.append("")
    p.append(strategy if strategy else "_今日未產出_")
    p.append("")
    p.append("---")
    p.append("")

    p.append("## 💼 操作股單 — 交易計畫")
    p.append("")
    p.append("> *by Stock Trader (進場/停損/目標/倉位/風報比)*")
    p.append("")
    p.append(trades if trades else "_今日未產出_")
    p.append("")
    p.append("---")
    p.append("")

    p.append("## 📈 策略回測驗證")
    p.append("")

    if has_multi:
        if bt_mom:
            p.append(_backtest_section(
                bt_mom, "🚀 動能方案 (Momentum Strategy)"))
            p.append("")
        if bt_man:
            p.append(_backtest_section(
                bt_man, "🎯 手動精選方案 (Manual Strategy J)"))
            p.append("")
        if bt_ofc:
            p.append(_backtest_section(
                bt_ofc,
                "🧑‍💼 上班族三檔方案 (Office Worker — 3 Picks)"))
            p.append("")
    else:
        p.append(_backtest_section(bt))
        p.append("")

    if bt_comment:
        p.append("### 💬 操盤手回測評析")
        p.append("")
        p.append(bt_comment)
        p.append("")

    # Trade logs (at end of report)
    if has_multi:
        p.append("---")
        p.append("")
        p.append("## 📋 回測交易進出明細")
        p.append("")
        if bt_mom:
            p.append(_trade_log_section(
                bt_mom, "🚀 動能方案 — 交易紀錄"))
            p.append("")
        if bt_man:
            p.append(_trade_log_section(
                bt_man, "🎯 手動精選方案 — 交易紀錄"))
            p.append("")
        if bt_ofc:
            p.append(_trade_log_section(
                bt_ofc,
                "🧑‍💼 上班族三檔方案 — 交易紀錄"))
            p.append("")
    elif bt:
        p.append("---")
        p.append("")
        p.append("## 📋 回測交易進出明細")
        p.append("")
        p.append(_trade_log_section(bt, "交易紀錄"))
        p.append("")

    p.append("---")
    p.append("")
    p.append("## ⚠️ 免責聲明")
    p.append("")
    p.append(
        "本報告由 AI 自動生成，僅供研究參考，**不構成任何投資建議**。"
        "過去回測績效不代表未來表現，投資前請獨立判斷並自行承擔風險。"
    )
    p.append("")
    p.append("---")
    p.append("")
    p.append(
        f"*Generated at `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}` · "
        f"[📚 所有報告](./README.md) · [🌐 Dashboard](https://mark00lui.github.io/Stock_U_turn/)*"
    )
    p.append("")

    content = "\n".join(p)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"cta_daily_{date_str}.md"
    out.write_text(content, encoding="utf-8")
    return out


def main() -> None:
    date_str = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    out = generate(date_str)
    print(f"Daily MD report: {out}")

    # refresh archive indexes
    from update_index import main as refresh
    refresh()


if __name__ == "__main__":
    main()
