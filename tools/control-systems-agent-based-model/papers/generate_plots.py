#!/usr/bin/env python3
"""Generate all figures for Paper 1.

  fig1 — Budget sensitivity (two panels: ALE + breaches)
  fig2 — Loss distribution (CDF + exceedance curve)
  fig3 — Control state distribution timeline (stacked area, Seed 50)
  fig4 — Contact-breach funnel (weak vs medium)
  fig5 — OpEff divergence (grouped bar: analytical vs emergent)
  fig6 — Backlog dynamics (mean trajectory + CI band by budget)
  fig7 — Cascade timeline (per-control state over 5 years)

Color palette: Classic Red / Benedict Evans
"""

import copy
import gc
import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("FAIR_CAM_CONFIG", str(PROJECT_ROOT / "inputs" / "model_config.yaml"))

FIGURES_DIR = Path(__file__).parent / "figures"
DATA_DIR = Path(__file__).parent / "data"
SCENARIO_DIR = Path(__file__).parent.parent / "scenarios"
FIGURES_DIR.mkdir(exist_ok=True)

# ── Color palette (Classic Red / Benedict Evans) ──
PRIMARY = "#1A1A1A"       # Primary text
ACCENT = "#E74C3C"        # Accent red
DARK_BG = "#34495E"       # Dark blue-gray
LIGHT_GRAY = "#95A5A6"    # Light gray
MED_GRAY = "#7F8C8D"      # Medium gray
VERY_LIGHT = "#BDC3C7"    # Very light gray
MED_BG = "#E0E0E0"        # Medium background

# fig3 stacked-area palette
STATE_NORMAL = "#2A9D8F"       # teal
STATE_VARIANT = "#C1553A"      # rust
STATE_REMEDIATING = "#D4A373"  # warm tan

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "axes.spines.top": False,
    "axes.spines.right": False,
})


# ── Helpers ──────────────────────────────────────────────────────────

def load_scenario(name):
    from src.config.loader import get_config
    from src.data.json_loader import JsonLoader
    get_config()
    p = PROJECT_ROOT / "scenarios" / name / "scenario_data.json"
    return JsonLoader(json_path=str(p)).load_all()


def run_one(data, seed, steps):
    from src.model import FAIRCAMModel
    model = FAIRCAMModel(model_data=copy.deepcopy(data), seed=seed, steps=steps)
    for _ in range(steps):
        model.step()
    result = {
        "total_gross_losses": float(model.metrics_state.total_gross_losses),
        "total_breach_events": int(model.metrics_state.total_breach_events),
        "total_contact_attempts": int(model.metrics_state.total_contact_attempts),
        "total_avoided_contacts": int(model.metrics_state.total_avoided_contacts),
        "total_resisted_events": int(model.metrics_state.total_resisted_events),
        "total_deterred_events": int(model.metrics_state.total_deterred_events),
    }
    del model
    gc.collect()
    return result


def _count_total_controls(scenario_name: str = "hospital_ransomware_medium") -> int:
    scen_path = SCENARIO_DIR / scenario_name / "scenario_data.json"
    with open(scen_path) as f:
        d = json.load(f)
    return len(d.get("lec", [])) + len(d.get("vmc", [])) + len(d.get("dsc", []))


# ── Figure 1: Budget Sensitivity — Two Clean Panels ──────────────────

