"""Multi-agent orchestrator.

Pipeline
--------
Phase 1 (Python)  : Data RD + Signal Analyst  — deterministic
Phase 2 (LLM ×2)  : Revenue Analyst ∥ Industry Analyst — parallel
Phase 3 (LLM)     : Chief Strategist — synthesis
Phase 4 (LLM)     : Trader — trade plans
Phase 5 (Python)  : Enhanced HTML report
"""
from __future__ import annotations

import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import config
from config import CACHE_DIR, OUTPUT_DIR
from agents.base import BaseAgent
from agents import prompts


# ── Helpers ────────────────────────────────────────────

def _fmt_signal_table(results: list[dict], limit: int = 50) -> str:
    """Format top signal results as a compact text table for LLM context."""
    lines = ["代號 | 名稱 | 市場 | 收盤 | 漲跌% | RSI | MACD | 星等 | 訊號"]
    lines.append("--- | --- | --- | --- | --- | --- | --- | --- | ---")
    for r in results[:limit]:
        sigs = ", ".join(r["descriptions"])
        lines.append(
            f'{r["code"]} | {r["name"]} | {r["market"]} | '
            f'{r["close"]:.1f} | {r["pct_change"]:+.1f}% | '
            f'{r["rsi"]:.1f} | {r["macd"]:.4f} | '
            f'{"★" * r["stars"]} | {sigs}'
        )
    return "\n".join(lines)


def _extract_sectors(results: list[dict]) -> str:
    """Derive unique sector hints from stock names/codes."""
    # simple heuristic — group by market + first digit of code
    sector_map = {
        "1": "水泥/食品/塑膠/紡織/電機/電器/化學/玻璃/鋼鐵/橡膠/造紙/汽車/營建",
        "2": "半導體/電子/光電/通訊/IC設計/電子通路",
        "3": "IC設計/電子零組件/光電/通訊/資訊服務/軟體",
        "4": "生技/醫療/航運/觀光/貿易/百貨",
        "5": "金融/保險/證券",
        "6": "半導體/電子/光電/電子零組件/資訊服務",
        "8": "金融/建材/觀光/文創",
        "9": "其他/KY股",
    }
    seen: set[str] = set()
    for r in results:
        prefix = r["code"][0] if r["code"] else ""
        if prefix in sector_map:
            seen.add(sector_map[prefix])
    # also just list top stock names for the LLM to infer sector
    top_names = ", ".join(f'{r["code"]} {r["name"]}' for r in results[:30])
    return (
        f"涵蓋行業板塊: {'; '.join(seen)}\n\n"
        f"代表性個股: {top_names}"
    )


# ── Orchestrator ───────────────────────────────────────

