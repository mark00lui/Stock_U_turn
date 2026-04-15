"""Regenerate output/index.html listing all HTML reports.

Call this after generating a new report so GitHub Pages landing page stays fresh.

Usage:
    python update_index.py
"""
from __future__ import annotations

import re
import sys
import io
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from config import OUTPUT_DIR


_PATTERNS = {
    "daily_md": re.compile(r"cta_daily_(\d{4}-\d{2}-\d{2})\.md"),
    "agent":    re.compile(r"cta_agent_report_(\d{4}-\d{2}-\d{2})\.html"),
    "tech":     re.compile(r"cta_report_(\d{4}-\d{2}-\d{2})\.html"),
    "backtest": re.compile(r"cta_backtest_(\d{4}-\d{2}-\d{2})\.html"),
}


def _collect() -> dict[str, list[tuple[str, str]]]:
    """Return {category: [(date, filename), ...]} sorted desc by date."""
    out = {k: [] for k in _PATTERNS}
    for f in list(OUTPUT_DIR.glob("*.html")) + list(OUTPUT_DIR.glob("*.md")):
        if f.name in ("index.html", "README.md"):
            continue
        for cat, pat in _PATTERNS.items():
            m = pat.match(f.name)
            if m:
                out[cat].append((m.group(1), f.name))
                break
    for cat in out:
        out[cat].sort(reverse=True)
    return out


def _card(date: str, filename: str, cat: str) -> str:
    tag_class = {"agent": "agent", "backtest": "backtest", "tech": ""}[cat]
    tag_label = {"agent": "Agent", "backtest": "Backtest", "tech": "Tech"}[cat]
    return (
        f'  <a class="card" href="{filename}">'
        f'<div class="card-title">{date}'
        f'<span class="card-type {tag_class}">{tag_label}</span></div>'
        f'<div class="card-date">&nbsp;</div>'
        f'</a>'
    )


def _section(title: str, subtitle: str, cards: list[str]) -> str:
    if not cards:
        return ""
    grid = "\n".join(cards)
    return (
        f'<section>\n<h2>{title} <span class="count">{subtitle}</span></h2>\n'
        f'<div class="grid">\n{grid}\n</div>\n</section>\n'
    )


def _md_readme(reports: dict[str, list[tuple[str, str]]]) -> str:
    """Build output/README.md — GitHub auto-renders this when browsing the folder."""
    lines = [
        "# 📊 CTA Daily Reports",
        "",
        "台股前 1000 大 · RSI / MACD 抄底反轉訊號 · 6-Agent AI 每日分析",
        "",
        "> 🌐 [Live Dashboard](https://mark00lui.github.io/Stock_U_turn/) · "
        "📁 [Source Code](https://github.com/mark00lui/Stock_U_turn) · "
        "🤖 Powered by Claude Code",
        "",
        "---",
        "",
        "## 📝 每日綜合報告 (Markdown)",
        "",
        "一份涵蓋技術面訊號、基本面、行業分析、策略整合、操作股單、回測驗證的完整報告。",
        "",
    ]

    if reports["daily_md"]:
        for d, fn in reports["daily_md"]:
            lines.append(f"- 📊 [`{d}`](./{fn})")
        lines.append("")
    else:
        lines.append("_尚無每日 Markdown 報告_")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 🗂️ HTML 互動式報告")
    lines.append("")

    if reports["agent"]:
        lines.append("### 6-Agent 整合分析")
        for d, fn in reports["agent"]:
            lines.append(f"- 🤖 [`{d}`](./{fn})")
        lines.append("")

    if reports["tech"]:
        lines.append("### 純技術面掃描")
        for d, fn in reports["tech"]:
            lines.append(f"- ⚡ [`{d}`](./{fn})")
        lines.append("")

    if reports["backtest"]:
        lines.append("### 策略回測報告")
        for d, fn in reports["backtest"]:
            lines.append(f"- 📈 [`{d}`](./{fn})")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## ⚙️ 策略規則",
        "",
        "| 參數 | 數值 |",
        "|------|------|",
        "| 停損 | `-8%` |",
        "| 目標 | `+10%` |",
        "| 最長持有 | `15 交易日` |",
        "| 早期出場 | `10 日內漲幅 < +3%` |",
        "| 單筆倉位 | `5%` of portfolio |",
        "| 最低訊號強度 | `★3` |",
        "",
        "## 🤖 6-Agent 流程",
        "",
        "```",
        "Data RD (Python)",
        "    └─> Signal Analyst (Python)",
        "            ├─> Revenue Analyst (LLM)  ─┐",
        "            └─> Industry Analyst (LLM) ─┤",
        "                                        ├─> Chief Strategist (LLM)",
        "                                        │       └─> Trader (LLM)",
        "                                        │               └─> Backtest Engine",
        "                                        │                       └─> Combined MD Report",
        "                                        │                               └─> GitHub Publish",
        "```",
        "",
        "## ⚠️ 免責聲明",
        "",
        "本報告由 AI 自動生成，僅供研究參考，**不構成任何投資建議**。",
        "過去回測績效不代表未來表現，投資前請獨立判斷並自行承擔風險。",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    reports = _collect()

    # ── HTML index (GitHub Pages) ─────────────────────
    agent_cards    = [_card(d, f, "agent")    for d, f in reports["agent"]]
    tech_cards     = [_card(d, f, "tech")     for d, f in reports["tech"]]
    backtest_cards = [_card(d, f, "backtest") for d, f in reports["backtest"]]

    # MD reports linked via HTML too (new section)
    md_cards = [
        f'  <a class="card" href="{fn}">'
        f'<div class="card-title">{d}'
        f'<span class="card-type md">Daily MD</span></div>'
        f'<div class="card-date">&nbsp;</div></a>'
        for d, fn in reports["daily_md"]
    ]

    sections = (
        _section("📝 每日綜合報告 (Markdown)", "基本面 + 行業 + 策略 + 交易 + 回測", md_cards)
        + _section("🤖 6-Agent HTML 報告", "互動式分析儀表板", agent_cards)
        + _section("⚡ 純技術面快速報告", "RSI / MACD 訊號掃描", tech_cards)
        + _section("📈 策略回測報告", "歷史數據驗證", backtest_cards)
    )

    html = _TMPL.format(sections=sections)
    idx_html = OUTPUT_DIR / "index.html"
    idx_html.write_text(html, encoding="utf-8")

    # ── README.md (GitHub browse view) ────────────────
    readme = OUTPUT_DIR / "README.md"
    readme.write_text(_md_readme(reports), encoding="utf-8")

    total = sum(len(v) for v in reports.values())
    print(f"Archive refreshed: {idx_html.name} + {readme.name}  ({total} reports)")