def plot_budget_sensitivity():
    """Two-panel: Mean/P95 ALE (left) and breach count (right).

    Separate panels avoid the dual-axis readability problem.
    """
    print("Figure 1: Budget sensitivity (two panels)...")

    # Prefer highest-N budget_sensitivity file when available (N=500 ensemble),
    # fall back to hardcoded N=100 values.
    budgets = [2, 5, 10, 20, 40, 80, 160]
    multi = sorted(DATA_DIR.glob("budget_sensitivity_n*.json"),
                   key=lambda p: int(p.stem.split("_n")[-1]))
    src = multi[-1] if multi else (DATA_DIR / "budget_sensitivity.json")
    if src.exists():
        with open(src) as f:
            bs = json.load(f)
        runs = bs.get("runs", {})
        mean_ale = [int(runs[str(b)]["mean_ale"]) for b in budgets]
        p95_ale = [int(runs[str(b)]["p95_ale"]) for b in budgets]
        breaches = [int(runs[str(b)]["total_breaches"]) for b in budgets]
        print(f"  -> loaded from {src.name}")
    else:
        mean_ale = [247601, 247601, 118930, 140599, 120780, 120780, 120780]
        p95_ale = [1437514, 1437514, 920003, 965579, 920003, 920003, 920003]
        breaches = [49, 49, 24, 29, 25, 25, 25]
        print("  -> using hardcoded N=100 fallback")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.5))

    # Left: ALE
    ax1.plot(budgets, [x/1000 for x in mean_ale], "o-", color=DARK_BG,
             linewidth=2, markersize=6, label="Mean ALE", zorder=3)
    ax1.plot(budgets, [x/1000 for x in p95_ale], "s--", color=ACCENT,
             linewidth=1.5, markersize=5, label="P95 ALE", zorder=3)
    ax1.set_xlabel("Remediation Budget (hours/month)")
    ax1.set_ylabel("Annual Loss ($K)")
    ax1.set_xticks(budgets)
    ax1.set_xticklabels([str(b) for b in budgets])
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}K"))
    ax1.legend(loc="upper right", fontsize=8)
    ax1.set_title("Loss vs Budget")

    # Threshold zone
    ax1.axvspan(0, 7, alpha=0.08, color=ACCENT)
    ax1.annotate("Degraded\nregime", xy=(4, max(mean_ale)/1000 * 0.7),
                 fontsize=8, color=ACCENT, ha="center", style="italic")

    # Right: Breaches
    colors = [ACCENT if b > 30 else (LIGHT_GRAY if b > 25 else DARK_BG) for b in breaches]
    ax2.bar(range(len(budgets)), breaches, color=colors, edgecolor="white", alpha=0.85)
    ax2.set_xticks(range(len(budgets)))
    ax2.set_xticklabels([str(b) for b in budgets])
    ax2.set_xlabel("Remediation Budget (hours/month)")
    ax2.set_ylabel("Total Breaches")
    ax2.set_title("Breaches vs Budget")

    # Annotate threshold
    ax2.axhline(25, color=VERY_LIGHT, linestyle=":", linewidth=0.8)
    ax2.text(6.5, 26, "Baseline (40 hrs/mo)", fontsize=7, color=MED_GRAY,
             ha="right", va="bottom")

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "fig1_budget_sensitivity.pdf")
    fig.savefig(FIGURES_DIR / "fig1_budget_sensitivity.png")
    plt.close(fig)
    print("  -> Done")


# ── Figure 2: Loss Distribution — CDF + Exceedance ──────────────────

