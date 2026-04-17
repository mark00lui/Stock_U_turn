"""Generate a single combined daily Markdown report — GitHub-friendly.

Restructured as a narrative flow:
  0. Title + Navigator
  1. Signal Scan — what the system found today
  2. Multi-Dimensional Validation — fundamentals + industry
  3. Integrated Scoring — Top 10 recommendations
  4. Three Strategy Dashboards — each with holdings + tomorrow's plan
  5. Full Trade Logs (appendix, collapsed)
  6. Disclaimer

Usage:
    python generate_daily_md.py              # today's date
    python generate_daily_md.py 2026-04-15   # specific date
"""
from __future__ import annotations

import json
import re
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


def _load_bt(label: str) -> dict | None:
    p = DATA_DIR / f"backtest_{label}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _strip_agent_heading(md: str) -> str:
    """Strip H1 title from agent markdown, downgrade ## → ####."""
    lines = md.split("\n")
    # Remove first H1 line
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    text = "\n".join(lines)
    # Downgrade headings: ## → ####
    text = re.sub(r"^## ", "#### ", text, flags=re.MULTILINE)
    text = re.sub(r"^### ", "##### ", text, flags=re.MULTILINE)
    return text.strip()


# ── Section 0: Title + Navigator ─────────────────────

def _section_title(p: list[str], date_str: str) -> None:
    p.append(f"# CTA Daily Report — {date_str}")
    p.append("")
    p.append(
        "> 台股前 1000 大 · RSI(14) / MACD(12,26,9) 抄底反轉 · 6-Agent AI 分析  "
    )
    p.append(
        "> [GitHub Repo](https://github.com/mark00lui/Stock_U_turn) · "
        "[Live Dashboard](https://mark00lui.github.io/Stock_U_turn/) · "
        "Powered by Claude Code"
    )
    p.append("")
    p.append("---")
    p.append("")
    p.append("**Report Navigator**")
    p.append("")
    p.append("| Step | Section | Key Question |")
    p.append("|------|---------|--------------|")
    p.append("| 1 | [訊號掃描](#1-訊號掃描) | 系統今天偵測到什麼？ |")
    p.append("| 2 | [三維驗證](#2-三維驗證) | 基本面和行業支持嗎？ |")
    p.append("| 3 | [整合評分](#3-整合評分) | 哪些股票通過三重篩選？ |")
    p.append("| 4 | [策略儀表板](#4-策略儀表板) | 明天要買什麼？賣什麼？ |")
    p.append("| 5 | [交易明細](#5-完整交易明細) | 歷史進出場紀錄 |")
    p.append("")


# ── Section 1: Signal Scan ────────────────��──────────

def _section_signal_scan(p: list[str], results: list[dict], total: int) -> None:
    p.append("## 1. 訊號掃描")
    p.append("")
    p.append(f"> 今日掃描 **{total}** 檔，偵測到 **{len(results)}** 檔反轉訊號。")
    p.append("")

    s5 = sum(1 for r in results if r["stars"] == 5)
    s4 = sum(1 for r in results if r["stars"] == 4)
    s3 = sum(1 for r in results if r["stars"] == 3)
    s12 = sum(1 for r in results if r["stars"] <= 2)
    strong = s5 + s4

    p.append("| 篩選漏斗 | 數量 |")
    p.append("|----------|------|")
    p.append(f"| 掃描標的 | {total} |")
    p.append(f"| 反轉訊號 | {len(results)} |")
    p.append(f"| ★★★★★ (5 星) | {s5} |")
    p.append(f"| ★★★★ (4 星) | {s4} |")
    p.append(f"| ★★★ (3 星) | {s3} |")
    p.append(f"| ★★ 以下 (觀察) | {s12} |")
    p.append(f"| **進入驗證** (4★+) | **{strong}** |")
    p.append("")

    # Top 10 signal table
    top = [r for r in results if r.get("stars", 0) >= 3][:10]
    if top:
        p.append("**Top 10 反轉訊號：**")
        p.append("")
        p.append("| # | 代號 | 名稱 | 市場 | 收盤 | 漲跌% | RSI | 星等 | 訊號描述 |")
        p.append("|---|------|------|------|------|-------|-----|------|----------|")
        for i, r in enumerate(top, 1):
            sigs = " / ".join(r["descriptions"])
            chg = r["pct_change"]
            chg_s = f"+{chg:.1f}%" if chg >= 0 else f"{chg:.1f}%"
            stars = "★" * r["stars"]
            p.append(
                f'| {i} | `{r["code"]}` | {r["name"]} | {r["market"]} | '
                f'{r["close"]:.1f} | {chg_s} | {r["rsi"]:.1f} | {stars} | {sigs} |'
            )
        p.append("")

    p.append(f"> 以上 {strong} 檔 4★+ 強訊號進入下一步三維驗證...")
    p.append("")
    p.append("---")
    p.append("")


