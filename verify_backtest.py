"""Quantitative verification of CTA backtest results.

Uses statistical tests to validate whether backtest performance is
statistically significant (not due to random chance).

Tests:
  1. Win rate significance — binomial test vs 50%
  2. Mean P&L significance — t-test vs 0
  3. Profit factor bootstrap CI — 10,000 resamples
  4. Monte Carlo equity curve — simulated paths under null hypothesis
  5. Max drawdown distribution — bootstrap MDD percentiles

Usage:
    python verify_backtest.py                    # verify all strategies
    python verify_backtest.py --label office     # verify specific strategy
"""
from __future__ import annotations

import json
import sys
import io
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np
from scipy import stats

from config import DATA_DIR


def load_trades(label: str) -> list[dict]:
    p = DATA_DIR / f"backtest_{label}.json"
    if not p.exists():
        return []
    bt = json.loads(p.read_text(encoding="utf-8"))
    return [t for t in bt.get("trades", []) if t.get("exit_reason") != "持倉中"]


def verify(label: str, trades: list[dict]) -> dict:
    """Run all verification tests on a set of closed trades."""
    if len(trades) < 5:
        return {"label": label, "error": f"Too few trades ({len(trades)}) for verification"}

    pnls = np.array([t["pnl_pct"] for t in trades])
    n = len(pnls)
    wins = np.sum(pnls > 0)
    losses = np.sum(pnls <= 0)
    win_rate = wins / n

    results = {"label": label, "n_trades": n}

    # ── Test 1: Win rate binomial test ────────────────
    # H0: win_rate = 0.5 (random), H1: win_rate > 0.5
    binom_p = stats.binomtest(int(wins), n, 0.5, alternative="greater").pvalue
    results["win_rate"] = {
        "observed": round(win_rate * 100, 1),
        "p_value": round(binom_p, 4),
        "significant": binom_p < 0.05,
        "interpretation": "WR significantly > 50%" if binom_p < 0.05
            else "WR not significantly different from random"
    }

    # ── Test 2: Mean P&L t-test ───────────────────────
    # H0: mean_pnl = 0, H1: mean_pnl > 0
    t_stat, t_p = stats.ttest_1samp(pnls, 0)
    t_p_one = t_p / 2 if t_stat > 0 else 1 - t_p / 2  # one-sided
    results["mean_pnl"] = {
        "observed": round(np.mean(pnls), 3),
        "std": round(np.std(pnls, ddof=1), 3),
        "t_statistic": round(t_stat, 3),
        "p_value": round(t_p_one, 4),
        "significant": t_p_one < 0.05,
        "interpretation": "Mean P&L significantly > 0" if t_p_one < 0.05
            else "Mean P&L not significantly different from 0"
    }

    # ── Test 3: Profit factor bootstrap CI ────────────
    rng = np.random.default_rng(42)
    n_bootstrap = 10000
    pf_samples = []
    for _ in range(n_bootstrap):
        sample = rng.choice(pnls, size=n, replace=True)
        gain = np.sum(sample[sample > 0])
        loss = abs(np.sum(sample[sample <= 0]))
        pf_samples.append(gain / loss if loss > 0 else float("inf"))
    pf_samples = np.array([x for x in pf_samples if x != float("inf")])
    pf_ci_lo, pf_ci_hi = float(np.percentile(pf_samples, 2.5)), float(np.percentile(pf_samples, 97.5))
    results["profit_factor"] = {
        "observed": round(np.sum(pnls[pnls > 0]) / abs(np.sum(pnls[pnls <= 0])), 3)
            if np.sum(pnls[pnls <= 0]) != 0 else float("inf"),
        "ci_95": [round(pf_ci_lo, 3), round(pf_ci_hi, 3)],
        "significant": pf_ci_lo > 1.0,
        "interpretation": f"PF 95% CI [{pf_ci_lo:.2f}, {pf_ci_hi:.2f}] — "
            + ("CI above 1.0 = genuine edge" if pf_ci_lo > 1.0
               else "CI crosses 1.0 = edge not confirmed")
    }

    # ── Test 4: Monte Carlo equity simulation ─────────
    # Simulate 10,000 equity paths using observed mean/std
    mc_paths = 10000
    mc_returns = rng.choice(pnls, size=(mc_paths, n), replace=True)
    mc_cumulative = np.cumsum(mc_returns, axis=1)
    mc_final = mc_cumulative[:, -1]
    mc_ci_lo, mc_ci_hi = float(np.percentile(mc_final, 5)), float(np.percentile(mc_final, 95))
    mc_median = float(np.median(mc_final))
    prob_positive = np.mean(mc_final > 0) * 100
    results["monte_carlo"] = {
        "paths": mc_paths,
        "median_return": round(mc_median, 2),
        "ci_90": [round(mc_ci_lo, 2), round(mc_ci_hi, 2)],
        "prob_positive": round(prob_positive, 1),
        "interpretation": f"Monte Carlo: {prob_positive:.0f}% paths profitable"
    }

    # ── Test 5: Max drawdown distribution ─────────────
    mdd_samples = []
    for i in range(min(5000, mc_paths)):
        cum = np.cumsum(mc_returns[i])
        peak = np.maximum.accumulate(cum)
        dd = cum - peak
        mdd_samples.append(np.min(dd))
    mdd_5, mdd_50, mdd_95 = [float(x) for x in np.percentile(mdd_samples, [5, 50, 95])]
    results["max_drawdown"] = {
        "median_mdd": round(mdd_50, 2),
        "worst_5pct": round(mdd_5, 2),
        "best_5pct": round(mdd_95, 2),
        "interpretation": f"Expected MDD: {mdd_50:.1f}%, worst case (5%): {mdd_5:.1f}%"
    }

    # ── Overall verdict ───────────────────────────────
    sig_count = sum([
        results["win_rate"]["significant"],
        results["mean_pnl"]["significant"],
        results["profit_factor"]["significant"],
    ])
    if sig_count == 3:
        verdict = "STRONG — all 3 tests significant"
    elif sig_count == 2:
        verdict = "MODERATE — 2/3 tests significant"
    elif sig_count == 1:
        verdict = "WEAK — only 1/3 tests significant"
    else:
        verdict = "INSUFFICIENT — no statistical significance"
    results["verdict"] = verdict

    return results


