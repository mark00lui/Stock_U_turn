"""Assemble an enhanced multi-agent HTML report from pre-generated analysis files.

Called by Claude Code after all agents have finished writing their analysis
to data/agent_outputs/.

Usage:
    python generate_report_cli.py
"""
import sys
import io
import json
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config import DATA_DIR, OUTPUT_DIR
from report import generate_enhanced_report


def main() -> None:
    signals_file = DATA_DIR / "signals_latest.json"
    agent_dir = DATA_DIR / "agent_outputs"

    if not signals_file.exists():
        print("No signals data found.  Run  python main.py --export  first.")
        sys.exit(1)

    signals = json.loads(signals_file.read_text(encoding="utf-8"))

    def _read(name: str) -> str:
        p = agent_dir / f"{name}.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    out = generate_enhanced_report(
        results=signals["results"],
        total_scanned=signals["total_scanned"],
        date_str=signals["date"],
        fundamentals=_read("fundamentals"),
        industry=_read("industry"),
        strategy=_read("strategy"),
        trades=_read("trades"),
    )
    print(f"Enhanced report: {out}")


if __name__ == "__main__":
    main()
