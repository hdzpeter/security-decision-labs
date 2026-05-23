#!/usr/bin/env python3
"""Threat landscape frequency sweep for OpEff divergence analysis.

Varies change_frequency_per_year from 0 to 1 in 0.1 increments,
holding budget fixed at 40 hrs/mo (paper default). Default 100
iterations per level (seeds 0-99 paired); --iterations N>100 writes
to threat_freq_sweep_n{N}.json to preserve the paper-baseline file.

Measures per-LEC emergent OpEff vs analytical OpEff at each level.
"""

import argparse
import copy
import gc
import json
import multiprocessing as mp
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("FAIR_CAM_CONFIG", str(PROJECT_ROOT / "inputs" / "model_config.yaml"))

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

SCENARIO = "hospital_ransomware_medium"
ONE_YEAR = 8760
BUDGET = 40  # hrs/mo — paper default


def load_scenario():
    from src.config.loader import get_config
    from src.data.json_loader import JsonLoader
    get_config()
    p = PROJECT_ROOT / "scenarios" / SCENARIO / "scenario_data.json"
    return JsonLoader(json_path=str(p)).load_all()


def run_model(data, seed, steps, freq_override):
    from src.model import FAIRCAMModel
    from src.config.loader import get_config

    cfg = get_config()
    overrides = {
        "remediation": {"budget_hours_per_month": float(BUDGET)},
        "threat_landscape": {"change_frequency_per_year": float(freq_override)},
    }
    with cfg.override(overrides):
        model = FAIRCAMModel(model_data=copy.deepcopy(data), seed=seed, steps=steps, collect_timeseries=False)
        for _ in range(steps):
            model.step()
    return model


def compute_opeff(model):
    """Return dict of control_id -> (emergent_opeff, analytical_opeff)."""
    results = {}
    narrative = model.narrative

    for agent in model.schedule.agents:
        cls = agent.__class__.__name__
        if cls not in ("LECAgent",):
            continue

        cid = str(agent.unique_id)
        intended = float(getattr(agent, "intended_efficacy", 0.0))
        variant_eff = float(getattr(agent, "variant_efficacy", 0.0))

        # Skip binary controls (intended == 1.0 and variant == 0.0 or similar)
        if intended <= 0.0:
            continue

        # Emergent reliability from narrative events
        var_events = [v for v in narrative.variance_events if v.control_id == cid]
        recovery_events = [r for r in narrative.recovery_events
                           if getattr(r, "control_id", "") == cid]

        total_variance_ticks = 0
        for ve in var_events:
            start = int(ve.tick)
            end = ONE_YEAR
            for re in recovery_events:
                re_tick = int(getattr(re, "tick", ONE_YEAR))
                if re_tick > start:
                    end = re_tick
                    break
            total_variance_ticks += (end - start)

        emergent_rel = 1.0 - (total_variance_ticks / ONE_YEAR)
        emergent_rel = max(0.0, min(1.0, emergent_rel))
        emergent_opeff = emergent_rel * intended + (1.0 - emergent_rel) * variant_eff

        # Analytical reliability: infinite-budget, no VMC cascades
        change_freq_params = getattr(agent, "change_freq_dist_params", None)
        analytical_opeff = emergent_opeff  # fallback
        if change_freq_params:
            expected_change_hours = float(change_freq_params.get("param2", 4000))
            default_rem = 40
            rem_hours = float(getattr(agent, "params", {}).get(
                "Remediation_Hours", default_rem) or default_rem)
            analytical_rel = expected_change_hours / (expected_change_hours + rem_hours)
            analytical_opeff = analytical_rel * intended + (1.0 - analytical_rel) * variant_eff

        results[cid] = (emergent_opeff, analytical_opeff)

    return results


def _worker_iteration(args):
    seed, freq, steps = args
    data = load_scenario()
    model = run_model(data, seed=seed, steps=steps, freq_override=freq)
    ale = float(model.metrics_state.total_gross_losses)
    breaches = int(model.metrics_state.total_breach_events)
    opeff = compute_opeff(model)
    return ale, breaches, opeff


