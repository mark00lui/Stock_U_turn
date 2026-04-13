"""CTA Multi-Agent Dashboard — entry point.

Usage:
    # Full multi-agent pipeline (requires ANTHROPIC_API_KEY)
    python run_agents.py

    # Technical-only fallback (no API key needed)
    python main.py

Environment variables:
    ANTHROPIC_API_KEY  — required for LLM agents
    CTA_MODEL          — override LLM model (default: claude-sonnet-4-6)
"""
import sys
import io
import os
from datetime import date

# Fix Windows console encoding
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def main() -> None:
    # ── dependency check ───────────────────────────────
    missing = []
    for mod in ("yfinance", "pandas", "requests", "numpy", "anthropic"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        print(f"Missing packages: {', '.join(missing)}")
        print("  pip install -r requirements.txt")
        sys.exit(1)

    # ── API key check ──────────────────────────────────
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("=" * 60)
        print("  ANTHROPIC_API_KEY not set.")
        print()
        print("  To run the full 6-agent pipeline:")
        print("    export ANTHROPIC_API_KEY=sk-ant-...")
        print("    python run_agents.py")
        print()
        print("  To run technical analysis only (no API needed):")
        print("    python main.py")
        print("=" * 60)
        sys.exit(1)

    # ── run orchestrator ───────────────────────────────
    from agents.orchestrator import Orchestrator
    from report import generate_enhanced_report

    orch = Orchestrator()
    result = orch.run()

    # ── Phase 5: enhanced report ───────────────────────
    print("\n[Phase 5] Generating enhanced HTML report ...")
    out = generate_enhanced_report(
        results=result["results"],
        total_scanned=result["total_scanned"],
        date_str=result["date"],
        fundamentals=result["fundamentals"],
        industry=result["industry"],
        strategy=result["strategy"],
        trades=result["trades"],
    )
    print(f"\n  >>> {out}")
    print("  Open in browser to view the multi-agent dashboard.")


if __name__ == "__main__":
    main()
