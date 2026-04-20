"""Generate CTA daily Markdown report — Serial Funnel Architecture.

Same stocks flow from signal scan → validation → scoring → action plan.

Sections:
  1. 訊號掃描 — funnel table + top signal list
  2. 三維驗證 — fundamentals + industry on the SAME stocks
  3. 最終推薦 — unified scoring + tomorrow's action plan
  4. 策略績效 — backtest dashboards (separate from picks)
  5. 交易明細 — collapsed appendix

Usage:
    python generate_daily_md.py              # today
    python generate_daily_md.py 2026-04-17   # specific date
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
    """Strip H1 title, downgrade ## → ####."""
    lines = md.split("\n")
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    text = "\n".join(lines)
    text = re.sub(r"^## ", "#### ", text, flags=re.MULTILINE)
    text = re.sub(r"^### ", "##### ", text, flags=re.MULTILINE)
    return text.strip()


# ── Section 1: Signal Scan ───────────────────────────

def _sec_signal_scan(p: list[str], results: list[dict], total: int) -> None:
    p.append("## 1. 訊號掃描：系統今天發現了什麼？")
    p.append("")

    s5 = sum(1 for r in results if r["stars"] == 5)
    s4 = sum(1 for r in results if r["stars"] == 4)
    s3 = sum(1 for r in results if r["stars"] == 3)
    strong = s5 + s4

    p.append("| 篩選漏斗 | 數量 | 說明 |")
    p.append("|----------|------|------|")
    p.append(f"| 掃描標的 | {total} | 台股前 1000 大 |")
    p.append(f"| 反轉訊號 | {len(results)} | RSI/MACD 偵測到反轉跡象 |")
    p.append(f"| ★★★★★ | {s5} | RSI 超賣反彈 + MACD 金叉 + 底部（最高品質）|")
    p.append(f"| ★★★★ | {s4} | 強反轉，兩項以上確認 |")
    p.append(f"| ★★★ | {s3} | 觀察級 |")
    p.append(f"| **精選漏斗 (5★)** | **{s5}** | **→ 進入三維驗證** |")
    p.append(f"| 備選 (4★) | {s4} | 5★ 不足時替補 |")
    p.append("")

    # Show funnel: 5★ first, then 4★ as backup
    funnel = [r for r in results if r["stars"] >= 5]
    backup = [r for r in results if r["stars"] == 4]
    if len(funnel) < 5 and backup:
        funnel = funnel + backup[:10 - len(funnel)]
    if funnel:
        p.append(f"**以下 {len(funnel)} 檔進入三維驗證（從頭到尾追蹤同一批股票）：**")
        p.append("")
        p.append("| # | 代號 | 名稱 | 市場 | 收盤 | 漲跌% | RSI | 星等 | 訊號描述 |")
        p.append("|---|------|------|------|------|-------|-----|------|----------|")
        for i, r in enumerate(funnel, 1):
            sigs = " / ".join(r["descriptions"])
            chg = r["pct_change"]
            chg_s = f"+{chg:.1f}%" if chg >= 0 else f"{chg:.1f}%"
            stars = "★" * r["stars"]
            p.append(
                f'| {i} | `{r["code"]}` | {r["name"]} | {r["market"]} | '
                f'{r["close"]:.1f} | {chg_s} | {r["rsi"]:.1f} | {stars} | {sigs} |'
            )
        p.append("")

    p.append("---")
    p.append("")


# ── Section 2: Validation ────────────────────────────

def _sec_validation(p: list[str], fundamentals: str, industry: str) -> None:
    p.append("## 2. 三維驗證：基本面與行業支持嗎？")
    p.append("")
    p.append("> 針對上方同一批訊號股票，兩位 AI 分析師逐檔驗證。")
    p.append("")

    p.append("### 2a. 基本面驗證")
    p.append("")
    p.append("> *Revenue Analyst — 針對訊號清單逐檔查月營收、EPS、財報*")
    p.append("")
    if fundamentals:
        p.append(_strip_agent_heading(fundamentals))
    else:
        p.append("_今日未產出_")
    p.append("")

    p.append("### 2b. 行業驗證")
    p.append("")
    p.append("> *Industry Analyst — 針對訊號清單逐檔查產業景氣、供應鏈位置*")
    p.append("")
    if industry:
        p.append(_strip_agent_heading(industry))
    else:
        p.append("_今日未產出_")
    p.append("")

    p.append("---")
    p.append("")