def print_report(r: dict) -> None:
    if "error" in r:
        print(f"\n  [{r['label']}] {r['error']}\n")
        return

    print(f"\n{'=' * 66}")
    print(f"  Quant Verification — {r['label']} ({r['n_trades']} trades)")
    print(f"{'=' * 66}")

    wr = r["win_rate"]
    mp = r["mean_pnl"]
    pf = r["profit_factor"]
    mc = r["monte_carlo"]
    md = r["max_drawdown"]

    pass_mark = lambda x: "PASS" if x else "FAIL"

    print(f"\n  1. Win Rate Binomial Test")
    print(f"     Observed: {wr['observed']}%  p={wr['p_value']}  [{pass_mark(wr['significant'])}]")
    print(f"     {wr['interpretation']}")

    print(f"\n  2. Mean P&L t-Test")
    print(f"     Mean: {mp['observed']}% ± {mp['std']}%  t={mp['t_statistic']}  p={mp['p_value']}  [{pass_mark(mp['significant'])}]")
    print(f"     {mp['interpretation']}")

    print(f"\n  3. Profit Factor Bootstrap (10K resamples)")
    print(f"     PF: {pf['observed']}  95% CI: {pf['ci_95']}  [{pass_mark(pf['significant'])}]")
    print(f"     {pf['interpretation']}")

    print(f"\n  4. Monte Carlo Equity Simulation ({mc['paths']:,} paths)")
    print(f"     Median return: {mc['median_return']}%  90% CI: {mc['ci_90']}")
    print(f"     {mc['interpretation']}")

    print(f"\n  5. Max Drawdown Distribution")
    print(f"     Median MDD: {md['median_mdd']}%  Worst 5%: {md['worst_5pct']}%")
    print(f"     {md['interpretation']}")

    print(f"\n  {'─' * 62}")
    print(f"  VERDICT: {r['verdict']}")
    print(f"{'=' * 66}\n")


def save_report(results: list[dict]) -> Path:
    """Save verification results as markdown for the daily report."""
    out: list[str] = []
    out.append("# 量化驗證報告")
    out.append("")

    for r in results:
        if "error" in r:
            out.append(f"### {r['label']}: {r['error']}")
            out.append("")
            continue

        wr = r["win_rate"]
        mp = r["mean_pnl"]
        pf = r["profit_factor"]
        mc = r["monte_carlo"]
        md = r["max_drawdown"]

        pass_mark = lambda x: "PASS" if x else "FAIL"

        out.append(f"### {r['label']} ({r['n_trades']} trades)")
        out.append("")
        out.append("| 檢驗項目 | 結果 | p-value | 判定 |")
        out.append("|----------|------|---------|------|")
        out.append(f"| 勝率顯著性 (>50%) | {wr['observed']}% | {wr['p_value']} | {pass_mark(wr['significant'])} |")
        out.append(f"| 平均損益 (>0) | {mp['observed']}% | {mp['p_value']} | {pass_mark(mp['significant'])} |")
        out.append(f"| PF 信賴區間 (>1.0) | {pf['observed']} CI{pf['ci_95']} | — | {pass_mark(pf['significant'])} |")
        out.append(f"| MC 獲利機率 | {mc['prob_positive']}% | — | {'PASS' if mc['prob_positive'] > 60 else 'FAIL'} |")
        out.append(f"| 預期最大回檔 | {md['median_mdd']}% (worst {md['worst_5pct']}%) | — | INFO |")
        out.append("")
        out.append(f"**判定：{r['verdict']}**")
        out.append("")

    p = DATA_DIR / "agent_outputs" / "verification.md"
    p.write_text("\n".join(out), encoding="utf-8")
    return p


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", type=str, default="",
                        help="Verify specific strategy (default: all)")
    args = parser.parse_args()

    if args.label:
        labels = [args.label]
    else:
        labels = ["momentum", "manual", "office"]

    results = []
    for label in labels:
        trades = load_trades(label)
        r = verify(label, trades)
        results.append(r)
        print_report(r)

    save_report(results)
    print(f"  Verification report saved to: data/agent_outputs/verification.md")


if __name__ == "__main__":
    main()