# ── Section 2: Multi-Dimensional Validation ──────────

def _section_validation(p: list[str], fundamentals: str, industry: str) -> None:
    p.append("## 2. 三維驗證")
    p.append("")
    p.append("> 兩位 AI 分析師獨立評估訊號清單：哪些有基本面支撐？哪些產業趨勢正確？")
    p.append("")

    p.append("### 2a. 基本面檢查")
    p.append("")
    p.append("> *by Revenue & Earnings Analyst (月營收 + 季財報)*")
    p.append("")
    if fundamentals:
        p.append(_strip_agent_heading(fundamentals))
    else:
        p.append("_今日未產出_")
    p.append("")
    p.append("")

    p.append("### 2b. 行業定位")
    p.append("")
    p.append("> *by Industry Analyst (產業趨勢 + 景氣循環)*")
    p.append("")
    if industry:
        p.append(_strip_agent_heading(industry))
    else:
        p.append("_今日未產出_")
    p.append("")
    p.append("")
    p.append("> 驗證完成。Chief Strategist 整合技術(40%) + 基本面(30%) + 行業(30%) 進行評分...")
    p.append("")
    p.append("---")
    p.append("")


# ── Section 3: Integrated Scoring ────────────────────

def _section_scoring(p: list[str], strategy: str) -> None:
    p.append("## 3. 整合評分")
    p.append("")
    p.append("> *by Chief Strategist — 整合分 = 技術×40% + 基本面×30% + 行業×30%*")
    p.append("")
    if strategy:
        p.append(_strip_agent_heading(strategy))
    else:
        p.append("_今日未產出_")
    p.append("")
    p.append("")
    p.append("> 以上推薦進入三套策略，各自依風格配置...")
    p.append("")
    p.append("---")
    p.append("")


# ── Section 4: Strategy Dashboards ───────────────────

def _compact_metrics(bt: dict) -> str:
    """Compact backtest metrics table."""
    if not bt:
        return "_無回測資料_"
    m = bt["metrics"]
    s = bt["strategy"]

    closed_n = m["total_trades"]
    open_n = sum(1 for t in bt.get("trades", []) if t.get("exit_reason") == "持倉中")
    pf = f'{m["profit_factor"]:.2f}' if m["profit_factor"] != float("inf") else "∞"

    out = []
    out.append("| 指標 | 數值 |")
    out.append("|------|------|")
    out.append(f'| 交易數 | {closed_n} 已平倉 + {open_n} 持倉中 |')
    out.append(f'| 勝率 | **{m["win_rate"]}%** |')
    out.append(f'| 平均損益 | **{m["avg_pnl"]:+.2f}%** |')
    out.append(f'| Profit Factor | **{pf}** |')
    out.append(f'| 累計報酬 | **{m["total_return_pct"]:+.1f}%** |')
    out.append(f'| 平均獲利 / 虧損 | {m["avg_win"]:+.2f}% / {m["avg_loss"]:+.2f}% |')
    out.append(f'| 平均持有 | {m["avg_hold_days"]} 天 |')
    out.append(f'| 最大連敗 | {m["max_consec_losses"]} 次 |')
    out.append("")

    if m.get("by_reason"):
        out.append("| 出場原因 | 筆數 | 平均損益 |")
        out.append("|----------|------|----------|")
        for reason in ("達標", "停損", "到期", "早期出場"):
            if reason in m["by_reason"]:
                r = m["by_reason"][reason]
                out.append(f'| {reason} | {r["count"]} | {r["avg_pnl"]:+.2f}% |')
        out.append("")

    return "\n".join(out)


