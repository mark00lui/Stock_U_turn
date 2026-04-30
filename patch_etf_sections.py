"""Patch §3.5 ETF Smart Money sections in past daily reports with correct shares-delta logic.

Background — earlier reports (2026-04-27 → 2026-04-30) used weight_delta to compute
TRIPLE BUY/SELL, which is contaminated by stock-price moves and AUM swings.
This caused systematic false signals (e.g. "TSMC TRIPLE SELL connecting 4/28-30"
when in reality 統一 actively bought 925k TSMC shares across 4/27 + 4/30).

This patch:
  1. Recomputes consensus using compute_consensus_signal() (shares-delta basis)
  2. Replaces the §3.5 ETF Smart Money block in each output/cta_daily_*.md
  3. Writes a per-date corrected ETF report to data/agent_outputs/backfill/
"""
from __future__ import annotations

import sys
import io
import re
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config import DATA_DIR, OUTPUT_DIR
from fetch_active_etf import compute_consensus_signal, format_consensus_report


# (today, yesterday) pairs to patch
PATCH_PAIRS = [
    ("2026-04-27", "2026-04-24"),  # first real diff (skips weekend)
    ("2026-04-28", "2026-04-27"),
    ("2026-04-29", "2026-04-28"),
    ("2026-04-30", "2026-04-29"),
]


def _build_etf_block(consensus: dict) -> str:
    """Wrap the consensus report into the §3.5 subsection used by daily MDs."""
    body = format_consensus_report(consensus, top_n=8)
    # convert top-level "## ETF Smart-Money Consensus..." header into "## 3.5 ETF Smart Money 籌碼疊加"
    body = body.replace(
        f"## ETF Smart-Money Consensus ({consensus['date_yesterday']} → {consensus['date_today']}, share-delta basis)",
        f"## 3.5 ETF Smart Money 籌碼疊加 (修正版 — shares-delta basis)",
        1,
    )
    correction_note = (
        f"\n> ⚠️ **本段於 2026-04-30 重做** — 原本用 weight_delta 算 TRIPLE BUY/SELL，\n"
        f"> 但 weight 同時含股價/AUM 效應，導致 TSMC 等個股訊號反向（4/27 + 4/30 統一基金\n"
        f"> 各加碼 579k + 346k 股，被原邏輯標為 SELL）。本版只用 raw shares delta，"
        f"> 排除股價與申購贖回干擾。\n"
    )
    return correction_note + body


_SECTION_RE = re.compile(r"## 3\.5 ETF.*?(?=^## |\Z)", re.DOTALL | re.MULTILINE)
_BACKWARDS_INSERT_AFTER = re.compile(r"(^## 3\.\s.*?)(?=^## )", re.DOTALL | re.MULTILINE)


def _patch_md(md_path: Path, new_block: str) -> str:
    """Replace existing §3.5 block, or insert one after §3 if missing.

    Returns: 'replaced' | 'inserted' | 'appended' | 'missing-file'
    """
    if not md_path.exists():
        return "missing-file"
    txt = md_path.read_text(encoding="utf-8")

    if _SECTION_RE.search(txt):
        new_txt = _SECTION_RE.sub(new_block.rstrip() + "\n\n", txt, count=1)
        md_path.write_text(new_txt, encoding="utf-8")
        return "replaced"

    # No existing §3.5 — insert after §3 if it exists, else append
    m = re.search(r"^(## 4\.\s.*?)$", txt, flags=re.MULTILINE)
    if m:
        new_txt = txt[:m.start()] + new_block.rstrip() + "\n\n" + txt[m.start():]
        md_path.write_text(new_txt, encoding="utf-8")
        return "inserted"

    md_path.write_text(txt.rstrip() + "\n\n" + new_block.rstrip() + "\n", encoding="utf-8")
    return "appended"


def main() -> None:
    backfill_dir = DATA_DIR / "agent_outputs" / "backfill"
    backfill_dir.mkdir(parents=True, exist_ok=True)

    for d_today, d_yday in PATCH_PAIRS:
        print(f"\n=== Patching {d_today} (vs {d_yday}) ===")
        consensus = compute_consensus_signal(d_today, d_yday)

        n_tb = len(consensus["TRIPLE_BUY"])
        n_ts = len(consensus["TRIPLE_SELL"])
        n_sb = len(consensus["SINGLE_BUY"])
        n_ss = len(consensus["SINGLE_SELL"])
        n_mx = len(consensus["MIXED"])
        print(f"  Consensus: TRIPLE_BUY={n_tb}, TRIPLE_SELL={n_ts}, "
              f"SINGLE_BUY={n_sb}, SINGLE_SELL={n_ss}, MIXED={n_mx}")

        # Save standalone report
        report = format_consensus_report(consensus, top_n=15)
        out = backfill_dir / f"etf_consensus_corrected_{d_today}.md"
        out.write_text(report, encoding="utf-8")
        print(f"  Wrote standalone: {out.relative_to(DATA_DIR.parent)}")

        # Patch the daily MD
        new_block = _build_etf_block(consensus)
        md = OUTPUT_DIR / f"cta_daily_{d_today}.md"
        result = _patch_md(md, new_block)
        print(f"  Daily MD ({md.name}): {result}")


if __name__ == "__main__":
    main()