_TMPL = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stock U-turn — CTA Dashboard Archive</title>
<style>
:root{{--bg:#0d1117;--sf:#161b22;--sf2:#21262d;--bd:#30363d;
  --t1:#e6edf3;--t2:#8b949e;--gr:#3fb950;--bl:#58a6ff;--yw:#d29922;--rd:#f85149}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--t1);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  font-size:14px;line-height:1.6;min-height:100vh}}
.wrap{{max-width:900px;margin:0 auto;padding:40px 24px}}
header{{text-align:center;margin-bottom:40px}}
h1{{font-size:32px;font-weight:700;
  background:linear-gradient(135deg,var(--gr),var(--bl));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:8px}}
.sub{{color:var(--t2);font-size:15px}}
.tag{{display:inline-block;background:var(--sf2);border:1px solid var(--bd);
  color:var(--t2);font-size:12px;padding:3px 10px;border-radius:12px;margin:0 4px}}
.tag.new{{border-color:var(--gr);color:var(--gr)}}
section{{margin-bottom:32px}}
h2{{font-size:18px;color:var(--t1);padding-bottom:10px;border-bottom:1px solid var(--bd);margin-bottom:16px}}
h2 .count{{color:var(--t2);font-size:13px;font-weight:400;margin-left:8px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
@media(max-width:640px){{.grid{{grid-template-columns:1fr}}}}
a.card{{display:block;background:var(--sf);border:1px solid var(--bd);border-radius:12px;
  padding:16px 20px;text-decoration:none;color:var(--t1);transition:all .15s}}
a.card:hover{{border-color:var(--bl);background:var(--sf2);transform:translateY(-1px)}}
.card-title{{font-size:15px;font-weight:600}}
.card-date{{color:var(--t2);font-size:12px}}
.card-type{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:8px;
  background:rgba(88,166,255,.15);color:var(--bl);margin-left:8px;vertical-align:middle}}
.card-type.agent{{background:rgba(63,185,80,.15);color:var(--gr)}}
.card-type.backtest{{background:rgba(210,153,34,.15);color:var(--yw)}}
.card-type.md{{background:rgba(248,81,73,.15);color:var(--rd)}}
.info{{background:var(--sf);border:1px solid var(--bd);border-radius:12px;padding:20px;
  margin-top:16px;color:var(--t2);font-size:13px;line-height:1.7}}
.info strong{{color:var(--t1)}}
.info code{{background:var(--sf2);padding:2px 8px;border-radius:4px;font-size:12px;color:var(--gr)}}
footer{{text-align:center;color:var(--t2);font-size:12px;margin-top:40px;padding-top:16px;border-top:1px solid var(--bd)}}
footer a{{color:var(--bl);text-decoration:none}}
</style>
</head>
<body>
<div class="wrap">

<header>
  <h1>CTA Dashboard Archive</h1>
  <p class="sub">台股 RSI / MACD 抄底反轉訊號 &middot; 多 Agent AI 分析</p>
  <div style="margin-top:10px">
    <span class="tag">台股前 1000 大</span>
    <span class="tag">RSI(14) / MACD(12,26,9)</span>
    <span class="tag new">6-Agent System</span>
  </div>
</header>

{sections}

<section>
<div class="info">
  <strong>自動更新機制</strong> · 本 Dashboard 由 Claude Code CLI 每個交易日 14:03 自動觸發，
  經過 6 Agent Pipeline 產出。<br><br>
  <strong>報告結構</strong><br>
  &nbsp;&middot; <strong>Agent 報告</strong> — 6 代理 AI 整合分析（基本面 + 行業 + 策略 + 交易計畫）<br>
  &nbsp;&middot; <strong>Tech 報告</strong> — 純 RSI/MACD 訊號表，不含 AI 分析<br>
  &nbsp;&middot; <strong>Backtest 報告</strong> — 策略歷史回測結果<br>
  <br>
  <strong>策略規則</strong> · 停損 <code>-8%</code> · 目標 <code>+10%</code> · 最長持有 <code>15 日</code>
  · 早期出場 <code>10日內漲幅&lt;3%</code> · 單筆倉位 <code>5%</code>
</div>
</section>

<footer>Generated by Claude Code &middot; Stock U-turn CTA Dashboard</footer>

</div>
</body>
</html>"""


if __name__ == "__main__":
    main()