def _portfolio_summary(bt: dict, max_top: int = 10, max_bottom: int = 5) -> str:
    """Top N best + bottom M worst open positions."""
    if not bt or not bt.get("trades"):
        return "_無持倉資料_"

    holding = [t for t in bt["trades"] if t.get("exit_reason") == "持倉中"]
    if not holding:
        return "_目前無持倉_"

    holding.sort(key=lambda t: t.get("pnl_pct", 0), reverse=True)
    total = len(holding)

    def _row(t: dict) -> str:
        stars = "★" * t.get("signal_stars", 0)
        pnl = t.get("pnl_pct", 0)
        pnl_s = f"+{pnl:.2f}%" if pnl >= 0 else f"{pnl:.2f}%"
        return (
            f'| `{t["code"]}` | {t["name"]} | {stars} | '
            f'{t["entry_date"]} | {t["entry_price"]:.2f} | '
            f'{t.get("exit_price", 0):.2f} | {pnl_s} | {t.get("holding_days", 0)}d |'
        )

    out = []
    out.append(f"**持倉中：{total} 筆**")
    out.append("")
    out.append("| 代號 | 名稱 | 星等 | 進場日 | 進場價 | 現價 | 損益% | 天數 |")
    out.append("|------|------|------|--------|--------|------|-------|------|")

    if total <= max_top + max_bottom + 3:
        # Show all
        for t in holding:
            out.append(_row(t))
    else:
        # Top N
        for t in holding[:max_top]:
            out.append(_row(t))
        skipped = total - max_top - max_bottom
        out.append(f"| ... | *另 {skipped} 筆* | | | | | | |")
        # Bottom M
        for t in holding[-max_bottom:]:
            out.append(_row(t))

    out.append("")
    return "\n".join(out)


def _tomorrow_action(bt: dict, signals: list[dict]) -> str:
    """Cross-reference today's signals vs current holdings → buy candidates + exit alerts."""
    if not bt or not bt.get("trades"):
        return "_無法產出明日計畫_"

    strat = bt.get("strategy", {})
    min_stars = strat.get("min_stars", 3)
    max_hold = strat.get("max_hold_days", 20)
    sl = strat.get("stop_loss_pct", -8)
    tgt = strat.get("target_pct", 10)

    holding = [t for t in bt["trades"] if t.get("exit_reason") == "持倉中"]
    held_codes = {t["code"] for t in holding}

    # New buy candidates: today's signals matching strategy, not already held
    candidates = [
        s for s in signals
        if s.get("stars", 0) >= min_stars and s["code"] not in held_codes
    ][:8]

    # Holdings approaching exit
    approaching_exit = []
    for t in holding:
        days = t.get("holding_days", 0)
        pnl = t.get("pnl_pct", 0)
        reasons = []
        if days >= max_hold - 3:
            reasons.append(f"到期倒數 {max_hold - days}d")
        if pnl <= sl + 2:
            reasons.append(f"接近停損 ({pnl:+.1f}%)")
        if pnl >= tgt - 3:
            reasons.append(f"接近達標 ({pnl:+.1f}%)")
        if reasons:
            approaching_exit.append((t, " / ".join(reasons)))

    out = []

    # Buy candidates
    out.append("**新買入候選** (今日訊號，尚未持有)：")
    out.append("")
    if candidates:
        out.append("| 代號 | 名稱 | 星等 | ��盤 | RSI | 訊號 | 進場區間 | 停損 |")
        out.append("|------|------|------|------|-----|------|----------|------|")
        for s in candidates:
            stars = "★" * s["stars"]
            sigs = " / ".join(s["descriptions"])
            close = s["close"]
            entry_hi = close * 1.005
            stop = close * (1 + sl / 100)
            out.append(
                f'| `{s["code"]}` | {s["name"]} | {stars} | '
                f'{close:.1f} | {s["rsi"]:.1f} | {sigs} | '
                f'{close:.1f}-{entry_hi:.1f} | {stop:.1f} ({sl}%) |'
            )
        out.append("")
    else:
        out.append("_今日無新候選_")
        out.append("")

    # Exit alerts
    if approaching_exit:
        out.append(f"**出場警示** ({len(approaching_exit)} 筆即將觸發)：")
        out.append("")
        out.append("| 代號 | 名稱 | 進場價 | 現價 | 損益% | 天數 | 警示原因 |")
        out.append("|------|------|--------|------|-------|------|----------|")
        for t, reason in approaching_exit[:10]:
            pnl = t.get("pnl_pct", 0)
            pnl_s = f"+{pnl:.2f}%" if pnl >= 0 else f"{pnl:.2f}%"
            out.append(
                f'| `{t["code"]}` | {t["name"]} | {t["entry_price"]:.2f} | '
                f'{t.get("exit_price", 0):.2f} | {pnl_s} | '
                f'{t.get("holding_days", 0)}d | {reason} |'
            )
        out.append("")
    else:
        out.append("**出場警示**：_目前無持倉接近出場條件_")
        out.append("")

    return "\n".join(out)