def plot_loss_distribution():
    """CDF and loss exceedance curve.

    Uses 1000-iteration data if available, falls back to running 100.
    """
    print("Figure 2: Loss distribution (CDF + exceedance)...")

    # Prefer scenario_comparison_n{N}.json for medium loss distribution when available.
    multi = sorted(DATA_DIR.glob("scenario_comparison_n*.json"),
                   key=lambda p: int(p.stem.split("_n")[-1]))
    src = multi[-1] if multi else (DATA_DIR / "scenario_comparison.json")
    if src.exists() and "per_seed" in (json.load(open(src)).get("medium") or {}):
        with open(src) as f:
            sc = json.load(f)
        losses = np.array(sc["medium"]["per_seed"]["gross_loss"])
        print(f"  -> loaded from {src.name} ({len(losses)} iterations)")
    else:
        data_file = DATA_DIR / "medium_1000_iterations.json"
        if data_file.exists():
            print("  Using pre-computed 1000-iteration data")
            with open(data_file) as f:
                d = json.load(f)
            losses = np.array(d["losses"])
        else:
            print("  Running 100 iterations...")
            data = load_scenario("hospital_ransomware_medium")
            losses = []
            for i in range(100):
                res = run_one(data, seed=i, steps=8760)
                losses.append(res["total_gross_losses"])
                if (i + 1) % 20 == 0:
                    print(f"    {i+1}/100 complete")
            losses = np.array(losses)

    n = len(losses)
    n_zero = int(np.sum(losses == 0))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    # Left: CDF
    sorted_losses = np.sort(losses)
    cdf = np.arange(1, n + 1) / n
    ax1.step(sorted_losses / 1e6, cdf, color=DARK_BG, linewidth=1.5, where="post")
    ax1.fill_between(sorted_losses / 1e6, 0, cdf, alpha=0.1, color=DARK_BG, step="post")

    # Mark key percentiles
    for pct, color, label in [(50, MED_GRAY, "Median"), (95, ACCENT, "P95"), (99, LIGHT_GRAY, "P99")]:
        val = np.percentile(losses, pct) / 1e6
        ax1.axhline(pct / 100, color=color, linestyle=":", linewidth=0.8, alpha=0.5)
        ax1.axvline(val, color=color, linestyle=":", linewidth=0.8, alpha=0.5)
        ax1.plot(val, pct / 100, "o", color=color, markersize=5, zorder=5)
        ax1.text(val + 0.1, pct / 100 - 0.03, f"{label}: ${val:.2f}M",
                 fontsize=7, color=color, va="top")

    ax1.set_xlabel("Annual Loss ($M)")
    ax1.set_ylabel("Cumulative Probability")
    ax1.set_title(f"Loss CDF ({n} iterations)")
    ax1.set_xlim(-0.1, max(losses) / 1e6 * 1.1)

    # Annotate zero-loss fraction
    ax1.text(0.05, 0.15, f"{n_zero}/{n} iterations\nzero loss ({n_zero/n*100:.0f}%)",
             transform=ax1.transAxes, fontsize=9, color=DARK_BG,
             fontweight="bold", va="bottom",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=DARK_BG, alpha=0.8))

    # Right: Loss Exceedance Curve (1 - CDF)
    exceedance = 1 - cdf
    # Filter to nonzero for cleaner plot
    mask = sorted_losses > 0
    if np.any(mask):
        ax2.semilogy(sorted_losses[mask] / 1e6, exceedance[mask],
                     color=ACCENT, linewidth=1.5)
        ax2.fill_between(sorted_losses[mask] / 1e6, exceedance[mask],
                         alpha=0.1, color=ACCENT)

    # Mark thresholds
    for threshold, label in [(0.5, "$500K"), (1.0, "$1M"), (2.0, "$2M"), (5.0, "$5M")]:
        exceed_pct = np.mean(losses > threshold * 1e6) * 100
        if exceed_pct > 0:
            ax2.axvline(threshold, color=VERY_LIGHT, linestyle=":", linewidth=0.7)
            ax2.text(threshold, ax2.get_ylim()[1] * 0.7,
                     f"{label}\n({exceed_pct:.1f}%)", fontsize=7, color=MED_GRAY,
                     ha="center", va="top")

    ax2.set_xlabel("Loss Threshold ($M)")
    ax2.set_ylabel("P(Loss > Threshold)")
    ax2.set_title("Loss Exceedance Curve")
    ax2.set_xlim(0, max(losses) / 1e6 * 1.1)
    ax2.set_ylim(bottom=1 / (n * 2))
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda y, _: f"{y*100:.1f}%" if y >= 0.01 else f"{y*100:.2f}%"))

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "fig2_loss_distribution.pdf")
    fig.savefig(FIGURES_DIR / "fig2_loss_distribution.png")
    plt.close(fig)
    print("  -> Done")


# ── Figure 3: Control State Distribution Over Time (Seed 50) ────────

def plot_variance_timeline(budget: str = "40", months: int = 12,
                           scenario_name: str = "hospital_ransomware_medium"):
    """Fig3: stacked-area control state counts (Normal/Variant/Remediating) over first 12 months.

    Reuses exp2_backlog_dynamics.json at the baseline budget (40 hrs/mo). Seed=50 is the
    high-breach seed used throughout §6.2/§6.3 — fig3 uses the same trajectory to set up
    the paper's control-drift narrative.
    """
    print("Figure 3: Control state distribution timeline...")

    with open(DATA_DIR / "exp2_backlog_dynamics.json") as f:
        d = json.load(f)

    if budget not in d["runs"]:
        raise KeyError(f"Budget {budget} not found in exp2 runs: {list(d['runs'].keys())}")

    run = d["runs"][budget]
    total = _count_total_controls(scenario_name)

    n = min(months + 1, len(run["sample_ticks"]))
    sample_months = [t / 730.0 for t in run["sample_ticks"][:n]]
    variant = np.array(run["variant_count"][:n], dtype=float)
    remediating = np.array(run["remediating_count"][:n], dtype=float)
    normal = np.full_like(variant, total) - variant - remediating

    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.stackplot(
        sample_months,
        normal,
        variant,
        remediating,
        labels=["Normal", "Variant", "Remediating"],
        colors=[STATE_NORMAL, STATE_VARIANT, STATE_REMEDIATING],
        alpha=0.9,
        edgecolor="white",
        linewidth=0.5,
    )

    ax.set_xlabel("Month")
    ax.set_ylabel("Number of Controls")
    ax.set_title("Control State Distribution Over Time (Seed 50)")
    ax.set_xlim(0, max(sample_months))
    ax.set_ylim(0, total + 1)
    ax.legend(loc="upper right", frameon=True, framealpha=0.95)

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "fig3_variance_timeline.pdf")
    fig.savefig(FIGURES_DIR / "fig3_variance_timeline.png")
    plt.close(fig)
    print(f"  -> total={total}, first-month normal={normal[0]:.0f}, variant={variant[0]:.0f}")
    print("  -> Done")