# ── Section 3: Final Picks + Action Plan ─────────────

def _sec_final_picks(p: list[str], strategy: str, trades_md: str,
                     bt_ofc: dict | None, signals: list[dict]) -> None:
    p.append("## 3. 最終推薦與明日操作")
    p.append("")
    p.append("> *Chief Strategist 整合三維評分 (技術 40% + 基本面 30% + 行業 30%) → 最終排序*")
    p.append("")

    if strategy:
        p.append(_strip_agent_heading(strategy))
    else:
        p.append("_今日未產出_")
    p.append("")

    # Tomorrow's action from office worker strategy
    if bt_ofc and bt_ofc.get("trades"):
        strat = bt_ofc.get("strategy", {})
        min_stars = strat.get("min_stars", 4)
        max_hold = strat.get("max_hold_days", 30)
        sl = strat.get("stop_loss_pct", -8)
        tgt = strat.get("target_pct", 20)

        holding = [t for t in bt_ofc["trades"] if t.get("exit_reason") == "持倉中"]
        held_codes = {t["code"] for t in holding}

        candidates = [
            s for s in signals
            if s.get("stars", 0) >= min_stars and s["code"] not in held_codes
        ][:8]

        approaching = []
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
                approaching.append((t, " / ".join(reasons)))

        p.append("### 明日操作計畫")
        p.append("")
        p.append(f"> 停損 `{sl}%` · 目標 `+{tgt}%` · 持有 `{max_hold}d` · 4★+ · 倉位 33%")
        p.append("")

        if candidates:
            p.append("**新買入候選：**")
            p.append("")
            p.append("| 代號 | 名稱 | 星等 | 收盤 | RSI | 訊號 | 進場區間 | 停損 |")
            p.append("|------|------|------|------|-----|------|----------|------|")
            for s in candidates:
                stars = "★" * s["stars"]
                sigs = " / ".join(s["descriptions"])
                close = s["close"]
                stop = close * (1 + sl / 100)
                p.append(
                    f'| `{s["code"]}` | {s["name"]} | {stars} | '
                    f'{close:.1f} | {s["rsi"]:.1f} | {sigs} | '
                    f'{close:.1f}-{close * 1.005:.1f} | {stop:.1f} |'
                )
            p.append("")
        else:
            p.append("**新買入候選**：今日訊號均已在回測持倉中，無新候選。持續持有現有部位。")
            p.append("")

        if approaching:
            p.append(f"**出場警示** ({len(approaching)} 筆)：")
            p.append("")
            p.append("| 代號 | 名稱 | 進場價 | 現價 | 損益% | 天數 | 警示 |")
            p.append("|------|------|--------|------|-------|------|------|")
            for t, reason in approaching[:15]:
                pnl = t.get("pnl_pct", 0)
                pnl_s = f"+{pnl:.2f}%" if pnl >= 0 else f"{pnl:.2f}%"
                p.append(
                    f'| `{t["code"]}` | {t["name"]} | {t["entry_price"]:.2f} | '
                    f'{t.get("exit_price", 0):.2f} | {pnl_s} | '
                    f'{t.get("holding_days", 0)}d | {reason} |'
                )
            p.append("")

    # Trader plan
    if trades_md:
        p.append("### 操盤手交易計畫")
        p.append("")
        p.append("> *Stock Trader — 進場/停損/目標/倉位/風報比*")
        p.append("")
        p.append(_strip_agent_heading(trades_md))
        p.append("")

    p.append("---")
    p.append("")


# ── Section 4: Strategy Performance ──────────────────