class Orchestrator:
    """Run the full CTA multi-agent pipeline."""

    def __init__(self) -> None:
        self.revenue_agent = BaseAgent(
            "Revenue Analyst", prompts.REVENUE_ANALYST
        )
        self.industry_agent = BaseAgent(
            "Industry Analyst", prompts.INDUSTRY_ANALYST
        )
        self.strategist = BaseAgent(
            "Chief Strategist", prompts.CHIEF_STRATEGIST
        )
        self.trader = BaseAgent(
            "Trader", prompts.TRADER
        )

    # ── Phase 1: data + technical (pure Python) ────────
    def run_data_pipeline(self) -> tuple[list[dict], dict, list[dict]]:
        """Return (stocks, prices, signal_results)."""
        from fetch_universe import get_top_stocks
        from fetch_prices import fetch_prices
        from indicators import calc_rsi, calc_macd
        from signals import detect_reversal

        print("\n[Phase 1] Data RD + Signal Analyst  (Python)")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        print("  [Data RD] fetching stock universe ...")
        stocks = get_top_stocks()

        print("  [Data RD] downloading prices ...")
        prices = fetch_prices(stocks)

        print("  [Signal Analyst] computing indicators ...")
        ticker_map = {s["yf_ticker"]: s for s in stocks}
        results: list[dict] = []

        for ticker, df in prices.items():
            info = ticker_map.get(ticker, {})
            try:
                df = df.copy()
                close = df["Close"]
                df["rsi"] = calc_rsi(close, config.RSI_PERIOD)
                macd, sig, hist = calc_macd(
                    close, config.MACD_FAST, config.MACD_SLOW, config.MACD_SIGNAL
                )
                df["macd"] = macd
                df["macd_signal"] = sig
                df["macd_hist"] = hist

                signal = detect_reversal(df)
                if signal is None:
                    continue

                prev = close.iloc[-2] if len(close) >= 2 else close.iloc[-1]
                pct = (close.iloc[-1] / prev - 1) * 100

                results.append(
                    {
                        "code": info.get("code", ticker.split(".")[0]),
                        "name": info.get("name", ""),
                        "market": info.get("market", ""),
                        "close": round(float(close.iloc[-1]), 2),
                        "pct_change": round(float(pct), 2),
                        "recent_prices": [
                            round(float(p), 2) for p in close.iloc[-20:].tolist()
                        ],
                        **signal,
                    }
                )
            except Exception:
                continue

        results.sort(key=lambda r: (-r["stars"], -r["score"]))
        strong = sum(1 for r in results if r["level"] == "strong")
        medium = sum(1 for r in results if r["level"] == "medium")
        watch  = sum(1 for r in results if r["level"] == "watch")
        print(
            f"  [Signal Analyst] {len(results)} signals  "
            f"(Strong {strong} / Call {medium} / Watch {watch})"
        )
        return stocks, prices, results

    # ── Phase 2: parallel LLM analysis ─────────────────
    def run_analysis(self, results: list[dict]) -> dict[str, str]:
        """Run Revenue & Industry agents in parallel; return their texts."""
        top = [r for r in results if r["stars"] >= 3][:50]
        signal_table = _fmt_signal_table(top)
        sector_ctx = _extract_sectors(top)

        print("\n[Phase 2] Revenue Analyst || Industry Analyst  (LLM x2)")
        analyses: dict[str, str] = {}

        def _run_revenue():
            return self.revenue_agent.run(
                "請分析以下台股候選標的的基本面（月營收與財務狀況）：",
                signal_table,
            )

        def _run_industry():
            return self.industry_agent.run(
                "請分析以下台股候選標的所屬行業的最新趨勢：",
                sector_ctx,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_rev = pool.submit(_run_revenue)
            fut_ind = pool.submit(_run_industry)
            for fut in as_completed([fut_rev, fut_ind]):
                pass  # just wait
            analyses["fundamentals"] = fut_rev.result()
            analyses["industry"] = fut_ind.result()

        return analyses

    # ── Phase 3: strategy synthesis ────────────────────
    def run_strategy(
        self, results: list[dict], analyses: dict[str, str]
    ) -> str:
        top = [r for r in results if r["stars"] >= 3][:50]
        signal_table = _fmt_signal_table(top)

        ctx = (
            f"## 技術面訊號\n{signal_table}\n\n"
            f"## 基本面分析\n{analyses['fundamentals']}\n\n"
            f"## 行業面分析\n{analyses['industry']}"
        )

        print("\n[Phase 3] Chief Strategist  (LLM)")
        return self.strategist.run(
            "請整合以下三維分析，產出最終操作建議與 Top Picks：", ctx
        )

    # ── Phase 4: trade plans ───────────────────────────
    def run_trader(self, strategy: str) -> str:
        print("\n[Phase 4] Trader  (LLM)")
        return self.trader.run(
            "請根據以下策略建議，為推薦標的制定具體交易計畫：", strategy
        )

    # ── Full pipeline ──────────────────────────────────
    def run(self) -> dict:
        """Execute the complete multi-agent pipeline.

        Returns a dict with all intermediate + final outputs.
        """
        today = date.today().isoformat()

        print("=" * 60)
        print("  CTA Multi-Agent Dashboard")
        print(f"  台股前 {config.TOP_N} 大  ·  {today}")
        print("=" * 60)

        # Phase 1 — Python
        stocks, prices, results = self.run_data_pipeline()

        # Phase 2 — LLM parallel
        analyses = self.run_analysis(results)

        # Phase 3 — LLM
        strategy = self.run_strategy(results, analyses)

        # Phase 4 — LLM
        trades = self.run_trader(strategy)

        return {
            "date": today,
            "stocks": stocks,
            "prices": prices,
            "results": results,
            "total_scanned": len(prices),
            "fundamentals": analyses["fundamentals"],
            "industry": analyses["industry"],
            "strategy": strategy,
            "trades": trades,
        }
