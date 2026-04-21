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

# CTA Daily Analysis Orchestrator (Serial Funnel Architecture)

You are the orchestrator for the CTA daily analysis pipeline for Taiwan top-1000 stocks.
Architecture: **Serial Funnel** — the SAME stocks flow from signal scan through validation to final picks.

## Step 1: Data Pipeline

```bash
cd E:/github/Stock_U_turn && PYTHONIOENCODING=utf-8 python main.py --export
```

Also ensure the agent output directory exists:
```bash
mkdir -p E:/github/Stock_U_turn/data/agent_outputs
```

## Step 2: Read & Prepare Signal Data

Read `E:/github/Stock_U_turn/data/signals_latest.json`.

Extract stocks where `stars >= 4` (strong signals only, typically 10-20 stocks).
These are the ONLY stocks that flow through the entire pipeline.

Write them to `E:/github/Stock_U_turn/data/agent_outputs/top_signals_today.txt` as:
```
代號 | 名稱 | 市場 | 收盤 | 漲跌% | RSI | 星等 | 訊號描述
```

**CRITICAL**: All subsequent agents analyze ONLY these stocks. No independent stock discovery.

## Step 3: Parallel Validation (Funnel Stage 2)

Spawn TWO agents in parallel. Both receive the SAME stock list from Step 2.

### 3a: Revenue Analyst
- Input: The signal stock list (10-20 stocks) from Step 2
- Task: For EACH stock in the list, evaluate monthly revenue, EPS, financial health
- Output format: Write to `E:/github/Stock_U_turn/data/agent_outputs/fundamentals.md`
  - Must include a per-stock grade table: `| 代號 | 名稱 | 營收YoY | EPS | 基本面等級 | 簡評 |`
  - Grades: A (strong), B (neutral), C (weak), D (red flag)
  - Brief market overview (3-4 lines max)

### 3b: Industry Analyst
- Input: The signal stock list (10-20 stocks) from Step 2
- Task: For EACH stock in the list, evaluate its industry cycle position and sector health
- Output format: Write to `E:/github/Stock_U_turn/data/agent_outputs/industry.md`
  - Must include a per-stock grade table: `| 代號 | 名稱 | 產業別 | 景氣位置 | 產業評等 | 簡評 |`
  - Grades: A (expansion), B (recovery), C (trough), D (decline)
  - Brief sector overview (3-4 lines max)

## Step 4: Chief Strategist (Funnel Stage 3)

Read outputs from Step 3. Produce UNIFIED scoring for the SAME stocks.

- Input: Signal list + fundamentals grades + industry grades
- Scoring: Technical 40% + Fundamental 30% + Industry 30% → integrated score 0-100
- Output format: Write to `E:/github/Stock_U_turn/data/agent_outputs/strategy.md`
  - UNIFIED table: `| 代號 | 名稱 | 收盤 | 技術分 | 基本分 | 產業分 | 整合分 | 風險 | 建議 |`
  - Market outlook (3-4 lines)
  - Risk warnings for D-grade stocks
  - Top 5 final picks with brief rationale

## Step 5: Trader

- Input: Strategy Top 5-8 picks from Step 4
- Task: Concrete trade plans with entry/stop/target/position for each
- Output: Write to `E:/github/Stock_U_turn/data/agent_outputs/trades.md`

## Step 6: Triple Strategy Backtests (all min-stars=4, STRONG verdict)

```bash
cd E:/github/Stock_U_turn && PYTHONIOENCODING=utf-8 python backtest.py --signal-type reversal --label reversal --min-stars 4 --stop-loss -7 --target 10 --max-hold 20 --position 5 --early-exit-days 10 --early-exit-min 3
cd E:/github/Stock_U_turn && PYTHONIOENCODING=utf-8 python backtest.py --signal-type momentum --label momentum --min-stars 4 --stop-loss -8 --target 10 --max-hold 15 --position 5 --early-exit-days 10 --early-exit-min 3
cd E:/github/Stock_U_turn && PYTHONIOENCODING=utf-8 python backtest.py --signal-type breakout --label breakout --min-stars 4 --stop-loss -8 --target 12 --max-hold 20 --position 5 --early-exit-days 10 --early-exit-min 4
```

## Step 7: Generate Daily Report + Publish

```bash
cd E:/github/Stock_U_turn && PYTHONIOENCODING=utf-8 python generate_daily_md.py
cd E:/github/Stock_U_turn && PYTHONIOENCODING=utf-8 python publish.py
```

## Step 8: Summary

Report: date, signal counts, Top 3 picks with integrated scores, backtest headlines, report link.