def main():
    parser = argparse.ArgumentParser(description="Threat landscape frequency sweep")
    parser.add_argument("--iterations", type=int, default=100,
                        help="Iterations per freq level (default 100 matches paper)")
    args = parser.parse_args()
    ITERATIONS = args.iterations

    print("Loading scenario...")
    load_scenario()  # parent-side sanity check; workers reload independently

    freq_levels = [round(x * 0.1, 1) for x in range(11)]  # 0.0, 0.1, ..., 1.0
    all_results = {
        "experiment": "threat_landscape_frequency_sweep",
        "budget_fixed": BUDGET,
        "iterations": ITERATIONS,
        "freq_levels": freq_levels,
        "per_level": {},
    }

    total_t0 = time.time()

    for freq in freq_levels:
        print(f"\n{'='*60}")
        print(f"  Threat landscape freq = {freq}/year  ({ITERATIONS} iterations)")
        print(f"{'='*60}", flush=True)
        t0 = time.time()

        per_control_emergent = defaultdict(list)
        per_control_analytical = {}
        ale_values = []
        breach_counts = []

        args_iter = [(seed, freq, ONE_YEAR) for seed in range(ITERATIONS)]
        # processes=2 + maxtasksperchild=25: macbook-safe
        with mp.Pool(processes=2, maxtasksperchild=25) as pool:
            for i, (ale, breaches, opeff_data) in enumerate(pool.imap_unordered(_worker_iteration, args_iter)):
                ale_values.append(ale)
                breach_counts.append(breaches)
                for cid, (em, an) in opeff_data.items():
                    per_control_emergent[cid].append(em)
                    if cid not in per_control_analytical:
                        per_control_analytical[cid] = an
                if (i + 1) % 25 == 0:
                    elapsed = time.time() - t0
                    print(f"    {i+1}/{ITERATIONS} done ({elapsed:.1f}s)", flush=True)

        elapsed = time.time() - t0

        # Compute per-control divergence
        divergences = []
        control_detail = {}
        for cid in per_control_emergent:
            analytical = per_control_analytical.get(cid, 0.0)
            if analytical <= 0.0 or analytical >= 1.0:
                continue  # skip binary/zero controls
            mean_emergent = sum(per_control_emergent[cid]) / len(per_control_emergent[cid])
            pct_div = (mean_emergent - analytical) / analytical * 100
            divergences.append(pct_div)
            control_detail[cid] = {
                "analytical": round(analytical, 4),
                "mean_emergent": round(mean_emergent, 4),
                "pct_divergence": round(pct_div, 2),
            }

        if divergences:
            sorted_div = sorted(divergences)
            n = len(sorted_div)
            median_div = sorted_div[n // 2] if n % 2 else (sorted_div[n//2 - 1] + sorted_div[n//2]) / 2
        else:
            median_div = 0.0

        mean_ale = sum(ale_values) / len(ale_values) if ale_values else 0
        mean_breaches = sum(breach_counts) / len(breach_counts) if breach_counts else 0

        print(f"  Completed in {elapsed:.1f}s")
        print(f"  Median per-LEC divergence: {median_div:+.1f}%")
        print(f"  Mean ALE: ${mean_ale:,.0f}  |  Mean breaches: {mean_breaches:.1f}")

        all_results["per_level"][str(freq)] = {
            "median_divergence_pct": round(median_div, 2),
            "mean_divergence_pct": round(sum(divergences) / len(divergences), 2) if divergences else 0,
            "min_divergence_pct": round(min(divergences), 2) if divergences else 0,
            "max_divergence_pct": round(max(divergences), 2) if divergences else 0,
            "mean_ale": round(mean_ale, 2),
            "mean_breaches": round(mean_breaches, 2),
            "controls": control_detail,
        }

    total_elapsed = time.time() - total_t0
    print(f"\n{'='*60}")
    print(f"  TOTAL: {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")
    print(f"{'='*60}")

    # Summary table
    print(f"\n{'Freq':>6} | {'Median Div':>10} | {'Mean Div':>10} | {'Mean ALE':>12} | {'Breaches':>8}")
    print("-" * 60)
    for freq in freq_levels:
        r = all_results["per_level"][str(freq)]
        print(f"{freq:6.1f} | {r['median_divergence_pct']:+9.1f}% | {r['mean_divergence_pct']:+9.1f}% | ${r['mean_ale']:>11,.0f} | {r['mean_breaches']:>7.1f}")

    suffix = "" if ITERATIONS == 100 else f"_n{ITERATIONS}"
    out = DATA_DIR / f"threat_freq_sweep{suffix}.json"
    with open(out, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {out}")


if __name__ == "__main__":
    main()