def _compact_metrics(bt: dict) -> str:
    if not bt:
        return "_無回測資料_"
    m = bt["metrics"]
    open_n = sum(1 for t in bt.get("trades", []) if t.get("exit_reason") == "持倉中")
    pf = f'{m["profit_factor"]:.2f}' if m["profit_factor"] != float("inf") else "∞"

    out = []
    out.append("| 指標 | 數值 |")
    out.append("|------|------|")
    out.append(f'| 交易數 | {m["total_trades"]} 平倉 + {open_n} 持倉 |')
    out.append(f'| 勝率 | **{m["win_rate"]}%** |')
    out.append(f'| 平均損益 | {m["avg_pnl"]:+.2f}% |')
    out.append(f'| PF | **{pf}** |')
    out.append(f'| 累計報酬 | **{m["total_return_pct"]:+.1f}%** |')
    out.append(f'| 平均持有 | {m["avg_hold_days"]}d |')
    out.append(f'| 最大連敗 | {m["max_consec_losses"]} |')

    if m.get("by_reason"):
        out.append("")
        out.append("| 出場原因 | 筆數 | 平均損益 |")
        out.append("|----------|------|----------|")
        for reason in ("達標", "停損", "到期", "早期出場"):
            if reason in m["by_reason"]:
                r = m["by_reason"][reason]
                out.append(f'| {reason} | {r["count"]} | {r["avg_pnl"]:+.2f}% |')

    return "\n".join(out)


def _sec_performance(p: list[str], bt_mom, bt_man, bt_ofc) -> None:
    p.append("## 4. 策略績效儀表板")
    p.append("")
    p.append("> 2 年歷史回測，最多同時持有 3 檔。回測驗證策略有效性。")
    p.append("")

    for bt, title, desc in [
        (bt_ofc, "U 型反轉三檔方案", "SL-10% · T+25% · 5★ · 40d · max 3 positions · pos 33%"),
    ]:
        if not bt:
            continue
        p.append(f"<details>")
        p.append(f"<summary><b>{title}</b> — {desc}</summary>")
        p.append("")
        p.append(_compact_metrics(bt))
        p.append("")

        # Top 10 + bottom 5 open positions
        holding = [t for t in bt.get("trades", []) if t.get("exit_reason") == "持倉中"]
        if holding:
            holding.sort(key=lambda t: t.get("pnl_pct", 0), reverse=True)
            total = len(holding)
            show = holding[:10] + (holding[-5:] if total > 15 else [])
            p.append(f"**持倉中 ({total} 筆，顯示 Top 10 + Bottom 5)：**")
            p.append("")
            p.append("| 代號 | 名稱 | 進場日 | 進場價 | 現價 | 損益% | 天數 |")
            p.append("|------|------|--------|--------|------|-------|------|")
            shown = 0
            for t in holding[:10]:
                pnl = t.get("pnl_pct", 0)
                p.append(f'| `{t["code"]}` | {t["name"]} | {t["entry_date"]} | {t["entry_price"]:.2f} | {t.get("exit_price",0):.2f} | {pnl:+.2f}% | {t.get("holding_days",0)}d |')
                shown += 1
            if total > 15:
                p.append(f"| ... | *另 {total - 15} 筆* | | | | | |")
                for t in holding[-5:]:
                    pnl = t.get("pnl_pct", 0)
                    p.append(f'| `{t["code"]}` | {t["name"]} | {t["entry_date"]} | {t["entry_price"]:.2f} | {t.get("exit_price",0):.2f} | {pnl:+.2f}% | {t.get("holding_days",0)}d |')
            p.append("")

        # Recent 10 closed
        closed = [t for t in bt.get("trades", []) if t.get("exit_reason") != "持倉中"]
        recent = closed[-10:]
        if recent:
            p.append(f"**近期平倉 (最近 {len(recent)} 筆 / 共 {len(closed)} 筆)：**")
            p.append("")
            p.append("| 代號 | 名稱 | 進場 | 出場 | 損益% | 天數 | 原因 |")
            p.append("|------|------|------|------|-------|------|------|")
            for t in recent:
                pnl = t.get("pnl_pct", 0)
                p.append(
                    f'| `{t["code"]}` | {t["name"]} | '
                    f'{t["entry_date"]} | {t.get("exit_date","")} | '
                    f'{pnl:+.2f}% | {t.get("holding_days",0)}d | {t.get("exit_reason","")} |'
                )
            p.append("")

        p.append("</details>")
        p.append("")

    p.append("---")
    p.append("")


# ── Section 5: Full Trade Logs ───────────────────────

