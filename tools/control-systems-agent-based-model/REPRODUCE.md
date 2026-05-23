# Reproducing the paper

All scripts are designed to be run from the repository root with the
virtual environment activated (see `README.md`). Each script is
deterministic given the seed set baked into the code; outputs land in
`papers/data/` (JSON) and `papers/figures/` (PNG + PDF).

Headline numbers in the paper and the scripts that produce them:

| Paper result | Script | Seed(s) | Output |
|---|---|---|---|
| OpEff divergence (-19.2% at freq = 1/year) | `papers/run_threat_freq_sweep.py` | 0–99 paired | `papers/data/threat_freq_sweep.json` |
| Per-control emergent vs. analytical OpEff | `papers/run_paper_experiments.py --exp 1` | 0–29 | `papers/data/exp1_opeff_divergence.json` |
| Remediation backlog phase transition (5–20 hrs/mo) | `papers/run_paper_experiments.py --exp 2` | 50 | `papers/data/exp2_backlog_dynamics.json` |
| Remediation backlog with mean ± p5/p95 band (N seeds) | `papers/run_paper_experiments.py --exp 2 --seeds 500` | 0–499 | `papers/data/exp2_backlog_dynamics_n500.json` |
| Cascading monitoring-failure run + narrative | `papers/run_paper_experiments.py --exp 3` | 50 | `papers/data/exp3_cascading_variance.json` |
| Weak vs. medium scenario (N = 100) | `papers/run_scenario_comparison.py` | 0–99 paired | `papers/data/scenario_comparison.json` |

Figures:

| Figure | Script | Data source |
|---|---|---|
| fig1 — budget sensitivity | `papers/generate_plots.py` | computed inline |
| fig2 — loss distribution | `papers/generate_plots.py` | computed inline |
| fig3 — control state distribution timeline (Seed 50) | `papers/generate_plots.py` | `exp2_backlog_dynamics.json` (b=40 run) |
| fig4 — contact funnel | `papers/generate_plots.py` | computed inline |
| fig5 — OpEff divergence (analytical vs emergent) | `papers/generate_plots.py` | `exp1_opeff_divergence.json` |
| fig6 — backlog dynamics (mean + p5/p95 band) | `papers/generate_plots.py` | `exp2_backlog_dynamics_n{N}.json` if present, else `exp2_backlog_dynamics.json` |
| fig7 — cascade timeline | `papers/generate_plots.py` | `exp3_cascading_variance.json` |

## End-to-end reproduction

```bash
# 1. Run the three main experiments (~30 min on a laptop for --exp 1 alone at N=30;
#    --exp 2 is fast; --exp 3 runs a 5-year horizon and is the longest).
python papers/run_paper_experiments.py --exp all

# 2. Run the threat-frequency sweep that produces the -19.2% headline number.
python papers/run_threat_freq_sweep.py

# 3. Run the scenario comparison.
python papers/run_scenario_comparison.py

# 4. Generate all figures.
python papers/generate_plots.py
```

## Notes on determinism

- The model uses a single seed passed to `FAIRCAMModel(..., seed=k)`. Per-agent
  PRNG stream isolation is handled by `src.data.streamed_rng.StreamedRNG`, so
  results are stable across runs for a given seed.
- `run_paper_experiments.py` pins seeds 0–29 for Experiment 1 and seed 50 for
  Experiments 2 and 3. Experiment 2 can also be run over N seeds (0..N-1) via
  `--seeds N` to produce a smoothed fig6 with mean and p5/p95 uncertainty band;
  this writes `exp2_backlog_dynamics_n{N}.json` alongside (not replacing) the
  single-seed output.
- `run_threat_freq_sweep.py` and `run_scenario_comparison.py` use paired seeds
  0–99 (same seed at each frequency/scenario level for variance reduction).
- The `fig6_backlog_dynamics.{png,pdf}` PDFs shipped in this repo were generated
  from `--seeds 500` (seeds 0–499) on the authors' hardware; a fresh run with
  the same seed range reproduces them bit-identically.

## What these scripts do NOT reproduce

- **Personnel-dynamics-driven results.** The open-core
  `PersonnelIntegration` is a no-op stub. Any result that depends on
  satisficing, CVF, or social contagion cannot be reproduced here. The
  paper runs with personnel dynamics disabled.
- **Results that depend on extended calibration data** not shipped here (DSC
  survey coefficients, industry reference baselines). The loss-magnitude
  tables shipped in `calibration/loss_tables/` are the empirically calibrated
  values used in the paper.