def _recent_closed(bt: dict, n: int = 10) -> str:
    """Last N closed trades."""
    if not bt or not bt.get("trades"):
        return ""

    closed = [t for t in bt["trades"] if t.get("exit_reason") != "持倉中"]
    recent = closed[-n:] if len(closed) > n else closed
    if not recent:
        return "_尚無已平倉交易_"

    out = []
    out.append(f"**近期平倉** (最近 {len(recent)} 筆 / 共 {len(closed)} 筆)：")
    out.append("")
    out.append("| 代號 | 名稱 | 進場 | 出場 | 損益% | 天數 | 原因 |")
    out.append("|------|------|------|------|-------|------|------|")
    for t in recent:
        pnl = t.get("pnl_pct", 0)
        pnl_s = f"+{pnl:.2f}%" if pnl >= 0 else f"{pnl:.2f}%"
        out.append(
            f'| `{t["code"]}` | {t["name"]} | '
            f'{t["entry_date"]} {t["entry_price"]:.0f} | '
            f'{t.get("exit_date", "")} {t.get("exit_price", 0):.0f} | '
            f'{pnl_s} | {t.get("holding_days", 0)}d | {t.get("exit_reason", "")} |'
        )
    out.append("")
    return "\n".join(out)


def _strategy_dashboard(
    p: list[str],
    bt: dict | None,
    signals: list[dict],
    title: str,
    desc: str,
    max_top: int = 10,
    max_bottom: int = 5,
) -> None:
    """One self-contained strategy dashboard block."""
    p.append(f"### {title}")
    p.append("")
    p.append(f"> {desc}")
    p.append("")

    if not bt:
        p.append("_此策略回測資料尚未產出_")
        p.append("")
        return

    s = bt.get("strategy", {})

    # Strategy ID card
    p.append("**策略參數：**")
    p.append("")
    params = (
        f"停損 `{s.get('stop_loss_pct', 0)}%` · "
        f"目標 `+{s.get('target_pct', 0)}%` · "
        f"持有 `{s.get('max_hold_days', 0)}d` · "
        f"星等 `{s.get('min_stars', 0)}★+` · "
        f"倉位 `{s.get('position_pct', 0)}%`"
    )
    ee = s.get("early_exit_days", 0)
    if ee > 0:
        params += f" · 早期出場 `{ee}d < +{s.get('early_exit_min_pct', 0)}%`"
    p.append(params)
    p.append("")

    # Compact metrics
    p.append("#### 回測績效")
    p.append("")
    p.append(_compact_metrics(bt))
    p.append("")

    # Today's portfolio
    p.append("#### 今日持倉")
    p.append("")
    p.append(_portfolio_summary(bt, max_top=max_top, max_bottom=max_bottom))
    p.append("")

    # Tomorrow's plan
    p.append("#### 明日操作計畫")
    p.append("")
    p.append(_tomorrow_action(bt, signals))
    p.append("")

    # Recent closed
    p.append("#### 近期平倉")
    p.append("")
    p.append(_recent_closed(bt, n=10))
    p.append("")


