#!/usr/bin/env python3
"""papers/run_scenario_comparison.py

Run weak vs medium hospital ransomware comparison.
Also runs budget sensitivity sweep on the MEDIUM scenario.

Default: N=100 iterations (matches paper §7 claims).
  --iterations N > 100 writes *_n{N}.json files so the N=100 baselines
  (referenced in paper §7 tables and figures) are preserved.

Outputs (N=100):
  papers/data/scenario_comparison.json
  papers/data/budget_sensitivity.json

Outputs (N>100):
  papers/data/scenario_comparison_n{N}.json
  papers/data/budget_sensitivity_n{N}.json
"""

import argparse
import copy
import gc
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("FAIR_CAM_CONFIG", str(PROJECT_ROOT / "inputs" / "model_config.yaml"))

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

ONE_YEAR = 8760


def load_scenario(name):
    from src.data.json_loader import JsonLoader
    p = PROJECT_ROOT / "scenarios" / name / "scenario_data.json"
    return JsonLoader(json_path=str(p)).load_all()


def _worker_iteration(args):
    scenario_name, seed, steps, budget_override = args
    from src.model import FAIRCAMModel
    from src.config.loader import get_config

    data = load_scenario(scenario_name)
    cfg = get_config()
    overrides = {}
    if budget_override is not None:
        overrides["remediation"] = {"budget_hours_per_month": float(budget_override)}

    with cfg.override(overrides):
        model = FAIRCAMModel(model_data=copy.deepcopy(data), seed=seed, steps=steps, collect_timeseries=False)
        for _ in range(steps):
            model.step()

    ms = model.metrics_state
    return {
        "contacts": int(ms.total_contact_events),
        "breaches": int(ms.total_breach_events),
        "losses": int(ms.total_loss_events),
        "gross_loss": float(ms.total_gross_losses),
        "variance_events": int(ms.total_variance_events),
        "avoided": int(ms.total_avoided_contacts),
        "resisted": int(ms.total_resisted_events),
    }


def run_batch(scenario_name, n_iterations, steps, seed_base=0, budget_override=None):
    results = {
        "contacts": [], "breaches": [], "losses": [],
        "gross_loss": [], "variance_events": [],
        "avoided": [], "resisted": [],
    }

    args_iter = [(scenario_name, seed_base + i, steps, budget_override)
                 for i in range(n_iterations)]
    # processes=2 + maxtasksperchild=25: macbook-safe, matches exp2/exp3 pattern
    with mp.Pool(processes=2, maxtasksperchild=25) as pool:
        completed = 0
        t0 = time.time()
        for r in pool.imap_unordered(_worker_iteration, args_iter):
            for k in results:
                results[k].append(r[k])
            completed += 1
            if n_iterations >= 100 and (completed % max(25, n_iterations // 20) == 0 or completed == n_iterations):
                elapsed = time.time() - t0
                eta = elapsed / completed * (n_iterations - completed)
                print(f"      [{completed}/{n_iterations}] done, {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining", flush=True)
    return results


def summarize(results):
    n = len(results["gross_loss"])
    losses = sorted(results["gross_loss"])
    total_breaches = sum(results["breaches"])
    iters_with_breach = sum(1 for b in results["breaches"] if b > 0)
    mean_ale = sum(losses) / n
    p95 = losses[min(int(n * 0.95), n - 1)]
    p99 = losses[min(int(n * 0.99), n - 1)]

    return {
        "iterations": n,
        "mean_contacts": sum(results["contacts"]) / n,
        "mean_avoided": sum(results["avoided"]) / n,
        "mean_resisted": sum(results["resisted"]) / n,
        "total_breaches": total_breaches,
        "mean_breaches": total_breaches / n,
        "iters_with_breach": iters_with_breach,
        "breach_rate_pct": (total_breaches / max(1, sum(results["contacts"]))) * 100,
        "mean_ale": mean_ale,
        "median_ale": losses[n // 2],
        "p95_ale": p95,
        "p99_ale": p99,
        "max_ale": max(losses),
        "mean_variance_events": sum(results["variance_events"]) / n,
    }


def main():
    import logging
    logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser(description="Scenario comparison + budget sensitivity")
    parser.add_argument("--iterations", type=int, default=100,
                        help="Iterations per cell (default: 100 matches paper baseline)")
    parser.add_argument("--only", choices=["scenario", "budget", "both"], default="both",
                        help="Which sweep to run")
    args = parser.parse_args()
    N = args.iterations
    suffix = "" if N == 100 else f"_n{N}"

    # ── Scenario Comparison ──
    if args.only in ("scenario", "both"):
        print("=" * 70)
        print(f"SCENARIO COMPARISON: Weak vs Medium ({N} iterations)")
        print("=" * 70)

        comparison = {}
        for name in ["hospital_ransomware_weak", "hospital_ransomware_medium"]:
            label = name.replace("hospital_ransomware_", "")
            print(f"\n  Running {label}...", flush=True)
            t0 = time.time()
            results = run_batch(name, N, ONE_YEAR)
            summary = summarize(results)
            # Preserve per-seed arrays for downstream bootstrap / CI analysis
            summary["per_seed"] = results
            comparison[label] = summary
            elapsed = time.time() - t0
            print(f"    Done in {elapsed:.0f}s — Mean ALE: ${summary['mean_ale']:,.0f}, "
                  f"Breaches: {summary['total_breaches']}, "
                  f"Iters w/ breach: {summary['iters_with_breach']}/{N}")

        out_path = DATA_DIR / f"scenario_comparison{suffix}.json"
        with open(out_path, "w") as f:
            json.dump(comparison, f, indent=2)
        print(f"\n  Saved: {out_path}")
    else:
        comparison = None

    # ── Budget Sensitivity (Medium) ──
    if args.only in ("budget", "both"):
        print("\n" + "=" * 70)
        print(f"BUDGET SENSITIVITY: Medium scenario, 7 budget levels ({N} iterations)")
        print("=" * 70)

        budget_levels = [2, 5, 10, 20, 40, 80, 160]
        budget_results = {"budget_levels": budget_levels, "iterations": N, "runs": {}}

        # For vs-40hr comparison we need the medium/40hr ALE; fall back to reading existing file.
        baseline_ale = None
        if comparison and "medium" in comparison:
            baseline_ale = comparison["medium"]["mean_ale"]
        else:
            existing = DATA_DIR / "scenario_comparison.json"
            if existing.exists():
                with open(existing) as f:
                    baseline_ale = json.load(f).get("medium", {}).get("mean_ale")

        for budget in budget_levels:
            print(f"\n  Budget: {budget} hrs/mo ({N} iterations)...", flush=True)
            t0 = time.time()
            results = run_batch("hospital_ransomware_medium", N, ONE_YEAR, budget_override=budget)
            summary = summarize(results)
            if baseline_ale:
                summary["vs_40hr_pct"] = ((summary["mean_ale"] - baseline_ale)
                                          / max(1, baseline_ale)) * 100
            summary["per_seed"] = results
            budget_results["runs"][str(budget)] = summary
            elapsed = time.time() - t0
            vs = f" ({summary.get('vs_40hr_pct','?'):+.1f}% vs 40hr)" if "vs_40hr_pct" in summary else ""
            print(f"    Done in {elapsed:.0f}s — Mean ALE: ${summary['mean_ale']:,.0f}{vs}")

        out_path = DATA_DIR / f"budget_sensitivity{suffix}.json"
        with open(out_path, "w") as f:
            json.dump(budget_results, f, indent=2)
        print(f"\n  Saved: {out_path}")


if __name__ == "__main__":
    main()
