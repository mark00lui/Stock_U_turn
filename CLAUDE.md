# Stock U-turn — CTA Trading Signal Dashboard

## Project Overview
CTA (Commodity Trading Advisor) style trading signal dashboard for Taiwan top-1000 stocks.
Daily HTML report with RSI/MACD bottom-reversal Call signals.

## Tech Stack
- Python 3.x, pandas, numpy, yfinance, requests
- Anthropic SDK (optional, for standalone multi-agent mode)
- Self-contained static HTML reports (no web server needed)

## Two Execution Modes

### Mode A: Technical Analysis Only (no API key)
```bash
python main.py              # basic RSI/MACD dashboard
python main.py --export     # also exports data/signals_latest.json
```

### Mode B: Multi-Agent Analysis (Claude Code native — recommended)
When the user asks to "run the multi-agent CTA analysis", follow this workflow:

1. **Data Pipeline** — run `python main.py --export` to fetch data and compute signals
2. **Read Signals** — read `data/signals_latest.json` for the top signal stocks
3. **Spawn 4 Agents in parallel pairs**:
   - Use Agent tool with `.claude/agents/revenue-analyst.md` → write output to `data/agent_outputs/fundamentals.md`
   - Use Agent tool with `.claude/agents/industry-analyst.md` → write output to `data/agent_outputs/industry.md`
4. **Chief Strategist** — read all outputs, synthesize → write to `data/agent_outputs/strategy.md`
5. **Trader** — read strategy, generate trade plans → write to `data/agent_outputs/trades.md`
6. **Generate Report** — run `python generate_report_cli.py` → produces `output/cta_agent_report_*.html`

### Mode C: Standalone Multi-Agent (API key required)
```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
python run_agents.py
```

## 6-Agent Roles
| Agent | Type | Role |
|-------|------|------|
| Data RD | Python | TWSE/TPEx data fetch, yfinance prices |
| Signal Analyst | Python | RSI/MACD indicators, reversal detection |
| Revenue Analyst | LLM | Monthly revenue & quarterly earnings |
| Industry Analyst | LLM | Sector trends, cycle positioning |
| Chief Strategist | LLM | 3D synthesis (tech 40%, fundamental 30%, industry 30%) |
| Trader | LLM | Trade plans, position sizing, risk control |

## Key Files
- `main.py` — data pipeline + technical report
- `run_agents.py` — standalone multi-agent (needs API key)
- `generate_report_cli.py` — assemble enhanced report from agent output files
- `config.py` — all parameters (RSI/MACD/thresholds)
- `agents/orchestrator.py` — Python multi-agent pipeline
- `.claude/agents/*.md` — Claude Code agent definitions

## Development Guidelines
- Windows 11 environment, UTF-8 encoding
- Auto-commit enabled for development iterations
- Main branch: `main`