def _section_dashboards(
    p: list[str],
    bt_mom: dict | None,
    bt_man: dict | None,
    bt_ofc: dict | None,
    signals: list[dict],
    trades_md: str,
) -> None:
    p.append("## 4. 策略儀表板")
    p.append("")
    p.append("> 同一池訊號，三種操作風格。選擇適合你的策略：")
    p.append("")

    # Comparison table
    p.append("| | 動能方案 | 手動精選 J | 上班族三檔 |")
    p.append("|---|---|---|---|")
    p.append("| 風格 | 高頻量化 | 中頻篩選 | 低頻集中 |")

    def _val(bt, key, fmt="{}", default="—"):
        if not bt:
            return default
        s = bt.get("strategy", {})
        m = bt.get("metrics", {})
        if key in s:
            return fmt.format(s[key])
        if key in m:
            return fmt.format(m[key])
        return default

    p.append(
        f'| 停損/目標 | {_val(bt_mom, "stop_loss_pct")}% / +{_val(bt_mom, "target_pct")}% | '
        f'{_val(bt_man, "stop_loss_pct")}% / +{_val(bt_man, "target_pct")}% | '
        f'{_val(bt_ofc, "stop_loss_pct")}% / +{_val(bt_ofc, "target_pct")}% |'
    )
    p.append(
        f'| 星等 | {_val(bt_mom, "min_stars")}★+ | '
        f'{_val(bt_man, "min_stars")}★+ | '
        f'{_val(bt_ofc, "min_stars")}★+ |'
    )
    p.append(
        f'| 持有/倉位 | {_val(bt_mom, "max_hold_days")}d / {_val(bt_mom, "position_pct")}% | '
        f'{_val(bt_man, "max_hold_days")}d / {_val(bt_man, "position_pct")}% | '
        f'{_val(bt_ofc, "max_hold_days")}d / {_val(bt_ofc, "position_pct")}% |'
    )
    p.append(
        f'| 勝率 | {_val(bt_mom, "win_rate", "{}%")} | '
        f'{_val(bt_man, "win_rate", "{}%")} | '
        f'{_val(bt_ofc, "win_rate", "{}%")} |'
    )

    def _pf(bt):
        if not bt:
            return "—"
        v = bt.get("metrics", {}).get("profit_factor", 0)
        return f"{v:.2f}" if v != float("inf") else "∞"

    p.append(f"| PF | {_pf(bt_mom)} | {_pf(bt_man)} | {_pf(bt_ofc)} |")
    p.append(
        f'| 報酬 | {_val(bt_mom, "total_return_pct", "{:+.1f}%")} | '
        f'{_val(bt_man, "total_return_pct", "{:+.1f}%")} | '
        f'{_val(bt_ofc, "total_return_pct", "{:+.1f}%")} |'
    )
    p.append("")
    p.append("---")
    p.append("")

    # Individual dashboards
    _strategy_dashboard(
        p, bt_mom, signals,
        "4.1 動能方案 (Momentum)",
        "高頻短線，自動化交易風格。停損快、換股快、靠量取勝。",
        max_top=8, max_bottom=5,
    )
    p.append("---")
    p.append("")

    _strategy_dashboard(
        p, bt_man, signals,
        "4.2 手動精選方案 (Manual J)",
        "中頻篩選，每日精選進場。R:R 1:2，搭配早期出場收割。",
        max_top=10, max_bottom=5,
    )
    p.append("---")
    p.append("")

    _strategy_dashboard(
        p, bt_ofc, signals,
        "4.3 上班族三檔方案 (Office Worker)",
        "前晚 15 分鐘看報告 → 隔天掛單。同時最多 3 檔，持有 20-30 天，R:R 1:2.5。",
        max_top=15, max_bottom=5,
    )
    p.append("---")
    p.append("")

    # Trader consolidated plan
    if trades_md:
        p.append("### 4.4 操盤手綜合建議")
        p.append("")
        p.append("> *by Stock Trader — 進場/停損/目標/倉位/風報比*")
        p.append("")
        p.append(_strip_agent_heading(trades_md))
        p.append("")
        p.append("---")
        p.append("")


# ── Section 5: Full Trade Logs (appendix) ────────────

