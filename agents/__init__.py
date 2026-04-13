"""CTA multi-agent system.

Agents
------
- Chief Strategist : cross-agent coordination, final ratings
- Yahoo Finance RD : data pipeline (pure Python, no LLM)
- Signal Analyst   : technical indicators (pure Python, no LLM)
- Revenue Analyst  : monthly revenue & earnings (LLM-powered)
- Industry Analyst : sector trend research (LLM-powered)
- Trader           : trade plan generation (LLM-powered)
"""

from agents.base import BaseAgent          # noqa: F401
from agents.orchestrator import Orchestrator  # noqa: F401