# ── Figure 4: Contact-Breach Funnel ──────────────────────────────────

def plot_contact_funnel():
    """Contact-breach funnel comparing weak vs medium scenarios."""
    print("Figure 4: Contact-breach funnel...")

    categories = ["Contacts", "Avoided", "Resisted", "Breached"]

    # Prefer N=500 scenario_comparison when available
    multi = sorted(DATA_DIR.glob("scenario_comparison_n*.json"),
                   key=lambda p: int(p.stem.split("_n")[-1]))
    src = multi[-1] if multi else (DATA_DIR / "scenario_comparison.json")
    if src.exists():
        with open(src) as f:
            sc = json.load(f)
        w, m = sc["weak"], sc["medium"]
        weak = [w["mean_contacts"], w["mean_avoided"], w["mean_resisted"], w["mean_breaches"]]
        medium = [m["mean_contacts"], m["mean_avoided"], m["mean_resisted"], m["mean_breaches"]]
        print(f"  -> loaded from {src.name}")
    else:
        weak = [96.2, 0.0, 51.9, 44.2]
        medium = [56.1, 26.7, 29.1, 0.25]

    x = np.arange(len(categories))
    width = 0.35

    fig, ax = plt.subplots(figsize=(7, 4))

    ax.bar(x - width/2, weak, width, label="Weak controls",
           color=ACCENT, alpha=0.85, edgecolor="white")
    ax.bar(x + width/2, medium, width, label="Medium controls",
           color=DARK_BG, alpha=0.85, edgecolor="white")

    ax.set_ylabel("Mean Events per Year")
    ax.set_title("Threat Event Pipeline: Weak vs Medium Controls")
    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.legend()

    # Annotate breach values
    for i, (w, m) in enumerate(zip(weak, medium)):
        if categories[i] == "Breached":
            ax.text(i - width/2, w + 1.5, f"{w:.1f}", ha="center", va="bottom",
                    fontsize=9, fontweight="bold", color=ACCENT)
            ax.text(i + width/2, m + 1.5, f"{m:.2f}", ha="center", va="bottom",
                    fontsize=9, fontweight="bold", color=DARK_BG)

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "fig4_contact_funnel.pdf")
    fig.savefig(FIGURES_DIR / "fig4_contact_funnel.png")
    plt.close(fig)
    print("  -> Done")


# ── Figure 5: OpEff Divergence — Grouped Bar Chart ──────────────────

