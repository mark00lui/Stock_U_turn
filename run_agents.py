"""CTA Multi-Agent Dashboard — standalone entry point.

Usage:
    python run_agents.py          # reads .env or env-var for API key

Environment variables (or .env file):
    ANTHROPIC_API_KEY  — required for LLM agents
    CTA_MODEL          — override LLM model (default: claude-sonnet-4-6)

NOTE: If you always use Claude Code CLI, you do NOT need this script.
      Instead ask Claude Code to run the multi-agent analysis directly —
      it uses its own auth and the .claude/agents/ definitions.
"""
import sys
import io
import os
from pathlib import Path

# Fix Windows console encoding
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def _load_dotenv() -> None:
    """Load .env from project root (no extra dependency needed)."""
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:      # don't overwrite existing
            os.environ[key] = value


def main() -> None:
    _load_dotenv()

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
        print("  Option A — .env file (recommended):")
        print('    echo "ANTHROPIC_API_KEY=sk-ant-..." > .env')
        print("    python run_agents.py")
        print()
        print("  Option B — env variable:")
        print("    export ANTHROPIC_API_KEY=sk-ant-...")
        print("    python run_agents.py")
        print()
        print("  Option C — use Claude Code CLI instead (no key needed):")
        print("    just ask Claude Code to run the multi-agent analysis")
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
