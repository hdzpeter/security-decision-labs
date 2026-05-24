#!/usr/bin/env python3
"""papers/run_paper_experiments.py

Run three experiments for Paper 1 §6 (Emergent vs Analytical):

  Experiment 1 (§6.1): Emergent OpEff vs analytical OpEff under budget stress
    - 30 iterations × 7 budget levels
    - Per-control emergent OpEff (time-weighted) vs analytical formula
    - Output: papers/data/exp1_opeff_divergence.json

  Experiment 2 (§6.2): Remediation backlog dynamics
    - Default: single 3-year run at 5 budget levels (seed=50)
    - With --seeds N (N>1): N seeds × 5 budgets, aggregate mean + p5/p95 band
    - Remediation queue depth sampled monthly
    - Output: papers/data/exp2_backlog_dynamics.json (single-seed)
              papers/data/exp2_backlog_dynamics_n{N}.json (N>1, per-seed arrays)

  Experiment 3 (§6.3): Cascading variance from narrative data
    - Default: single 5-year run at seed 50 (high-breach seed) — drives fig7
    - With --cascade-seeds N (N>1): ensemble of N seeds × 5-year, per-seed
      cascade-window summaries (count, duration, n undetected LEC variants),
      plus breach/loss summaries. Answers §6.3's deferred question:
      "distribution of cascade-window durations across seeds".
    - Full narrative export: variance events, loss events, linchpin analysis
    - Output: papers/data/exp3_cascading_variance.json (single-seed)
              papers/data/exp3_cascading_variance_n{N}.json (ensemble)

Uses hospital_ransomware_medium scenario.

Usage:
    papers/run_paper_experiments.py [--exp 1|2|3|all] [--seeds N] [--cascade-seeds N] [--iterations N]
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
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("FAIR_CAM_CONFIG", str(PROJECT_ROOT / "inputs" / "model_config.yaml"))

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

SCENARIO = "hospital_ransomware_medium"
ONE_YEAR = 8760
TICKS_PER_MONTH = 730


def load_scenario():
    from src.config.loader import get_config
    from src.data.json_loader import JsonLoader
    get_config()
    p = PROJECT_ROOT / "scenarios" / SCENARIO / "scenario_data.json"
    return JsonLoader(json_path=str(p)).load_all()


def run_model(data, seed, steps, budget_override=None):
    """Run a single simulation, return (model, metrics_state)."""
    from src.model import FAIRCAMModel
    from src.config.loader import get_config

    cfg = get_config()
    overrides = {}
    if budget_override is not None:
        overrides["remediation"] = {"budget_hours_per_month": float(budget_override)}

    with cfg.override(overrides):
        model = FAIRCAMModel(model_data=copy.deepcopy(data), seed=seed, steps=steps, collect_timeseries=False)
        for _ in range(steps):
            model.step()
    return model


# ══════════════════════════════════════════════════════════════════════
# Experiment 1: Emergent OpEff vs Analytical OpEff
# ══════════════════════════════════════════════════════════════════════

def _exp1_worker(args):
    seed, budget, steps = args
    data = load_scenario()
    model = run_model(data, seed=seed, steps=steps, budget_override=budget)
    ale = float(model.metrics_state.total_gross_losses)

    per_control = {}
    for agent in model.schedule.agents:
        cls = agent.__class__.__name__
        if cls not in ("LECAgent", "VMCAgent", "DSCAgent"):
            continue
        cid = str(agent.unique_id)
        intended = float(getattr(agent, "intended_efficacy", 0.0))
        variant_eff = float(getattr(agent, "variant_efficacy", 0.0))

        narrative = model.narrative
        var_events = [v for v in narrative.variance_events if v.control_id == cid]
        recovery_events = []
        if hasattr(narrative, "recovery_events"):
            recovery_events = [r for r in narrative.recovery_events
                               if getattr(r, "control_id", "") == cid]

        total_variance_ticks = 0
        for ve in var_events:
            start = int(ve.tick)
            end = steps
            for re in recovery_events:
                re_tick = int(getattr(re, "tick", steps))
                if re_tick > start:
                    end = re_tick
                    break
            total_variance_ticks += (end - start)

        reliability = 1.0 - (total_variance_ticks / steps)
        reliability = max(0.0, min(1.0, reliability))
        emergent_opeff = reliability * intended + (1.0 - reliability) * variant_eff
        analytical_opeff = reliability * intended + (1.0 - reliability) * variant_eff

        change_freq_params = getattr(agent, "change_freq_dist_params", None)
        if change_freq_params:
            expected_change_hours = float(change_freq_params.get("param2", 4000))
            default_rem = 40
            rem_hours = float(getattr(agent, "params", {}).get(
                "Remediation_Hours", default_rem) or default_rem)
            analytical_rel = expected_change_hours / (expected_change_hours + rem_hours)
            analytical_opeff = analytical_rel * intended + (1.0 - analytical_rel) * variant_eff

        per_control[cid] = (emergent_opeff, analytical_opeff)

    return ale, per_control


def experiment_1(data, iterations=100):
    """Compare emergent vs analytical OpEff across budget levels."""
    print("\n" + "=" * 70)
    print(f"EXPERIMENT 1: Emergent OpEff vs Analytical OpEff (iterations={iterations})")
    print("=" * 70)

    budget_levels = [2, 5, 10, 20, 40, 80, 160]
    results = {"budget_levels": budget_levels, "iterations": iterations, "controls": {}}

    for budget in budget_levels:
        print(f"\n  Budget: {budget} hrs/mo ({iterations} iterations, 2 procs macbook-safe)...", flush=True)
        t0 = time.time()

        per_control_emergent = {}
        per_control_analytical = {}
        ale_values = []

        args_iter = [(i, budget, ONE_YEAR) for i in range(iterations)]
        # processes=2 leaves cores free for OS; maxtasksperchild=25 amortizes fork cost.
        with mp.Pool(processes=2, maxtasksperchild=25) as pool:
            completed = 0
            for ale, per_control in pool.imap_unordered(_exp1_worker, args_iter):
                ale_values.append(ale)
                for cid, (em, an) in per_control.items():
                    per_control_emergent.setdefault(cid, []).append(em)
                    if cid not in per_control_analytical:
                        per_control_analytical[cid] = an
                completed += 1
                if completed % 25 == 0 or completed == iterations:
                    elapsed = time.time() - t0
                    eta = elapsed / completed * (iterations - completed)
                    print(f"    [{completed}/{iterations}] done, {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining", flush=True)

        elapsed = time.time() - t0
        print(f"    Budget {budget} complete in {elapsed:.1f}s. Mean ALE: ${sum(ale_values)/len(ale_values):,.0f}", flush=True)

        # Aggregate per budget level
        for cid in per_control_emergent:
            if cid not in results["controls"]:
                results["controls"][cid] = {
                    "analytical_opeff": per_control_analytical.get(cid, 0.0),
                    "budgets": {},
                }
            emergent_vals = per_control_emergent[cid]
            results["controls"][cid]["budgets"][str(budget)] = {
                "mean_emergent_opeff": sum(emergent_vals) / len(emergent_vals),
                "min_emergent_opeff": min(emergent_vals),
                "max_emergent_opeff": max(emergent_vals),
                "mean_ale": sum(ale_values) / len(ale_values),
            }

    out = DATA_DIR / "exp1_opeff_divergence.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results: {out}")
    return results


# ══════════════════════════════════════════════════════════════════════
# Experiment 2: Remediation Backlog Dynamics
# ══════════════════════════════════════════════════════════════════════

def _exp2_worker(args):
    """Single (seed, budget) 3-year run, returns monthly samples + summary."""
    seed, budget, steps = args
    data = load_scenario()

    from src.model import FAIRCAMModel
    from src.config.loader import get_config

    cfg = get_config()
    overrides = {"remediation": {"budget_hours_per_month": float(budget)}}

    with cfg.override(overrides):
        model = FAIRCAMModel(
            model_data=copy.deepcopy(data), seed=seed, steps=steps,
            collect_timeseries=False,
        )

        queue_depth = []
        variant_count = []
        remediating_count = []
        cumulative_losses = []
        sample_ticks = []

        for t in range(steps):
            model.step()
            if t % TICKS_PER_MONTH == 0 or t == steps - 1:
                sample_ticks.append(t)
                queue_depth.append(len(model.remediation.queue))
                n_variant = 0
                n_remediating = 0
                for agent in model.schedule.agents:
                    if agent.__class__.__name__ in ("LECAgent", "VMCAgent", "DSCAgent"):
                        st = str(getattr(agent, "state", "normal")).lower()
                        if st == "variant":
                            n_variant += 1
                        elif st == "remediating":
                            n_remediating += 1
                variant_count.append(n_variant)
                remediating_count.append(n_remediating)
                cumulative_losses.append(float(model.metrics_state.total_gross_losses))

        final_loss = float(model.metrics_state.total_gross_losses)
        total_breaches = int(model.metrics_state.total_breach_events)
        total_variance = int(model.metrics_state.total_variance_events)

    result = {
        "seed": seed,
        "budget": budget,
        "sample_ticks": sample_ticks,
        "queue_depth": queue_depth,
        "variant_count": variant_count,
        "remediating_count": remediating_count,
        "cumulative_losses": cumulative_losses,
        "final_gross_loss": final_loss,
        "total_breaches": total_breaches,
        "total_variance_events": total_variance,
    }

    # Release 3-year narrative accumulation explicitly before worker returns —
    # prevents VM pressure buildup across seeds when maxtasksperchild > 1.
    if hasattr(model, "narrative"):
        model.narrative = None
    del model
    gc.collect()

    return result


def experiment_2(data, n_seeds: int = 1):
    """Track remediation queue depth over time at different budget levels.

    n_seeds=1: single-seed (seed=50) — matches original single-seed output schema.
    n_seeds>1: N seeds (0..N-1), per-seed arrays stored for downstream CI aggregation.
    """
    print("\n" + "=" * 70)
    print(f"EXPERIMENT 2: Remediation Backlog Dynamics (n_seeds={n_seeds})")
    print("=" * 70)

    budget_levels = [2, 5, 10, 20, 40]
    three_years = ONE_YEAR * 3

    if n_seeds == 1:
        results = {"budget_levels": budget_levels, "steps": three_years, "runs": {}}
        for budget in budget_levels:
            print(f"\n  Budget: {budget} hrs/mo (3-year run, seed=50)...")
            t0 = time.time()
            out = _exp2_worker((50, budget, three_years))
            elapsed = time.time() - t0
            print(f"    Completed in {elapsed:.1f}s. 3-year gross loss: ${out['final_gross_loss']:,.0f}")
            print(f"    Max queue depth: {max(out['queue_depth'])}, max variant: {max(out['variant_count'])}")
            results["runs"][str(budget)] = {
                "sample_ticks": out["sample_ticks"],
                "queue_depth": out["queue_depth"],
                "variant_count": out["variant_count"],
                "remediating_count": out["remediating_count"],
                "cumulative_losses": out["cumulative_losses"],
                "final_gross_loss": out["final_gross_loss"],
                "total_breaches": out["total_breaches"],
                "total_variance_events": out["total_variance_events"],
            }
            gc.collect()

        out_path = DATA_DIR / "exp2_backlog_dynamics.json"
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n  Results: {out_path}")
        return results

    # Multi-seed path
    seeds = list(range(n_seeds))
    results = {
        "budget_levels": budget_levels,
        "steps": three_years,
        "seeds_used": seeds,
        "n_seeds": n_seeds,
        "runs": {},
    }

    for budget in budget_levels:
        print(f"\n  Budget: {budget} hrs/mo — {n_seeds} seeds × 3-year, 2 procs (macbook-safe)...")
        t0 = time.time()
        args_iter = [(s, budget, three_years) for s in seeds]

        per_seed_queue = []
        per_seed_variant = []
        per_seed_remediating = []
        per_seed_cumulative = []
        per_seed_final_loss = []
        per_seed_breaches = []
        per_seed_variance_events = []
        sample_ticks_ref = None

        completed = 0
        # processes=2 leaves cores free for OS + page compressor;
        # maxtasksperchild=25 amortizes fork cost 25x while still bounding per-child growth.
        with mp.Pool(processes=2, maxtasksperchild=25) as pool:
            for r in pool.imap_unordered(_exp2_worker, args_iter, chunksize=1):
                if sample_ticks_ref is None:
                    sample_ticks_ref = r["sample_ticks"]
                per_seed_queue.append(r["queue_depth"])
                per_seed_variant.append(r["variant_count"])
                per_seed_remediating.append(r["remediating_count"])
                per_seed_cumulative.append(r["cumulative_losses"])
                per_seed_final_loss.append(r["final_gross_loss"])
                per_seed_breaches.append(r["total_breaches"])
                per_seed_variance_events.append(r["total_variance_events"])
                completed += 1
                if completed % 50 == 0 or completed == n_seeds:
                    elapsed = time.time() - t0
                    eta = elapsed / completed * (n_seeds - completed)
                    print(f"    [{completed}/{n_seeds}] seeds done, {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining", flush=True)

        elapsed = time.time() - t0
        mean_final_loss = sum(per_seed_final_loss) / len(per_seed_final_loss)
        print(f"    Budget {budget} complete in {elapsed:.0f}s. Mean 3-year gross loss: ${mean_final_loss:,.0f}")

        results["runs"][str(budget)] = {
            "sample_ticks": sample_ticks_ref,
            "per_seed_queue_depth": per_seed_queue,
            "per_seed_variant_count": per_seed_variant,
            "per_seed_remediating_count": per_seed_remediating,
            "per_seed_cumulative_losses": per_seed_cumulative,
            "per_seed_final_gross_loss": per_seed_final_loss,
            "per_seed_total_breaches": per_seed_breaches,
            "per_seed_total_variance_events": per_seed_variance_events,
        }
        gc.collect()

    out_path = DATA_DIR / f"exp2_backlog_dynamics_n{n_seeds}.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results: {out_path}")
    return results


# ══════════════════════════════════════════════════════════════════════
# Experiment 3: Cascading Variance
# ══════════════════════════════════════════════════════════════════════

def _add_cascade_window(windows, vmc_id, start, end, monitored, variance_events):
    """Helper: check if any monitored LECs went variant during a VMC variant window."""
    lec_variants_during = []
    for ve in variance_events:
        if ve["control_id"] in monitored and start <= ve["tick"] < end:
            lec_variants_during.append(ve)
    if lec_variants_during:
        windows.append({
            "vmc_id": vmc_id,
            "vmc_variant_start": start,
            "vmc_variant_end": end,
            "duration_hours": end - start,
            "undetected_lec_variants": lec_variants_during,
        })


def _compute_cascade_summary(model, control_states, variance_events):
    """Compute lightweight cascade-window summary from a single model run.

    Returns a list of {vmc_id, start_tick, duration_hours, n_undetected_lec_variants}.
    Used by both single-seed (experiment_3) and ensemble (_exp3_worker) paths.
    """
    net = model.network
    windows = []
    for cid, cs in control_states.items():
        if cs["type"] != "VMC":
            continue
        monitored = []
        try:
            monitored = [str(getattr(c, "unique_id", ""))
                         for c in (net.get_monitored_controls(cid) or [])]
        except Exception:
            pass
        vmc_variant_start = None
        for tick, state in zip(cs["ticks"], cs["state"]):
            if state in ("variant", "remediating") and vmc_variant_start is None:
                vmc_variant_start = tick
            elif state not in ("variant", "remediating") and vmc_variant_start is not None:
                n_lecs = sum(1 for ve in variance_events
                             if ve["control_id"] in monitored
                             and vmc_variant_start <= ve["tick"] < tick)
                if n_lecs > 0:
                    windows.append({
                        "vmc_id": cid,
                        "start_tick": vmc_variant_start,
                        "duration_hours": tick - vmc_variant_start,
                        "n_undetected_lec_variants": n_lecs,
                    })
                vmc_variant_start = None
        if vmc_variant_start is not None and cs["ticks"]:
            end_tick = cs["ticks"][-1]
            n_lecs = sum(1 for ve in variance_events
                         if ve["control_id"] in monitored
                         and vmc_variant_start <= ve["tick"] < end_tick)
            if n_lecs > 0:
                windows.append({
                    "vmc_id": cid,
                    "start_tick": vmc_variant_start,
                    "duration_hours": end_tick - vmc_variant_start,
                    "n_undetected_lec_variants": n_lecs,
                })
    return windows


def _exp3_worker(args):
    """Single-seed 5-year cascade run. Returns lightweight per-seed summary
    only — does NOT retain control_states timeseries or full narratives."""
    seed, steps = args
    data = load_scenario()

    from src.model import FAIRCAMModel
    from src.config.loader import get_config

    cfg = get_config()
    overrides = {"threat_landscape": {"affect_detection_controls": True}}
    SAMPLE_INTERVAL = 24

    with cfg.override(overrides):
        model = FAIRCAMModel(
            model_data=copy.deepcopy(data), seed=seed, steps=steps,
            collect_timeseries=False,
        )

        control_states = {}
        for t in range(steps):
            model.step()
            if t % SAMPLE_INTERVAL == 0:
                for agent in model.schedule.agents:
                    cls = agent.__class__.__name__
                    if cls not in ("LECAgent", "VMCAgent", "DSCAgent"):
                        continue
                    cid = str(agent.unique_id)
                    if cid not in control_states:
                        control_states[cid] = {
                            "type": cls.replace("Agent", ""),
                            "ticks": [], "state": [],
                        }
                    control_states[cid]["ticks"].append(t)
                    control_states[cid]["state"].append(str(getattr(agent, "state", "normal")))

        variance_events = [
            {"control_id": v.control_id, "tick": int(v.tick)}
            for v in model.narrative.variance_events
        ]
        cascade_windows = _compute_cascade_summary(model, control_states, variance_events)

        summary = {
            "seed": seed,
            "breaches": int(model.metrics_state.total_breach_events),
            "loss_events": int(model.metrics_state.total_loss_events),
            "variance_events_count": int(model.metrics_state.total_variance_events),
            "gross_losses": float(model.metrics_state.total_gross_losses),
            "cascade_windows": cascade_windows,
        }

    if hasattr(model, "narrative"):
        model.narrative = None
    del model, control_states, variance_events
    gc.collect()
    return summary


def experiment_3(data, n_seeds: int = 1):
    """Extract narrative cascade data showing VMC-LEC cascade effects.

    Uses a 5-year horizon to allow VMC drift (VMC change frequencies are
    15,000-35,000 hours = 1.7-4 years). Enables affect_detection_controls
    so extrinsic variance (threat landscape) also hits VMCs — the realistic
    scenario where zero-days affect monitoring tools, not just prevention.

    n_seeds=1: single-seed (seed=50) full-detail run — drives fig7.
    n_seeds>1: ensemble of seeds 0..N-1, per-seed cascade summaries only.
    """
    print("\n" + "=" * 70)
    print(f"EXPERIMENT 3: Cascading Variance Patterns (n_seeds={n_seeds})")
    print("=" * 70)

    if n_seeds > 1:
        seeds = list(range(n_seeds))
        five_years = ONE_YEAR * 5
        args_iter = [(s, five_years) for s in seeds]
        per_seed = []
        t0 = time.time()
        completed = 0
        print(f"  Ensemble: {n_seeds} seeds × 5-year, 2 procs (macbook-safe)...")
        with mp.Pool(processes=2, maxtasksperchild=25) as pool:
            for r in pool.imap_unordered(_exp3_worker, args_iter, chunksize=1):
                per_seed.append(r)
                completed += 1
                if completed % 25 == 0 or completed == n_seeds:
                    elapsed = time.time() - t0
                    eta = elapsed / completed * (n_seeds - completed)
                    print(f"    [{completed}/{n_seeds}] seeds done, {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining", flush=True)

        per_seed.sort(key=lambda r: r["seed"])
        out = {
            "experiment": "cascade_ensemble",
            "n_seeds": n_seeds,
            "steps": five_years,
            "config_overrides": {"affect_detection_controls": True},
            "per_seed": per_seed,
        }
        out_path = DATA_DIR / f"exp3_cascading_variance_n{n_seeds}.json"
        with open(out_path, "w") as f:
            json.dump(out, f, indent=2)
        total_elapsed = time.time() - t0
        seeds_with_cascades = sum(1 for r in per_seed if r["cascade_windows"])
        total_windows = sum(len(r["cascade_windows"]) for r in per_seed)
        total_breaches = sum(r["breaches"] for r in per_seed)
        print(f"\n  Ensemble complete in {total_elapsed:.0f}s")
        print(f"  Seeds with >=1 cascade: {seeds_with_cascades}/{n_seeds} ({seeds_with_cascades/n_seeds*100:.0f}%)")
        print(f"  Total cascade windows: {total_windows}, total breaches: {total_breaches}")
        print(f"  Results: {out_path}")
        return out

    from src.model import FAIRCAMModel
    from src.config.loader import get_config

    five_years = ONE_YEAR * 5
    cfg = get_config()

    # Enable VMC vulnerability to threat landscape changes for cascade effect
    overrides = {"threat_landscape": {"affect_detection_controls": True}}

    with cfg.override(overrides):
        model = FAIRCAMModel(model_data=copy.deepcopy(data), seed=50, steps=five_years, collect_timeseries=False)

    # Per-control state timeline (sampled every 24 hours)
    SAMPLE_INTERVAL = 24  # hourly is too much data; every 24h is ~365 samples
    control_states = {}  # control_id -> {"ticks": [], "state": [], "efficacy": []}
    sample_ticks = []

    t0 = time.time()
    for t in range(five_years):
        model.step()

        if t % SAMPLE_INTERVAL == 0:
            sample_ticks.append(t)
            for agent in model.schedule.agents:
                cls = agent.__class__.__name__
                if cls not in ("LECAgent", "VMCAgent", "DSCAgent"):
                    continue
                cid = str(agent.unique_id)
                if cid not in control_states:
                    control_states[cid] = {
                        "type": cls.replace("Agent", ""),
                        "ticks": [],
                        "state": [],
                        "efficacy": [],
                    }
                control_states[cid]["ticks"].append(t)
                control_states[cid]["state"].append(str(getattr(agent, "state", "normal")))
                control_states[cid]["efficacy"].append(float(getattr(agent, "current_efficacy", 0.0)))

    elapsed = time.time() - t0
    print(f"  Run completed in {elapsed:.1f}s")
    print(f"  Breaches: {model.metrics_state.total_breach_events}")
    print(f"  Loss events: {model.metrics_state.total_loss_events}")
    print(f"  Variance events: {model.metrics_state.total_variance_events}")
    print(f"  Gross losses: ${model.metrics_state.total_gross_losses:,.0f}")

    # Extract narrative
    narrative_export = {}
    try:
        narrative_export = model.narrative.export_narratives()
    except Exception as e:
        print(f"  WARNING: narrative export failed: {e}")

    # Extract variance events with timing
    variance_events = []
    for v in model.narrative.variance_events:
        variance_events.append({
            "control_id": v.control_id,
            "tick": int(v.tick),
            "change_type": str(getattr(v, "change_type", "")),
            "cause": str(getattr(v, "cause", "")),
            "variance_source": str(getattr(v, "variance_source", "")),
            "intended_efficacy": float(getattr(v, "intended_efficacy", 0.0)),
            "variant_efficacy": float(getattr(v, "variant_efficacy", 0.0)),
        })

    # Extract loss events with root causes
    loss_events = []
    for l in model.narrative.loss_events:
        loss_events.append({
            "business_asset_id": str(getattr(l, "business_asset_id", "")),
            "tech_asset_id": str(getattr(l, "tech_asset_id", "")),
            "breach_tick": int(getattr(l, "breach_tick", 0)),
            "loss_tick": int(getattr(l, "loss_tick", 0)),
            "gross_loss": float(getattr(l, "gross_loss", 0.0)),
            "detected": bool(getattr(l, "detected", True)),
            "root_variance_events": list(getattr(l, "root_variance_events", [])),
            "variant_controls_at_breach": list(getattr(l, "variant_controls_at_breach", [])),
        })

    # Linchpin VMCs (from narrative if available)
    linchpins = {}
    if hasattr(model.narrative, "linchpin_analysis"):
        try:
            linchpins = model.narrative.linchpin_analysis()
        except Exception:
            pass
    elif "linchpin_vmcs" in narrative_export:
        linchpins = narrative_export.get("linchpin_vmcs", {})

    # Build cascade windows: periods where a VMC was variant AND
    # the LECs it monitors accumulated undetected variance
    cascade_windows = []
    net = model.network
    for cid, cs in control_states.items():
        if cs["type"] != "VMC":
            continue

        # Get controls monitored by this VMC
        monitored = []
        try:
            monitored = [str(getattr(c, "unique_id", ""))
                         for c in (net.get_monitored_controls(cid) or [])]
        except Exception:
            pass

        # Find windows where this VMC was variant
        vmc_variant_start = None
        for i, (tick, state) in enumerate(zip(cs["ticks"], cs["state"])):
            if state in ("variant", "remediating") and vmc_variant_start is None:
                vmc_variant_start = tick
            elif state not in ("variant", "remediating") and vmc_variant_start is not None:
                # Window ended
                _add_cascade_window(cascade_windows, cid, vmc_variant_start, tick,
                                    monitored, variance_events)
                vmc_variant_start = None

        # Handle VMC still variant at end of run
        if vmc_variant_start is not None:
            _add_cascade_window(cascade_windows, cid, vmc_variant_start,
                                cs["ticks"][-1], monitored, variance_events)

    print(f"  Cascade windows found: {len(cascade_windows)}")

    results = {
        "seed": 50,
        "steps": five_years,
        "config_overrides": {"affect_detection_controls": True},
        "summary": {
            "breaches": int(model.metrics_state.total_breach_events),
            "loss_events": int(model.metrics_state.total_loss_events),
            "variance_events_count": int(model.metrics_state.total_variance_events),
            "gross_losses": float(model.metrics_state.total_gross_losses),
        },
        "control_states": control_states,
        "variance_events": variance_events,
        "loss_events": loss_events,
        "cascade_windows": cascade_windows,
        "linchpins": linchpins,
    }

    del model
    gc.collect()

    out = DATA_DIR / "exp3_cascading_variance.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results: {out}")
    return results


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Run Paper 1 §6 experiments")
    parser.add_argument("--exp", type=str, default="all",
                        help="Which experiment to run: 1, 2, 3, or all (default: all)")
    parser.add_argument("--seeds", type=int, default=1,
                        help="Number of seeds for experiment 2 (default: 1 = single-seed, preserves original schema)")
    parser.add_argument("--iterations", type=int, default=100,
                        help="Number of iterations for experiment 1 (default: 100, matches paper §6.1)")
    parser.add_argument("--cascade-seeds", type=int, default=1,
                        help="Number of seeds for experiment 3 ensemble (default: 1 = single-seed=50 preserves fig7 data source)")
    args = parser.parse_args()

    import logging
    logging.basicConfig(level=logging.WARNING)

    print(f"Loading scenario: {SCENARIO}")
    data = load_scenario()
    print(f"  Loaded. Controls: {sum(1 for r in data.get('lec_params', []) or [])}"
          f" LECs, {sum(1 for r in data.get('vmc_params', []) or [])} VMCs,"
          f" {sum(1 for r in data.get('dsc_params', []) or [])} DSCs")

    run = args.exp.strip().lower()
    t_total = time.time()

    if run in ("1", "all"):
        experiment_1(data, iterations=args.iterations)
    if run in ("2", "all"):
        experiment_2(data, n_seeds=args.seeds)
    if run in ("3", "all"):
        experiment_3(data, n_seeds=args.cascade_seeds)

    print(f"\nTotal time: {time.time() - t_total:.1f}s")
    print(f"Data directory: {DATA_DIR}/")


if __name__ == "__main__":
    main()