def plot_opeff_divergence():
    """§6.1: Grouped bar chart showing analytical vs emergent OpEff per control.

    Much clearer than the old line chart — directly shows the gap for each control.
    Uses 40 hrs/mo (baseline budget) data.
    """
    print("Figure 5: OpEff divergence (bar chart)...")

    with open(DATA_DIR / "exp1_opeff_divergence.json") as f:
        d = json.load(f)

    # Filter: probability-based controls, skip time-based and perfect (1.0)
    controls = []
    for cid, ctrl in sorted(d["controls"].items()):
        a = ctrl["analytical_opeff"]
        if not (0.05 < a < 0.995):
            continue
        if not cid.startswith("LEC"):
            continue
        e = ctrl["budgets"]["40"]["mean_emergent_opeff"]
        controls.append((cid, a, e))

    if not controls:
        print("  No suitable controls found")
        return

    # Sort by analytical value descending
    controls.sort(key=lambda x: x[1], reverse=True)
    controls = controls[:8]  # limit for readability

    labels = [c[0] for c in controls]
    analytical = [c[1] for c in controls]
    emergent = [c[2] for c in controls]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 4))

    bars_a = ax.bar(x - width/2, analytical, width, label="Analytical (FAIR-CAM formula)",
                    color=VERY_LIGHT, edgecolor="white", alpha=0.9)
    bars_e = ax.bar(x + width/2, emergent, width, label="Emergent (simulation, 40 hrs/mo)",
                    color=DARK_BG, edgecolor="white", alpha=0.9)

    # Annotate divergence percentage on each pair
    for i, (a, e) in enumerate(zip(analytical, emergent)):
        if a > 0.01:
            div = (e - a) / a * 100
            y_pos = max(a, e) + 0.02
            ax.text(i, y_pos, f"{div:+.0f}%", ha="center", va="bottom",
                    fontsize=7, color=ACCENT, fontweight="bold")

    ax.set_ylabel("Operational Efficacy")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylim(0, 1.1)
    ax.legend(loc="upper right")
    ax.set_title("Emergent vs Analytical OpEff (probability-based LECs, 40 hrs/mo budget)")

    # Median divergence annotation
    divs = [(e - a) / a * 100 for _, a, e in controls if a > 0.01]
    median_div = sorted(divs)[len(divs) // 2]
    ax.text(0.02, 0.02, f"Median divergence: {median_div:+.0f}%",
            transform=ax.transAxes, fontsize=9, color=ACCENT,
            style="italic", verticalalignment="bottom")

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "fig5_opeff_divergence.pdf")
    fig.savefig(FIGURES_DIR / "fig5_opeff_divergence.png")
    plt.close(fig)
    print("  -> Done")


# ── Figure 6: Backlog Dynamics — Cleaner Two-Panel ──────────────────

def _find_backlog_data():
    """Return (path, is_multi_seed). Prefer highest-N multi-seed file, else single-seed."""
    multi = sorted(DATA_DIR.glob("exp2_backlog_dynamics_n*.json"),
                   key=lambda p: int(p.stem.split("_n")[-1]))
    if multi:
        return multi[-1], True
    return DATA_DIR / "exp2_backlog_dynamics.json", False


def plot_backlog_dynamics():
    """§6.2: Queue depth and variant count over time by budget.

    Single-seed mode: thin trajectory lines (original behavior).
    Multi-seed mode: mean trajectory + shaded p5–p95 band per budget (when
    exp2_backlog_dynamics_n{N}.json is present).
    """
    path, multi = _find_backlog_data()
    print(f"Figure 6: Backlog dynamics ({'multi-seed' if multi else 'single-seed'} from {path.name})...")

    with open(path) as f:
        d = json.load(f)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 5.5), sharex=True,
                                    gridspec_kw={"hspace": 0.15})

    stressed = {"2": ACCENT, "5": LIGHT_GRAY}
    adequate = {"10": MED_GRAY, "20": VERY_LIGHT, "40": DARK_BG}
    all_budgets = {**stressed, **adequate}
    labels = {"2": "2 hrs/mo", "5": "5 hrs/mo", "10": "10 hrs/mo",
              "20": "20 hrs/mo", "40": "40 hrs/mo"}

    for budget, run in d["runs"].items():
        months = np.array([t / 730 for t in run["sample_ticks"]], dtype=float)
        color = all_budgets.get(budget, VERY_LIGHT)
        label = labels.get(budget, f"{budget} hrs/mo")
        lw = 2.0 if budget in stressed else 1.4

        if multi:
            q = np.array(run["per_seed_queue_depth"], dtype=float)
            v = np.array(run["per_seed_variant_count"], dtype=float)
            q_mean = q.mean(axis=0)
            q_p5, q_p95 = np.percentile(q, [5, 95], axis=0)
            v_mean = v.mean(axis=0)
            v_p5, v_p95 = np.percentile(v, [5, 95], axis=0)

            ax1.plot(months, q_mean, "-", color=color, linewidth=lw, label=label)
            ax1.fill_between(months, q_p5, q_p95, color=color, alpha=0.15, linewidth=0)
            ax2.plot(months, v_mean, "-", color=color, linewidth=lw, label=label)
            ax2.fill_between(months, v_p5, v_p95, color=color, alpha=0.15, linewidth=0)
        else:
            alpha = 0.9 if budget in stressed else 0.7
            ax1.plot(months, run["queue_depth"], "-", color=color, linewidth=lw,
                     label=label, alpha=alpha)
            ax2.plot(months, run["variant_count"], "-", color=color, linewidth=lw,
                     label=label, alpha=alpha)

    ax1.set_ylabel("Queue Depth")
    n_seeds = d.get("n_seeds")
    title_suffix = f" (N={n_seeds} seeds, mean ±p5/p95)" if multi and n_seeds else " (Seed 50)"
    ax1.set_title(f"Remediation Backlog Over Time{title_suffix}")
    ax1.legend(loc="upper right", fontsize=8, ncol=2)

    y1_top = ax1.get_ylim()[1]
    ax1.axhspan(5, y1_top if y1_top > 5 else 20, alpha=0.05, color=ACCENT)
    ax1.text(35.5, 7, "Degraded\nregime", fontsize=7, color=ACCENT,
             ha="right", va="bottom", style="italic")

    ax2.set_xlabel("Month")
    ax2.set_ylabel("Variant Controls")
    ax2.set_title("Simultaneously Variant Controls")
    ax2.legend(loc="upper right", fontsize=8, ncol=2)

    for ax in (ax1, ax2):
        ax.set_xlim(0, 36)

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "fig6_backlog_dynamics.pdf")
    fig.savefig(FIGURES_DIR / "fig6_backlog_dynamics.png")
    plt.close(fig)
    print("  -> Done")


