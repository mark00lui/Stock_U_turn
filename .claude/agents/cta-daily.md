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

## Step 6: Generate Enhanced Report

Run the report assembly script:

```bash
cd E:/github/Stock_U_turn && PYTHONIOENCODING=utf-8 python generate_report_cli.py
```

Then open the report in the default browser:

```bash
start "" "E:/github/Stock_U_turn/output/cta_agent_report_$(date +%Y-%m-%d).html"
```

## Step 7: Summary

Report completion with:
- Date of analysis
- Number of stocks scanned
- Number of signals found (Strong / Call / Watch)
- Top 3 picks with scores
- Report file path
