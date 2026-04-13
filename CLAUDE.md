# Stock U-turn — CTA Trading Signal Dashboard

## Project Overview
CTA (Commodity Trading Advisor) style daily dashboard for Taiwan top-1000 stocks.
RSI/MACD bottom-reversal Call signals + multi-agent AI analysis.

## Quick Start

### Tech-only (no AI, instant)
```bash
python main.py              # HTML report with RSI/MACD signals
```

### Full 6-Agent Analysis (recommended)
Tell Claude Code:
> 跑CTA

Or invoke the orchestrator agent directly. This runs the complete pipeline:
1. Data fetch + RSI/MACD signals (Python)
2. Revenue Analyst + Industry Analyst (LLM, parallel)
3. Chief Strategist synthesis (LLM)
4. Trader trade plans (LLM)
5. Enhanced HTML report generation

Output: `output/cta_agent_report_YYYY-MM-DD.html`

### Daily Auto-Trigger
Tell Claude Code:
> 設定每日CTA排程

This creates a CronCreate job that runs the full pipeline **every weekday at 14:03** (30 min after Taiwan market close at 13:30). The cron job lives in the current session — re-create it when you restart Claude Code.

## 6-Agent System

| Agent | Type | Role | Output |
|-------|------|------|--------|
| Data RD | Python | TWSE/TPEx data, yfinance prices | `data/signals_latest.json` |
| Signal Analyst | Python | RSI/MACD indicators, reversal detection | (in JSON above) |
| Revenue Analyst | LLM | Monthly revenue & earnings analysis | `data/agent_outputs/fundamentals.md` |
| Industry Analyst | LLM | Sector trends, cycle positioning | `data/agent_outputs/industry.md` |
| Chief Strategist | LLM | 3D synthesis (tech 40% + fundamental 30% + industry 30%) | `data/agent_outputs/strategy.md` |
| Trader | LLM | Trade plans, position sizing, risk control | `data/agent_outputs/trades.md` |

## Key Files
```
main.py                     — data pipeline + --export JSON
generate_report_cli.py      — assemble enhanced report from agent outputs
config.py                   — all parameters (RSI/MACD/thresholds)
report.py                   — HTML report templates (basic + enhanced)
fetch_universe.py           — TWSE/TPEx stock list API
fetch_prices.py             — yfinance batch download + cache
indicators.py               — RSI & MACD calculation
signals.py                  — reversal signal detection
.claude/agents/cta-daily.md — orchestrator agent (runs full pipeline)
.claude/agents/*.md         — 6 specialist agent definitions
```

## Tech Stack
- Python 3.x, pandas, numpy, yfinance, requests
- Claude Code CLI (Agent tool for LLM agents — no API key needed)
- Self-contained static HTML reports
- Windows 11, UTF-8, Git Bash