def _section_trade_logs(
    p: list[str],
    bt_mom: dict | None,
    bt_man: dict | None,
    bt_ofc: dict | None,
) -> None:
    p.append("## 5. 完整交易明細")
    p.append("")
    p.append("> 各策略完整持倉 + 近期平倉。使用摺疊區塊，點擊展開。")
    p.append("")

    for bt, label in [
        (bt_mom, "動能方案"),
        (bt_man, "手動精選方案"),
        (bt_ofc, "上班族三檔方案"),
    ]:
        if not bt or not bt.get("trades"):
            continue

        holding = [t for t in bt["trades"] if t.get("exit_reason") == "持倉中"]
        closed = [t for t in bt["trades"] if t.get("exit_reason") != "持倉中"]

        p.append(f"<details>")
        p.append(f"<summary><b>{label}</b>：{len(holding)} 筆持倉 + {len(closed)} 筆已平倉（點擊展開）</summary>")
        p.append("")

        if holding:
            p.append(f"#### 持倉中 ({len(holding)} 筆)")
            p.append("")
            p.append("| 代號 | 名稱 | 星等 | 進場日 | 進場價 | 現價 | 損益% | 天數 | 訊號 |")
            p.append("|------|------|------|--------|--------|------|-------|------|------|")
            for t in holding:
                stars = "★" * t.get("signal_stars", 0)
                pnl = t.get("pnl_pct", 0)
                pnl_s = f"+{pnl:.2f}%" if pnl >= 0 else f"{pnl:.2f}%"
                sigs = " / ".join(t.get("signal_descs", []))
                p.append(
                    f'| `{t["code"]}` | {t["name"]} | {stars} | '
                    f'{t["entry_date"]} | {t["entry_price"]:.2f} | '
                    f'{t.get("exit_price", 0):.2f} | {pnl_s} | '
                    f'{t.get("holding_days", 0)}d | {sigs} |'
                )
            p.append("")

        recent_closed = closed[-30:] if len(closed) > 30 else closed
        if recent_closed:
            p.append(f"#### 近期平倉 (最近 {len(recent_closed)} 筆 / 共 {len(closed)} 筆)")
            p.append("")
            p.append("| 代號 | 名稱 | 進場日 | 進場價 | 出場日 | 出場價 | 損益% | 天數 | 原因 |")
            p.append("|------|------|--------|--------|--------|--------|-------|------|------|")
            for t in recent_closed:
                pnl = t.get("pnl_pct", 0)
                pnl_s = f"+{pnl:.2f}%" if pnl >= 0 else f"{pnl:.2f}%"
                p.append(
                    f'| `{t["code"]}` | {t["name"]} | '
                    f'{t["entry_date"]} | {t["entry_price"]:.2f} | '
                    f'{t.get("exit_date", "")} | {t.get("exit_price", 0):.2f} | '
                    f'{pnl_s} | {t.get("holding_days", 0)}d | {t.get("exit_reason", "")} |'
                )
            p.append("")

        p.append("</details>")
        p.append("")

    p.append("---")
    p.append("")


# ── Section 6: Disclaimer ────────────────────────────

def _section_footer(p: list[str], date_str: str) -> None:
    p.append("## 免責聲明")
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
        f"[所有報告](./README.md) · "
        f"[Dashboard](https://mark00lui.github.io/Stock_U_turn/)*"
    )
    p.append("")


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

    fundamentals = _read_md("fundamentals")
    industry     = _read_md("industry")
    strategy     = _read_md("strategy")
    trades_md    = _read_md("trades")

    bt_mom = _load_bt("momentum")
    bt_man = _load_bt("manual")
    bt_ofc = _load_bt("office")

    # ── Compose ───────────────────────────────────────
    p: list[str] = []

    # Section 0: Title + Navigator
    _section_title(p, date_str)

    # Section 1: Signal Scan
    _section_signal_scan(p, results, total_scanned)

    # Section 2: Multi-Dimensional Validation
    _section_validation(p, fundamentals, industry)

    # Section 3: Integrated Scoring
    _section_scoring(p, strategy)

    # Section 4: Strategy Dashboards
    _section_dashboards(p, bt_mom, bt_man, bt_ofc, results, trades_md)

    # Section 5: Full Trade Logs
    _section_trade_logs(p, bt_mom, bt_man, bt_ofc)

    # Section 6: Disclaimer
    _section_footer(p, date_str)

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
