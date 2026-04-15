---
name: CTA Daily Analysis
description: End-to-end CTA 6-agent pipeline — data fetch, 4 LLM agents, enhanced HTML report
allowedTools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Agent
  - WebSearch
  - WebFetch
---

# CTA Daily Analysis Orchestrator

You are the orchestrator for the CTA (Commodity Trading Advisor) daily analysis pipeline for Taiwan top-1000 stocks.
Execute all steps in order. If a step fails, report the error and stop.

## Step 1: Data Pipeline

Run the Python data pipeline (fetches prices, computes RSI/MACD, detects reversal signals):

```bash
cd E:/github/Stock_U_turn && PYTHONIOENCODING=utf-8 python main.py --export
```

Verify that `data/signals_latest.json` was created. If the command fails, stop and report the error.

Also ensure the agent output directory exists:
```bash
mkdir -p E:/github/Stock_U_turn/data/agent_outputs
```

## Step 2: Read & Prepare Signal Data

Read `E:/github/Stock_U_turn/data/signals_latest.json`.

Extract the top signal stocks where `stars >= 3` (up to 50 stocks). Format them as a compact text summary:

```
代號 | 名稱 | 市場 | 收盤 | 漲跌% | RSI | MACD | 星等 | 訊號
```

Also group stocks by sector (inferred from name/code) for the Industry Analyst.

## Step 3: Parallel Analysis

Spawn TWO agents in parallel (both in the same message):

### 3a: Revenue Analyst
Use the Agent tool. In the prompt, include:
- The signal stock table from Step 2
- Instruct the agent to analyze each stock's monthly revenue trends, profitability, and financial health
- Instruct the agent to write its COMPLETE output in Traditional Chinese to: `E:/github/Stock_U_turn/data/agent_outputs/fundamentals.md`

### 3b: Industry Analyst
Use the Agent tool. In the prompt, include:
- The sector grouping from Step 2
- Instruct the agent to analyze sector trends, business cycle positioning, and risks
- Instruct the agent to write its COMPLETE output in Traditional Chinese to: `E:/github/Stock_U_turn/data/agent_outputs/industry.md`

Wait for both agents to complete before proceeding.

## Step 4: Chief Strategist

Read the outputs from Step 3:
- `E:/github/Stock_U_turn/data/agent_outputs/fundamentals.md`
- `E:/github/Stock_U_turn/data/agent_outputs/industry.md`

Use the Agent tool. In the prompt, include:
- The signal table from Step 2 (technical dimension)
- The fundamentals analysis (fundamental dimension)
- The industry analysis (industry dimension)
- Scoring formula: Technical 40% + Fundamental 30% + Industry 30%
- Instruct the agent to synthesize all three dimensions, produce Top 10-15 picks, market outlook, and risk warnings
- Instruct the agent to write its COMPLETE output in Traditional Chinese to: `E:/github/Stock_U_turn/data/agent_outputs/strategy.md`

## Step 5: Trader

Read the strategy output: `E:/github/Stock_U_turn/data/agent_outputs/strategy.md`

Use the Agent tool. In the prompt, include:
- The strategy and Top Picks from Step 4
- Risk control rules: single stock <= 10%, same sector <= 25%, total <= 70%, stop loss 5-8%
- Instruct the agent to generate trade plans with entry/stop-loss/target/position sizing for each pick
- Instruct the agent to write its COMPLETE output in Traditional Chinese to: `E:/github/Stock_U_turn/data/agent_outputs/trades.md`

## Step 6: Run Backtest with Current Data

Validate the strategy against the latest prices:

```bash
cd E:/github/Stock_U_turn && PYTHONIOENCODING=utf-8 python backtest.py --stop-loss -8 --target 10 --max-hold 15 --position 5 --early-exit-days 10 --early-exit-min 3
```

This produces `data/backtest_latest.json` (metrics snapshot) that feeds into the daily MD report.

## Step 7: Generate Combined Daily Markdown Report

Assemble the full report — analysis + trade list + backtest — into one GitHub-friendly `.md`:

```bash
cd E:/github/Stock_U_turn && PYTHONIOENCODING=utf-8 python generate_daily_md.py
```

Output: `output/cta_daily_YYYY-MM-DD.md` — this is the primary daily artifact.
The script also refreshes `output/README.md` (archive index) and `output/index.html` (GitHub Pages landing).

## Step 8: Auto-Publish to GitHub

Commit today's new reports and push so they appear publicly:

```bash
cd E:/github/Stock_U_turn && PYTHONIOENCODING=utf-8 python publish.py
```

Stages only `output/`, commits with `report: CTA daily YYYY-MM-DD`, pushes to `origin main`.
Skips gracefully if no changes. On push failure, commit is preserved locally — report the error but do NOT retry.

## Step 9: Summary

Report completion with:
- Date of analysis
- Number of stocks scanned + signal breakdown (Strong / Call / Watch)
- Top 3 picks with combined scores
- Backtest headline (win rate, profit factor)
- Direct link to today's MD report: `https://github.com/mark00lui/Stock_U_turn/blob/main/output/cta_daily_YYYY-MM-DD.md`
- GitHub Pages archive: `https://mark00lui.github.io/Stock_U_turn/`