# ── Figure 7: Cascade Timeline ──────────────────────────────────────

def plot_cascade_timeline():
    """§6.3: Per-control state timeline showing VMC-LEC cascades."""
    print("Figure 7: Cascade timeline...")

    with open(DATA_DIR / "exp3_cascading_variance.json") as f:
        d = json.load(f)

    cascade_lecs = set()
    for cw in d["cascade_windows"]:
        for lv in cw["undetected_lec_variants"]:
            cascade_lecs.add(lv["control_id"])

    vmcs = sorted([cid for cid, cs in d["control_states"].items() if cs["type"] == "VMC"])
    lecs = sorted([cid for cid in cascade_lecs if cid in d["control_states"]
                    and cid.startswith("LEC")])[:8]

    controls = vmcs + lecs
    n_controls = len(controls)

    fig, ax = plt.subplots(figsize=(10, 0.4 * n_controls + 1.5))

    state_colors = {"normal": DARK_BG, "variant": ACCENT, "remediating": LIGHT_GRAY}

    for row, cid in enumerate(controls):
        cs = d["control_states"][cid]
        ticks = cs["ticks"]
        states = cs["state"]

        prev_state = states[0]
        seg_start = ticks[0]
        for i in range(1, len(ticks)):
            if states[i] != prev_state or i == len(ticks) - 1:
                seg_end = ticks[i]
                color = state_colors.get(prev_state, VERY_LIGHT)
                ax.barh(row, (seg_end - seg_start) / 730, left=seg_start / 730,
                        height=0.7, color=color, edgecolor="none", alpha=0.85)
                seg_start = seg_end
                prev_state = states[i]

    ax.set_yticks(range(n_controls))
    ax.set_yticklabels(controls, fontsize=8)
    ax.set_xlabel("Month")
    ax.set_title("Control State Timeline — 5-Year Run (Seed 50, affect_detection_controls=True)")
    ax.set_xlim(0, 60)
    ax.invert_yaxis()

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=DARK_BG, label="Normal"),
        Patch(facecolor=ACCENT, label="Variant"),
        Patch(facecolor=LIGHT_GRAY, label="Remediating"),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=8)

    if vmcs and lecs:
        sep = len(vmcs) - 0.5
        ax.axhline(sep, color=MED_GRAY, linestyle="-", linewidth=0.5, alpha=0.5)
        ax.text(0.5, sep - 0.3, "VMCs ↑", fontsize=7, color=MED_GRAY, ha="left")
        ax.text(0.5, sep + 0.7, "LECs ↓", fontsize=7, color=MED_GRAY, ha="left")

    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "fig7_cascade_timeline.pdf")
    fig.savefig(FIGURES_DIR / "fig7_cascade_timeline.png")
    plt.close(fig)
    print("  -> Done")


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Generating paper figures in {FIGURES_DIR}/\n")
    plot_budget_sensitivity()
    plot_loss_distribution()
    plot_variance_timeline()
    plot_contact_funnel()
    plot_opeff_divergence()
    plot_backlog_dynamics()
    plot_cascade_timeline()
    print(f"\nAll figures saved to {FIGURES_DIR}/")