def _sec_trade_logs(p: list[str], bt_mom, bt_man, bt_ofc) -> None:
    p.append("## 5. 完整交易明細")
    p.append("")

    for bt, label in [(bt_mom, "動能方案"), (bt_man, "手動精選"), (bt_ofc, "上班族三檔")]:
        if not bt or not bt.get("trades"):
            continue
        holding = [t for t in bt["trades"] if t.get("exit_reason") == "持倉中"]
        closed = [t for t in bt["trades"] if t.get("exit_reason") != "持倉中"]

        p.append(f"<details>")
        p.append(f"<summary>{label}：{len(holding)} 筆持倉 + {len(closed)} 筆平倉</summary>")
        p.append("")

        if holding:
            p.append(f"#### 持倉中 ({len(holding)} 筆)")
            p.append("")
            p.append("| 代號 | 名稱 | 星等 | 進場日 | 進場價 | 現價 | 損益% | 天數 |")
            p.append("|------|------|------|--------|--------|------|-------|------|")
            for t in holding:
                pnl = t.get("pnl_pct", 0)
                p.append(f'| `{t["code"]}` | {t["name"]} | {"★"*t.get("signal_stars",0)} | {t["entry_date"]} | {t["entry_price"]:.2f} | {t.get("exit_price",0):.2f} | {pnl:+.2f}% | {t.get("holding_days",0)}d |')
            p.append("")

        recent = closed[-30:]
        if recent:
            p.append(f"#### 近期平倉 ({len(recent)} / {len(closed)} 筆)")
            p.append("")
            p.append("| 代號 | 名稱 | 進場日 | 出場日 | 損益% | 天數 | 原因 |")
            p.append("|------|------|--------|--------|-------|------|------|")
            for t in recent:
                pnl = t.get("pnl_pct", 0)
                p.append(f'| `{t["code"]}` | {t["name"]} | {t["entry_date"]} | {t.get("exit_date","")} | {pnl:+.2f}% | {t.get("holding_days",0)}d | {t.get("exit_reason","")} |')
            p.append("")

        p.append("</details>")
        p.append("")

    p.append("---")
    p.append("")


# ── Main generator ─────────────────────────────────────

def generate(date_str: str) -> Path:
    signals_file = DATA_DIR / "signals_latest.json"
    if not signals_file.exists():
        raise FileNotFoundError(f"{signals_file} not found.")
    signals = json.loads(signals_file.read_text(encoding="utf-8"))
    results = signals["results"]
    total_scanned = signals["total_scanned"]

    fundamentals = _read_md("fundamentals")
    industry     = _read_md("industry")
    strategy     = _read_md("strategy")
    trades_md    = _read_md("trades")
    verification = _read_md("verification")

    bt_ofc = _load_bt("office")

    p: list[str] = []

    # Title
    p.append(f"# CTA Daily Report — {date_str}")
    p.append("")
    p.append("> 台股前 1000 大 · U 型反轉 · 精選三檔 · max 3 positions · 6-Agent AI")
    p.append(">")
    p.append("> [GitHub](https://github.com/mark00lui/Stock_U_turn) · [Dashboard](https://mark00lui.github.io/Stock_U_turn/)")
    p.append("")

    # Navigator
    p.append("| Step | Section | 回答什麼？ |")
    p.append("|------|---------|-----------|")
    p.append("| 1 | 訊號掃描 | 系統偵測到哪些反轉？ |")
    p.append("| 2 | 三維驗證 | 基本面和行業支持嗎？ |")
    p.append("| 3 | 最終推薦 | 通過驗證的 Top picks + 明日操作 |")
    p.append("| 4 | 策略績效 | 回測證明策略有效嗎？ |")
    p.append("| 5 | 交易明細 | 完整持倉 + 平倉紀錄 |")
    p.append("")
    p.append("---")
    p.append("")

    # Sections
    _sec_signal_scan(p, results, total_scanned)
    _sec_validation(p, fundamentals, industry)
    _sec_final_picks(p, strategy, trades_md, bt_ofc, results)
    _sec_performance(p, None, None, bt_ofc)

    # Quant verification
    if verification:
        p.append("## 4b. 量化驗證")
        p.append("")
        p.append("> 統計檢定驗證回測結果是否具顯著性（非隨機運氣）")
        p.append("")
        p.append(_strip_agent_heading(verification))
        p.append("")
        p.append("---")
        p.append("")

    _sec_trade_logs(p, None, None, bt_ofc)

    # Footer
    p.append("## 免責聲明")
    p.append("")
    p.append("本報告由 AI 自動生成，僅供研究參考，**不構成任何投資建議**。")
    p.append("")
    p.append(f"*Generated `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}` · [所有報告](./README.md)*")
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
    from update_index import main as refresh
    refresh()


if __name__ == "__main__":
    main()
