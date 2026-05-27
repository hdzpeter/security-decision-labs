# Control Systems Agent-Based Model

[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)
[![Methodology: FAIR-CAM](https://img.shields.io/badge/Methodology-FAIR--CAM-blue.svg)](https://www.fairinstitute.org/)

**Important:** This is an independent implementation of the FAIR-CAM methodology. See [FAIR_NOTICE.md](FAIR_NOTICE.md) for trademark information, data sources, and attributions.

Minimal reproduction package for:

> Jones, J. and Voicu, L. (2026). *Control Physiology: An Agent-Based Model of FAIR-CAM Dynamics.* arXiv:2605.26597 [cs.CR]. https://doi.org/10.48550/arXiv.2605.26597

This repository ships the code, scenario data, configuration, calibration
tables, and experiment scripts needed to reproduce the paper's figures and
headline numbers. It is **not** the full toolkit. For the full
toolkit (Monte Carlo batch infrastructure, dynamic personnel behaviour,
and the full UI), contact the authors.

## What's included

- `src/` — the agent-based simulation engine (8 agent types; LEC/VMC/DSC
  control processors; multiplicative defense-in-depth susceptibility;
  narrative causation engine).
- `scenarios/hospital_ransomware_medium/` and `scenarios/hospital_ransomware_weak/`
  — the two parameterisations used in the paper.
- `inputs/model_config.yaml` — the global model configuration.
- `calibration/loss_tables/` — empirically calibrated loss-magnitude data:
  `empirical_breach.json` (lognormal parameters fit to IRIS 2025 data,
  with fallback ladder by scenario type / sector / revenue bucket) and
  outage cost tables. See `calibration/README.md` for provenance.
- `papers/` — the exact scripts that produced every figure and headline
  number in the paper. See `REPRODUCE.md` for the scripts → figures mapping.

## What's intentionally excluded

This repository is deliberately minimal. The features below belong to the
full toolkit and are not distributed here. For access, contact the
authors.

### Dynamic personnel behaviour

- Satisficing decision model with aspiration and propensity dynamics
- Competing Values Framework (CVF) organisational-culture types
  (Hierarchy / Clan / Market / Adhocracy) and their effect on variance rates
- Social contagion of misalignment through organisational influence networks
- Event-shock responses (incident → awareness / budget / priority / distraction arcs)
- Personnel-driven monthly variance emission
- The psychometric model backing the DSC five-dimension evaluation

In this repository, `PersonnelIntegration` is a no-op stub with
`enabled = False`. The paper runs with personnel dynamics disabled;
this module is reserved for future work on organisational influence.

### Extended calibration data

- The DSC calibration coefficients fit from survey data
- The conditional-probability table fit for the five-dimension DSC model
  beyond the inline `default_v13` table shipped here
- Industry reference baselines for threat frequency and response timing
- The full curated empirical corpus (163+ records across 20 categories)
  from which the shipped loss tables are derived

### Monte Carlo and experiment infrastructure

- The batch-run API (`api/batch.py`) with per-iteration parallelism
- Sensitivity sweeps at scale (budget × frequency × cadence × strategy)
- Common Random Numbers (CRN) / paired-seed variance reduction for
  counterfactual analysis
- Sobol / Morris global sensitivity analyses
- Stream-isolated PRNG allocation per agent (`StreamedRNG` is shipped but
  the full counterfactual-evaluation tooling that depends on it is not)

### Analysis layer

- `src/analysis/metrics.py` risk-appetite metrics (VaR, CVaR, appetite-breach
  detection, posture scoring)
- Linchpin analysis (ranking which VMCs cause the most downstream loss when
  degraded) — the hook exists in narrative but the full analysis is not here
- Counterfactual breach classification
- Advanced narrative analytics: cascade-path taxonomies, causal-chain length
  distributions, monitoring-failure root-cause clustering

### Scenario library

- **SaaS ransomware** (low / medium / high postures)
- Multi-personnel scenarios for organisational influence experiments
- Test-harness micro-scenarios (17 fixtures used by the internal validation suite)
- Topology editor and scenario-authoring UI

### UI and service layer

- The full production web UI: dashboard, runs view, scenario browser,
  narrative explorer, topology editor, variance timeline, compare view,
  wizard, and 11 charting components
- REST API (`api/main.py`, `api/engine.py`, `api/store.py`, `api/scenarios.py`)
- Settings and configuration-diff UIs
- Real-time simulation streaming over WebSockets

### Tests

- The internal `pytest` suite (`tests/`) is not shipped here. It has been
  run against the code in this repository to confirm no regressions relative
  to the private repo; the suite itself stays with the full toolkit.

## Requirements

- Python 3.10+
- The dependencies listed in `pyproject.toml`

## Install

```bash
git clone <this-repo>
cd control-systems-agent-based-model
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Reproduce a paper figure

From the repository root:

```bash
# The three Section 6 experiments (OpEff divergence, backlog dynamics,
# cascading variance). Writes JSON outputs to papers/data/.
python papers/run_paper_experiments.py --exp all

# Generate every figure in the paper. Writes PNG and PDF to papers/figures/.
python papers/generate_plots.py
python papers/generate_section6_plots.py
```

Full details in [`REPRODUCE.md`](./REPRODUCE.md).

## Citation

```bibtex
@article{Jones2026ControlPhysiology,
  author        = {Jones, Jack and Voicu, Laura},
  title         = {Control Physiology: An Agent-Based Model of FAIR-CAM Dynamics},
  year          = {2026},
  eprint        = {2605.26597},
  archiveprefix = {arXiv},
  primaryclass  = {cs.CR},
  doi           = {10.48550/arXiv.2605.26597},
}
```

## Licence

Code and data in this repository are released under the Creative Commons
Attribution-NonCommercial-ShareAlike 4.0 International Licence
(CC BY-NC-SA 4.0). See [`LICENSE`](./LICENSE).
