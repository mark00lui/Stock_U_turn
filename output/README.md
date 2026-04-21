# 📊 CTA Daily Reports

台股前 1000 大 · RSI / MACD 抄底反轉訊號 · 6-Agent AI 每日分析

> 🌐 [Live Dashboard](https://mark00lui.github.io/Stock_U_turn/) · 📁 [Source Code](https://github.com/mark00lui/Stock_U_turn) · 🤖 Powered by Claude Code

---

## 📝 每日綜合報告 (Markdown)

一份涵蓋技術面訊號、基本面、行業分析、策略整合、操作股單、回測驗證的完整報告。

- 📊 [`2026-04-21`](./cta_daily_2026-04-21.md)
- 📊 [`2026-04-20`](./cta_daily_2026-04-20.md)
- 📊 [`2026-04-17`](./cta_daily_2026-04-17.md)
- 📊 [`2026-04-16`](./cta_daily_2026-04-16.md)
- 📊 [`2026-04-15`](./cta_daily_2026-04-15.md)

---

## 🗂️ HTML 互動式報告

### 6-Agent 整合分析
- 🤖 [`2026-04-15`](./cta_agent_report_2026-04-15.html)
- 🤖 [`2026-04-14`](./cta_agent_report_2026-04-14.html)
- 🤖 [`2026-04-13`](./cta_agent_report_2026-04-13.html)

### 純技術面掃描
- ⚡ [`2026-04-21`](./cta_report_2026-04-21.html)
- ⚡ [`2026-04-20`](./cta_report_2026-04-20.html)
- ⚡ [`2026-04-17`](./cta_report_2026-04-17.html)
- ⚡ [`2026-04-16`](./cta_report_2026-04-16.html)
- ⚡ [`2026-04-15`](./cta_report_2026-04-15.html)
- ⚡ [`2026-04-14`](./cta_report_2026-04-14.html)
- ⚡ [`2026-04-13`](./cta_report_2026-04-13.html)

### 策略回測報告
- 📈 [`2026-04-21`](./cta_backtest_2026-04-21.html)
- 📈 [`2026-04-20`](./cta_backtest_2026-04-20.html)
- 📈 [`2026-04-17`](./cta_backtest_2026-04-17.html)
- 📈 [`2026-04-16`](./cta_backtest_2026-04-16.html)
- 📈 [`2026-04-15`](./cta_backtest_2026-04-15.html)
- 📈 [`2026-04-13`](./cta_backtest_2026-04-13.html)

---

## ⚙️ 策略規則

| 參數 | 數值 |
|------|------|
| 停損 | `-8%` |
| 目標 | `+10%` |
| 最長持有 | `15 交易日` |
| 早期出場 | `10 日內漲幅 < +3%` |
| 單筆倉位 | `5%` of portfolio |
| 最低訊號強度 | `★3` |

## 🤖 6-Agent 流程

```
Data RD (Python)
    └─> Signal Analyst (Python)
            ├─> Revenue Analyst (LLM)  ─┐
            └─> Industry Analyst (LLM) ─┤
                                        ├─> Chief Strategist (LLM)
                                        │       └─> Trader (LLM)
                                        │               └─> Backtest Engine
                                        │                       └─> Combined MD Report
                                        │                               └─> GitHub Publish
```

## ⚠️ 免責聲明

本報告由 AI 自動生成，僅供研究參考，**不構成任何投資建議**。
過去回測績效不代表未來表現，投資前請獨立判斷並自行承擔風險。
