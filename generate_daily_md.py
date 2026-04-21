"""Generate CTA daily Markdown report — 3-Strategy Architecture.

Sections:
  1. 三策略掃描 — each strategy's candidates today
  2. 精選三檔 — why these 3 per strategy (current holdings)
  3. 明日計畫 — buy/sell actions per strategy
  4. 策略績效 — backtest dashboards
  5. 量化驗證 — statistical tests
  6. 交易明細 — collapsed appendix

Usage:
    python generate_daily_md.py
    python generate_daily_md.py 2026-04-20
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

def _load_signals(label: str) -> list[dict]:
    name = "signals_latest.json" if label == "reversal" else f"signals_{label}.json"
    p = DATA_DIR / name
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("results", [])

def _strip_heading(md: str) -> str:
    lines = md.split("\n")
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    text = "\n".join(lines)
    text = re.sub(r"^## ", "#### ", text, flags=re.MULTILINE)
    text = re.sub(r"^### ", "##### ", text, flags=re.MULTILINE)
    return text.strip()


# ── Strategy metadata ─────────────────────────────────

STRATEGIES = [
    {
        "key": "reversal", "label": "U 型反轉",
        "icon": "🔄", "style": "逆勢抄底",
        "desc": "RSI 超賣反彈 + MACD 金叉 · SL-10% T+25% · 5★ · 40d",
    },
    {
        "key": "momentum", "label": "動能突破",
        "icon": "🚀", "style": "順勢追漲",
        "desc": "突破 20MA + 量增 + 趨勢確認 · SL-10% T+25% · 5★ · 30d",
    },
    {
        "key": "breakout", "label": "創新高突破",
        "icon": "📈", "style": "快進快出",
        "desc": "60 日新高 + 量爆 · SL-5% T+15% · 4★ · 10d",
    },
]


# ── Section 1: Four Strategy Scan ────────────────────

def _sec_scan(p: list[str], all_signals: dict[str, list], total_scanned: int) -> None:
    p.append("## 1. 三策略掃描：今日候選股")
    p.append("")
    p.append(f"> 掃描 {total_scanned} 檔，三套策略各自偵測候選（min-stars=4）。每策略最多持 3 檔。")
    p.append("")

    # Summary table
    p.append("| 策略 | 風格 | 候選數 | 4★+ | 5★ | 今日 Top 3 候選 |")
    p.append("|------|------|--------|-----|----|--------------------|")
    for s in STRATEGIES:
        sigs = all_signals.get(s["key"], [])
        s4 = sum(1 for r in sigs if r.get("stars", 0) >= 4)
        s5 = sum(1 for r in sigs if r.get("stars", 0) >= 5)
        top3 = [f'{r["code"]}{r["name"]}' for r in sigs[:3]]
        top3_str = " / ".join(top3) if top3 else "—"
        p.append(f'| {s["icon"]} {s["label"]} | {s["style"]} | {len(sigs)} | {s4} | {s5} | {top3_str} |')
    p.append("")

    # Detail per strategy
    for s in STRATEGIES:
        sigs = all_signals.get(s["key"], [])
        top = sigs[:8]
        if not top:
            continue
        p.append(f'### {s["icon"]} {s["label"]} 候選 ({len(sigs)} 檔)')
        p.append("")
        p.append(f"> {s['desc']}")
        p.append("")
        p.append("| # | 代號 | 名稱 | 收盤 | 漲跌% | RSI | 星等 | 訊號 |")
        p.append("|---|------|------|------|-------|-----|------|------|")
        for i, r in enumerate(top, 1):
            chg = r.get("pct_change", 0)
            chg_s = f"+{chg:.1f}%" if chg >= 0 else f"{chg:.1f}%"
            stars = "★" * r.get("stars", 0)
            descs = " / ".join(r.get("descriptions", []))
            p.append(f'| {i} | `{r["code"]}` | {r["name"]} | {r["close"]:.1f} | {chg_s} | {r.get("rsi", 0):.1f} | {stars} | {descs} |')
        p.append("")

    p.append("---")
    p.append("")


# ── Section 2: Current Holdings ──────────────────────

def _sec_holdings(p: list[str], all_bt: dict[str, dict | None]) -> None:
    p.append("## 2. 精選三檔：各策略當前持倉")
    p.append("")
    p.append("> 每策略最多同時持有 3 檔。以下為回測模擬的當前持倉狀態。")
    p.append("")

    for s in STRATEGIES:
        bt = all_bt.get(s["key"])
        if not bt or not bt.get("trades"):
            continue

        holding = [t for t in bt["trades"] if t.get("exit_reason") == "持倉中"]
        strat = bt.get("strategy", {})

        p.append(f'### {s["icon"]} {s["label"]}：{len(holding)} 檔持倉中')
        p.append("")

        if not holding:
            p.append("_目前無持倉_")
            p.append("")
            continue

        holding.sort(key=lambda t: t.get("pnl_pct", 0), reverse=True)

        p.append("| 代號 | 名稱 | 進場日 | 進場價 | 現價 | 損益% | 天數 | 為什麼選它 |")
        p.append("|------|------|--------|--------|------|-------|------|-----------|")
        for t in holding:
            pnl = t.get("pnl_pct", 0)
            pnl_s = f"+{pnl:.2f}%" if pnl >= 0 else f"{pnl:.2f}%"
            stars = "★" * t.get("signal_stars", 0)
            descs = " / ".join(t.get("signal_descs", []))
            reason = f'{stars} {descs}' if descs else stars
            p.append(
                f'| `{t["code"]}` | {t["name"]} | {t["entry_date"]} | '
                f'{t["entry_price"]:.2f} | {t.get("exit_price", 0):.2f} | '
                f'{pnl_s} | {t.get("holding_days", 0)}d | {reason} |')
        p.append("")

    p.append("---")
    p.append("")


# ── Section 3: Tomorrow's Plan ───────────────────────

def _sec_tomorrow(p: list[str], all_bt: dict[str, dict | None],
                  all_signals: dict[str, list]) -> None:
    p.append("## 3. 明日操作計畫")
    p.append("")
    p.append("> 收盤後分析 → 次日 08:55 掛限價單 → 盤中不盯盤")
    p.append("")

    for s in STRATEGIES:
        bt = all_bt.get(s["key"])
        sigs = all_signals.get(s["key"], [])
        if not bt or not bt.get("trades"):
            continue

        strat = bt.get("strategy", {})
        min_stars = strat.get("min_stars", 4)
        max_hold = strat.get("max_hold_days", 30)
        sl = strat.get("stop_loss_pct", -10)
        tgt = strat.get("target_pct", 25)

        holding = [t for t in bt["trades"] if t.get("exit_reason") == "持倉中"]
        held_codes = {t["code"] for t in holding}

        # New buy candidates
        candidates = [r for r in sigs
                      if r.get("stars", 0) >= min_stars and r["code"] not in held_codes][:5]

        # Exit alerts
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

        slots_free = 3 - len(holding)

        p.append(f'### {s["icon"]} {s["label"]}')
        p.append("")
        p.append(f'持倉 {len(holding)}/3 · 空位 {slots_free} · 停損 {sl}% · 目標 +{tgt}% · 持有 {max_hold}d')
        p.append("")

        # Buy
        if slots_free > 0 and candidates:
            p.append(f"**買入候選** (空位 {slots_free} 檔)：")
            p.append("")
            p.append("| 代號 | 名稱 | 星等 | 收盤 | 訊號 | 掛單價 | 停損 |")
            p.append("|------|------|------|------|------|--------|------|")
            for r in candidates[:slots_free + 2]:  # show a few extra as backup
                stars = "★" * r.get("stars", 0)
                descs = " / ".join(r.get("descriptions", []))[:30]
                close = r["close"]
                stop = close * (1 + sl / 100)
                p.append(
                    f'| `{r["code"]}` | {r["name"]} | {stars} | '
                    f'{close:.1f} | {descs} | {close:.1f} | {stop:.1f} |')
            p.append("")
        elif slots_free > 0:
            p.append(f"**買入候選**：今日無符合 {min_stars}★ 的新訊號。等待。")
            p.append("")
        else:
            p.append("**買入候選**：滿倉 3/3，暫不進場。")
            p.append("")

        # Exit
        if approaching:
            p.append(f"**出場警示** ({len(approaching)} 筆)：")
            p.append("")
            p.append("| 代號 | 名稱 | 損益% | 天數 | 警示 |")
            p.append("|------|------|-------|------|------|")
            for t, reason in approaching[:8]:
                pnl = t.get("pnl_pct", 0)
                pnl_s = f"+{pnl:.2f}%" if pnl >= 0 else f"{pnl:.2f}%"
                p.append(f'| `{t["code"]}` | {t["name"]} | {pnl_s} | {t.get("holding_days", 0)}d | {reason} |')
            p.append("")
        else:
            p.append("**出場警示**：無持倉接近出場條件。")
            p.append("")

    p.append("---")
    p.append("")


# ── Section 4: Performance Dashboard ─────────────────

def _compact_metrics(bt: dict) -> str:
    if not bt:
        return "_無回測資料_"
    m = bt["metrics"]
    open_n = sum(1 for t in bt.get("trades", []) if t.get("exit_reason") == "持倉中")
    pf = f'{m["profit_factor"]:.2f}' if m["profit_factor"] != float("inf") else "∞"

    out = []
    out.append("| 指標 | 數值 |")
    out.append("|------|------|")
    out.append(f'| 交易 | {m["total_trades"]} 平倉 + {open_n} 持倉 |')
    out.append(f'| 勝率 | **{m["win_rate"]}%** |')
    out.append(f'| 平均損益 | {m["avg_pnl"]:+.2f}% |')
    out.append(f'| PF | **{pf}** |')
    out.append(f'| 報酬 | **{m["total_return_pct"]:+.1f}%** |')
    out.append(f'| 持有 | {m["avg_hold_days"]}d |')
    out.append(f'| 連敗 | {m["max_consec_losses"]} |')
    if m.get("by_reason"):
        out.append("")
        out.append("| 出場 | 筆數 | avg |")
        out.append("|------|------|-----|")
        for reason in ("達標", "停損", "到期", "早期出場"):
            if reason in m["by_reason"]:
                r = m["by_reason"][reason]
                out.append(f'| {reason} | {r["count"]} | {r["avg_pnl"]:+.2f}% |')
    return "\n".join(out)


def _sec_performance(p: list[str], all_bt: dict[str, dict | None]) -> None:
    p.append("## 4. 策略績效儀表板")
    p.append("")
    p.append("> 5 年歷史回測，每策略 max 3 檔同時持倉。")
    p.append("")

    # Summary comparison
    p.append("| 策略 | 交易數 | 勝率 | PF | 5yr 報酬 | 統計驗證 |")
    p.append("|------|--------|------|----|----------|----------|")
    for s in STRATEGIES:
        bt = all_bt.get(s["key"])
        if not bt:
            p.append(f'| {s["icon"]} {s["label"]} | — | — | — | — | — |')
            continue
        m = bt["metrics"]
        pf = f'{m["profit_factor"]:.2f}' if m["profit_factor"] != float("inf") else "∞"
        p.append(f'| {s["icon"]} {s["label"]} | {m["total_trades"]} | {m["win_rate"]}% | {pf} | {m["total_return_pct"]:+.1f}% | — |')
    p.append("")

    for s in STRATEGIES:
        bt = all_bt.get(s["key"])
        if not bt:
            continue
        p.append(f'<details>')
        p.append(f'<summary><b>{s["icon"]} {s["label"]}</b> — {s["desc"]}</summary>')
        p.append("")
        p.append(_compact_metrics(bt))
        p.append("")

        # Recent 10 closed
        closed = [t for t in bt.get("trades", []) if t.get("exit_reason") != "持倉中"]
        recent = closed[-10:]
        if recent:
            p.append(f"**近期平倉 ({len(recent)}/{len(closed)})：**")
            p.append("")
            p.append("| 代號 | 名稱 | 進場 | 出場 | 損益% | 天數 | 原因 |")
            p.append("|------|------|------|------|-------|------|------|")
            for t in recent:
                pnl = t.get("pnl_pct", 0)
                p.append(
                    f'| `{t["code"]}` | {t["name"]} | {t["entry_date"]} | '
                    f'{t.get("exit_date", "")} | {pnl:+.2f}% | '
                    f'{t.get("holding_days", 0)}d | {t.get("exit_reason", "")} |')
            p.append("")

        p.append("</details>")
        p.append("")

    p.append("---")
    p.append("")


# ── Section 5: Quant Verification ────────────────────

def _sec_verification(p: list[str], verification: str) -> None:
    if not verification:
        return
    p.append("## 5. 量化驗證")
    p.append("")
    p.append("> 統計檢定：回測結果是否具顯著性（非隨機運氣）")
    p.append("")
    p.append(_strip_heading(verification))
    p.append("")
    p.append("---")
    p.append("")


# ── Section 6: Trade Logs ────────────────────────────

def _sec_trade_logs(p: list[str], all_bt: dict[str, dict | None]) -> None:
    p.append("## 6. 完整交易明細")
    p.append("")

    for s in STRATEGIES:
        bt = all_bt.get(s["key"])
        if not bt or not bt.get("trades"):
            continue
        holding = [t for t in bt["trades"] if t.get("exit_reason") == "持倉中"]
        closed = [t for t in bt["trades"] if t.get("exit_reason") != "持倉中"]

        p.append(f"<details>")
        p.append(f'<summary>{s["icon"]} {s["label"]}：{len(holding)} 持倉 + {len(closed)} 平倉</summary>')
        p.append("")

        if holding:
            p.append(f"#### 持倉中 ({len(holding)})")
            p.append("")
            p.append("| 代號 | 名稱 | 星等 | 進場日 | 進場價 | 現價 | 損益% | 天數 |")
            p.append("|------|------|------|--------|--------|------|-------|------|")
            for t in holding:
                pnl = t.get("pnl_pct", 0)
                p.append(f'| `{t["code"]}` | {t["name"]} | {"★"*t.get("signal_stars",0)} | {t["entry_date"]} | {t["entry_price"]:.2f} | {t.get("exit_price",0):.2f} | {pnl:+.2f}% | {t.get("holding_days",0)}d |')
            p.append("")

        recent = closed[-30:]
        if recent:
            p.append(f"#### 近期平倉 ({len(recent)}/{len(closed)})")
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
    # Load all signals
    all_signals = {}
    total_scanned = 0
    for s in STRATEGIES:
        sigs = _load_signals(s["key"])
        all_signals[s["key"]] = sigs
    # Get total_scanned from reversal (primary)
    sig_file = DATA_DIR / "signals_latest.json"
    if sig_file.exists():
        total_scanned = json.loads(sig_file.read_text(encoding="utf-8")).get("total_scanned", 0)

    # Load all backtests
    all_bt = {s["key"]: _load_bt(s["key"]) for s in STRATEGIES}

    # Load agent outputs
    verification = _read_md("verification")

    # ── Compose ───────────────────────────────────────
    p: list[str] = []

    # Title
    p.append(f"# CTA Daily Report — {date_str}")
    p.append("")
    p.append("> 台股強勢股 (≥NT$50) · 三策略掃描 · min-stars=4 · 每策略精選 3 檔 · 收盤分析 → 次日掛單")
    p.append(">")
    p.append("> [GitHub](https://github.com/mark00lui/Stock_U_turn) · [Dashboard](https://mark00lui.github.io/Stock_U_turn/)")
    p.append("")

    # Navigator
    p.append("| Section | 內容 |")
    p.append("|---------|------|")
    p.append("| 1. 三策略掃描 | 各策略偵測到的候選股 |")
    p.append("| 2. 精選三檔 | 各策略當前持倉 + 選股理由 |")
    p.append("| 3. 明日計畫 | 買入候選 + 出場警示 |")
    p.append("| 4. 績效儀表板 | 5 年回測統計 |")
    p.append("| 5. 量化驗證 | 統計顯著性檢定 |")
    p.append("| 6. 交易明細 | 完整進出場紀錄 |")
    p.append("")
    p.append("---")
    p.append("")

    # Sections
    _sec_scan(p, all_signals, total_scanned)
    _sec_holdings(p, all_bt)
    _sec_tomorrow(p, all_bt, all_signals)
    _sec_performance(p, all_bt)
    _sec_verification(p, verification)
    _sec_trade_logs(p, all_bt)

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
