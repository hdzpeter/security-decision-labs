# User Guide

## What This Tool Does

tef-estimator estimates **Threat Event Frequency (TEF)** — how often threat actors *attempt* to attack an organization matching your profile. It does not estimate whether those attempts succeed (that depends on your controls) or how much damage they cause (that depends on your assets and response).

TEF is the first input to a FAIR (Factor Analysis of Information Risk) quantitative risk analysis. The tool produces a defensible, data-grounded TEF estimate that you can feed into a Monte Carlo simulation alongside susceptibility and loss magnitude estimates.

### What TEF Is and Isn't

| Concept | What It Measures | Example |
|---------|-----------------|---------|
| **TEF** (this tool) | How often adversaries *try* | "Ransomware operators attempt to reach organizations like yours about once every 80 years" |
| **Susceptibility** | Probability that an attempt *succeeds* | "Given your controls, there's a 15-25% chance a ransomware attempt succeeds" |
| **LEF** (Loss Event Frequency) | TEF x Susceptibility | "You experience a ransomware loss event roughly once every 400 years" |
| **Loss Magnitude** | Financial impact *if* it happens | "A ransomware event costs $2-8M for your profile" |

The tool estimates TEF only. Susceptibility (control effectiveness) and loss magnitude are assessed separately.

### Prerequisites

Install from [PyPI](https://pypi.org/project/tef-estimator/): `pip install tef-estimator`

Requires **Python 3.10+**. All reference data (IRIS, DBIR, Unit42, Mandiant, CrowdStrike, Beazley, IBM, Coalition, DShield, KEV, EPSS, Ransomware.live) ships with the package — no external API keys or accounts needed.

### Interaction Modes

The tool offers three ways to interact:

- **Web UI** — `tef-estimator ui` opens a browser interface with live estimation, charts, and compare mode. Best for exploration and presentations. Requires `pip install tef-estimator[ui]`.
- **CLI** — `tef-estimator estimate ...` for scripted use and quick lookups. See the [API Reference](api-reference.md#cli).
- **Python API** — `TEFEngine(scenario=...).estimate(profile)` for integration into notebooks and pipelines. See the [API Reference](api-reference.md#python-api).
- **Telemetry monitoring** — `tef-estimator telemetry ...` collects from 7 sources and detects shifts that warrant re-estimation. Requires `pip install tef-estimator[telemetry]`. See the [API Reference](api-reference.md#telemetry).
  - *Live APIs:* DShield, CISA KEV, Ransomware.live, GreyNoise, annual report edition monitor
  - *Bundled reference importers:* IRIS reference data, vector benchmarks (DBIR/Unit42/Mandiant/Beazley/CrowdStrike/IBM)

## How the Estimation Works

### Three-Layer Model

Every estimate is bounded by three layers:

**Layer 1 — Floor (observed loss event frequency).** Cyentia IRIS data provides observed LEF by sector and revenue band. Since TEF is always greater than or equal to LEF (some attempts fail, so TEF >= LEF), these serve as a logical minimum. The floor is known to be conservative because IRIS only captures publicly disclosed events.

**Layer 2 — Ceiling (campaign-level contact frequency).** Derived from scanning telemetry (DShield, GreyNoise) for the exploitation vector and operational tempo data for the credential vector. The ceiling confirms constant bombardment — it tells you the threat is real but doesn't help position the estimate precisely.

**Layer 3 — Positioned estimate (base rate x profile adjustments).** A triangulated base rate is adjusted by your sector, revenue band, technology exposure, geography, and other profile factors. This is the number you use. It sits between the floor and ceiling, with floor enforcement preventing estimates below observed LEF.

### Vector Decomposition

Instead of one blended estimate, the tool decomposes TEF into four initial access vectors — the pathways by which attackers reach your organization:

| Vector | What It Represents | Ransomware Share | BEC Share |
|--------|-------------------|:---:|:---:|
| **Exploitation** | Scanning for and exploiting software vulnerabilities on exposed devices | ~20-25% | ~3% |
| **Credential** | Using stolen credentials (purchased from initial access brokers, harvested by infostealers) | ~50-55% | ~22% |
| **Phishing** | Email-based social engineering to deliver malware or steal credentials | ~15-20% | ~65% |
| **Supply chain** | Compromising a trusted third party to reach the target | ~5-8% | ~10% |

Each vector is estimated independently with its own data sources, floor, ceiling, and positioning logic. The four vector estimates are summed with cross-vector dampening to produce the total TEF.

**Why these four vectors.** DBIR, Mandiant M-Trends, Unit 42, and CrowdStrike GTR all converge on the same picture: these four pathways account for 95%+ of initial access across all major incident response datasets. They are not a theoretical taxonomy — they are what the data shows. They are also the resolution at which you have both independent empirical data to calibrate *and* a direct mapping to defensive controls. Each vector has its own measurable attack surface (edge devices, email footprint, vendor count), its own telemetry sources, and its own control set. Finer decomposition would lack data to calibrate. Coarser would lose the connection to actionable controls.

**Why decomposition matters:** An organization with no edge devices but a large email footprint has almost all its TEF in the phishing and credential vectors. Without decomposition, it would get a floor-bound number with no insight into *where* the threat enters or *which controls* address it.

### Scenarios

A scenario defines a specific threat type with its own vector proportions and base rate. The engine is scenario-agnostic — it runs the same computation regardless of scenario. Currently supported:

**Ransomware** — The most data-rich scenario. Credential access is the dominant vector (~52%). Base rate triangulated from operational tempo, IRIS back-calculation, and Coalition insurer data. Typical mid-market US TEF: ~1-2%.

**Business Email Compromise (BEC)** — Phishing is the dominant vector (~65%). BEC frequency is roughly 10-20x higher than ransomware for the same profile because BEC campaigns are cheaper to execute, harder to detect, and target a wider range of organizations. Typical mid-market US financial sector TEF: ~15%.

**Custom scenarios** — Analysts can define their own threat scenarios by specifying vector proportions and a base rate. Custom scenarios use the same four initial access vectors (exploitation, credential, phishing, supply chain) — you set the proportion allocated to each, and can zero out vectors that don't apply. For example, an insider threat scenario might weight credential at 80% and phishing at 20% with exploitation and supply chain at zero.

Custom scenarios are defined as JSON files:

```json
{
  "scenario_name": "Insider Threat",
  "scenario_slug": "insider_threat",
  "vector_proportions": {
    "exploitation": [0.0, 0.0, 0.05],
    "credential": [0.60, 0.80, 0.90],
    "phishing": [0.10, 0.20, 0.30],
    "supply_chain": [0.0, 0.0, 0.05]
  },
  "base_rate": {
    "consensus": [0.01, 0.03, 0.08]
  },
  "overall_share": 0.15
}
```

Each vector proportion is a PERT range `[low, mode, high]`. The modes should sum to approximately 1.0. The `base_rate.consensus` is the estimated annual probability that an organization in the addressable population experiences an attempt. The `overall_share` is this scenario's share of all cyber incidents (used for sector/revenue multiplier scaling).

CLI: `tef-estimator scenario template` generates a starter JSON. `tef-estimator scenario validate <path>` checks the file before use. `tef-estimator estimate --scenario custom --scenario-file <path>` runs an estimate. The web UI includes a visual scenario builder under the Scenarios tab. Saved scenarios appear in the scenario dropdown on the Estimate tab.

### Base Rate Triangulation

Each scenario's base rate is derived from three independent estimation anchors. If all three land in the same order of magnitude, the result is defensible. If they diverge, the divergence is itself analytically valuable.

**Anchor 1 — Operational tempo.** Active threat groups x campaigns x estimated targets / addressable population. This is structurally conservative (the denominator includes unexposed firms) and serves as a lower bound.

**Anchor 2 — IRIS back-calculation.** Observed LEF / susceptibility prior. Uses a stated susceptibility assumption (not derived — stated) to back-solve for the TEF implied by empirical loss data.

**Anchor 3 — Insurer market-adjusted.** Claims frequency from cyber insurers (e.g., Coalition), corrected for selection bias (Coalition policyholders experience 73% fewer claims than the NAIC market average, so raw Coalition frequencies are multiplied by 3.70x).

The tool computes a consensus PERT distribution from these three anchors and validates that the analyst-set consensus is within a reasonable range of the computed suggestion. The full triangulation appears in the Tier 3 audit trail.

### Cross-Vector Dampening

The four vector estimates are not fully independent — an organization that's targeted via credential theft is more likely to also face phishing attempts (because the same threat actor ecosystem operates across vectors). Summing the raw vector estimates would overcount.

The tool applies a cross-vector dampening coefficient (default k=0.85, configurable in `config.yaml` and the UI) to the sum:

```
Total_TEF = (TEF_exploitation + TEF_credential + TEF_phishing + TEF_supplychain) x vector_k
```

This default coefficient is empirically supported by VERIS co-occurrence analysis of 10,037 incidents from the Verizon VERIS dataset. The analysis found that credential and phishing vectors are strong complements (lift = 8.3, meaning they co-occur much more than chance), while exploitation is independent (lift ~ 0.2). The bimodal structure (some vectors complement, some are independent) means a single k is a simplification, but k=0.85 is a defensible central value.

### Credibility Blending (Organization-Specific Telemetry)

If your organization has its own observations — WAF/IDS logs for exploitation, email gateway data for phishing, authentication logs for credential — you can supply per-vector telemetry to refine the population-level estimate.

The engine blends the population prior with your observed rate using Bühlmann credibility weighting. The weight Z = n/(n+k) increases with more observation periods and higher detection coverage. Vectors with better observability (exploitation, default k=6) gain credibility faster than hard-to-observe vectors (supply chain, default k=40). Per-vector k values are configurable in `config.yaml` and the UI.

**Band contraction:** The uncertainty band around your estimate narrows as you provide more data. The engine uses a Gamma-inspired variance contraction mechanism to derive tighter bands from the accumulated evidence. At zero telemetry, the band equals the population-level PERT range. With 20 quarters (5 years) of observation at a rate of 0.05, the band contracts by approximately 16%. This means the lognormal sigma fed to your Monte Carlo shrinks — you get a more precise TEF input, not just a shifted one. Note: detection coverage affects the point estimate but not the band width (see `docs/technical-reference.md` §8.6 for details).

```python
from tef_estimator.credibility import VectorObservation, OrgTelemetry

telemetry = OrgTelemetry(observations=[
    VectorObservation(
        vector="credential",
        annualized_frequency=0.05,   # Your observed rate
        observation_periods=8,        # 2 years of quarterly data
        detection_coverage=0.8,       # 80% detection coverage
    ),
])

profile = OrganizationProfile(
    sector=Sector.MANUFACTURING,
    revenue_band=RevenueBand.R_100M_1B,
    geography=Geography.US,
    telemetry=telemetry,
)
```

### Peer Percentile

The tool runs itself across a grid of profiles — all sector/revenue/geography combinations at default technology settings — and reports where your estimate falls relative to peers in the same revenue band:

> "Your positioned TEF of 1.8% is at the 78th percentile across all mid-market profiles."

This means 78% of comparable organizations face lower TEF than you. Boards and executives understand relative positioning better than raw probabilities.

## Worked Examples

### Example 1: Ransomware — Manufacturing Company

**Profile:** Manufacturing sector, $100M-$1B revenue, US-based, Fortinet VPN exposed, 2,000 employees.

```bash
tef-estimator estimate --sector manufacturing --revenue 100m_1b --geo us \
    --remote-access fortinet --employees 2000
```

**Output (Tier 2 — default):**

```
RANSOMWARE TEF ESTIMATE
========================================
Annual probability: 2.1%
Recurrence: ~1 in 47 years

Peer percentile: 100th (100m-1b)

VECTOR BREAKDOWN:
  Exploitation     24% #########
  Credential       56% ######################
  Phishing         16% ######
  Supply Chain      5% #
```

**How to read this:**

- **Annual probability 2.1%** means ransomware operators attempt to reach organizations like this one roughly 2.1 times per 100 organization-years, or about once every 47 years. This is the *attempt* rate, not the success rate.
- **Peer percentile 100th** means this profile faces higher TEF than all other mid-market profiles in the peer grid. This is driven by the Fortinet VPN exposure (vulnerable VPN vendors elevate both exploitation and credential vectors) combined with manufacturing's high ransomware concentration (1.66x sector-adjusted multiplier).
- **Credential at 56%** is the dominant vector because stolen VPN credentials are the primary entry point for ransomware operators targeting manufacturing.
- **Distribution parameters** (shown below the vector breakdown) give you PERT and lognormal parameters to use in a Monte Carlo simulation. The lognormal is recommended: mu=-3.858, sigma=0.831.

**What to do with this:** Feed the TEF distribution into your FAIR model alongside susceptibility and loss magnitude. The vector breakdown tells you where to focus your susceptibility assessment — in this case, credential controls (56% of your TEF).

### Example 2: BEC — Financial Services Company

**Profile:** Financial sector, $100M-$1B revenue, US-based, no remote access exposed.

```bash
tef-estimator estimate --sector financial --revenue 100m_1b --geo us --scenario bec
```

**Output:**

```
BUSINESS EMAIL COMPROMISE TEF ESTIMATE
========================================
Annual probability: 14.9%
Recurrence: ~1 in 7 years

VECTOR BREAKDOWN:
  Exploitation      2%
  Credential       16% ######
  Phishing         71% ############################
  Supply Chain     11% ####
```

**How to read this:**

- **14.9% annual probability** — BEC attempts are dramatically more frequent than ransomware for the same profile. Financial services is the #1 BEC target sector.
- **Phishing at 71%** — BEC is overwhelmingly a phishing-driven threat.
- **Supply chain at 11%** — vendor email compromise (fake invoices from compromised supplier accounts) is a meaningful BEC vector, especially for financial services.
- **No peer percentile** — the BEC peer grid hasn't been built yet; run `tef-estimator data peer-grid --rebuild` with `--scenario bec` to generate one.

**Comparing scenarios:** The same mid-market US financial profile faces ~0.7% ransomware TEF vs ~14.9% BEC TEF. BEC is attempted roughly 20x more often than ransomware for this profile. This doesn't mean BEC is 20x riskier — BEC loss magnitudes are typically much smaller than ransomware, and susceptibility differs. But it means the TEF input to your FAIR model will be very different depending on which threat scenario you're analyzing.

### Example 3: Comparing Profiles

```bash
tef-estimator compare \
    --sector manufacturing --revenue 100m_1b --geo us --remote-access fortinet \
    --b-remote-access none
```

```
PROFILE COMPARISON
============================================================
Profile A: Manufacturing | 100M–1B | Us | VPN: fortinet
Profile B: Manufacturing | 100M–1B | Us

VECTOR DELTAS:
  Exploitation    -0.00260 (-0.26pp)
  Credential      -0.00701 (-0.70pp)
  Phishing        +0.00000 (+0.00pp)
  Supply Chain    +0.00000 (+0.00pp)

  TOTAL           -0.00817 (-0.82pp)
```

**How to read this:** Removing the Fortinet VPN reduces total TEF by 0.82 percentage points. The reduction comes from two vectors — credential (-0.70pp) because VPN credentials are no longer a viable entry point, and exploitation (-0.26pp) because the vulnerable edge device is removed. Phishing and supply chain are unaffected because they don't depend on VPN exposure.

This is how the tool connects to control investment decisions: "Completing the VPN migration reduces our ransomware TEF by 39%."

### Example 4: Sensitivity Analysis

```bash
tef-estimator sensitivity --sector manufacturing --revenue 100m_1b --geo us
```

```
SENSITIVITY ANALYSIS
============================================================
Baseline TEF: 0.01245 (1.24%)

Parameter                 Low          High            Range
------------------------------------------------------------
base_rate                 0.00771    0.03112    4.0x
vector_k                  0.01025    0.01465    1.4x
factor_k                  0.01125    0.01425    1.3x
```

**How to read this:** The base rate dominates the output uncertainty with a 4.0x range — varying the base rate from its low to high produces a 4x change in the total TEF, while dampening parameters (vector_k, factor_k) produce only 1.3-1.4x variation. This means the base rate is the single most valuable parameter to refine through better data (e.g., insurer partnership data).

## Interpreting the Output

How to read the output, what the numbers mean, and what to do with them.

### Reading Tier 1 (Summary)

Tier 1 is designed for slides and executive communication. Access it via `--brief` or `result.brief_report()`.

```
RANSOMWARE TEF ESTIMATE
========================================
Annual probability: 2.1%
Recurrence: ~1 in 47 years

Peer percentile: 100th (100m-1b)

VECTOR BREAKDOWN:
  Exploitation     24% #########
  Credential       56% ######################
  Phishing         16% ######
  Supply Chain      5% #
```

#### Annual Probability

The positioned TEF mode expressed as a percentage. "2.1%" means: in a population of 1,000 organizations with this profile, approximately 21 would face a ransomware attempt in a given year.

This is *not* a guarantee. It's a frequency estimate based on current threat landscape data, subject to the uncertainty ranges in Tier 2.

#### Recurrence

The inverse of the annual probability: 1 / 0.021 = 47 years. This is the expected time between events if the current threat level remains constant. It's easier for non-technical audiences to reason about than a percentage.

A common misinterpretation to avoid: "We're safe for 47 years." Events are stochastic — you could be hit next year. The recurrence interval is a statistical expectation, not a schedule.

#### Peer Percentile

Where your estimate falls within all profiles in the same revenue band. "100th percentile (100m-1b)" means your TEF is higher than all other mid-market profiles in the pre-computed peer grid.

**What it does mean:** Your profile has elevated risk factors compared to peers (e.g., vulnerable VPN vendor, high-target sector).

**What it doesn't mean:** It's not a score or a grade. A high percentile means high *attempt frequency*, which may or may not translate to high *risk* depending on your controls and loss exposure.

#### Vector Breakdown

The share of total TEF attributed to each initial access vector. This is the most actionable part of the output — it tells you where the threat enters.

The bar chart uses the raw (pre-dampening) vector estimates as the denominator, so shares always sum to 100%.

### Reading Tier 2 (Analysis)

Tier 2 is the analyst's workspace. Access it via default CLI output or the `analysis` property.

#### Distribution Parameters

```
DISTRIBUTION PARAMETERS (for Monte Carlo):
  Recommended distribution: Lognormal
  mu (ln-space): -3.858
  sigma (ln-space): 0.831
  5th percentile:  0.00538  (0.54%)
  Median:          0.02111  (2.11%)
  95th percentile: 0.08283  (8.28%)

  Alternative: PERT(min=0.00771, mode=0.02111, max=0.11874)
```

**For Monte Carlo simulation:** Use the lognormal parameters directly. In Python:

```python
import numpy as np
samples = np.random.lognormal(mean=-3.858, sigma=0.831, size=10000)
```

Or use the `LognormalParams.sample(n)` method.

**The 5th-95th range** is the practical uncertainty band. For this example: somewhere between 0.5% and 8.3% annual probability, with 2.1% as the most likely value. This 16x range reflects genuine uncertainty, dominated by base rate uncertainty (see sensitivity analysis).

**Lognormal vs PERT:** The lognormal is recommended because TEF distributions are right-skewed (the right tail matters more than the left tail for risk). The PERT is provided as a simpler alternative for tools that support it.

### Reading Tier 3 (Audit)

Tier 3 is for the challenger or reviewer who wants to verify the calculation. Access it via `--full` or `result.full_report()`.

#### Triangulation Validation

```
Anchor mode convergence: 3.0x (convergent)
  operational_tempo: PERT(0.0030, 0.0050, 0.0070)
  iris_back_calculation: PERT(0.0050, 0.0150, 0.0800)
  coalition_market_adjusted: PERT(0.0060, 0.0120, 0.0150)
Suggested consensus: PERT(0.0030, 0.0107, 0.0267)
Analyst consensus:   PERT(0.0030, 0.0100, 0.0250)
Consensus within 7% of suggestion
```

**Convergence ratio** (3.0x here): the ratio between the highest and lowest anchor modes. Below 10x = "convergent" — the three independent methods agree within an order of magnitude, which makes the consensus defensible.

**Suggested vs analyst consensus:** The suggested consensus is computed mechanically (arithmetic mean of modes, min of lows, capped high). The analyst consensus is the value actually used in the estimation. A deviation under 50% is flagged as acceptable. Large deviations trigger a warning.

#### Validation Checks

```
Floor <= Positioned: 0.00771 <= 0.01245
Positioned <= Ceiling: 0.01245 <= 0.09
At susceptibility 5%: implied LEF = 0.00062 (0.1x IRIS floor)
At susceptibility 15%: implied LEF = 0.00187 (0.4x IRIS floor)
At susceptibility 30%: implied LEF = 0.00373 (0.8x IRIS floor)
```

These checks verify internal consistency:

- **Floor <= Positioned <= Ceiling** — the estimate is within the logical bounds
- **Implied LEF at various susceptibilities** — what LEF would result if you applied different susceptibility assumptions. Compare against the IRIS floor (observed LEF) as a sanity check. At 30% susceptibility, the implied LEF is 0.8x the IRIS floor — plausible.

#### Warnings

Contextual warnings about the estimate's limitations:

- **"Floor is binding"** — the positioned estimate is very close to the floor, meaning the IRIS observed LEF is more informative than the base-rate-plus-adjustments approach for this profile
- **"IRIS under-counts small/mid-market firms"** — the floor is differentially conservative for smaller firms due to disclosure requirements
- **"Dampening coefficient k=..."** — reminds you that dampening is applied and cites the empirical basis

### What Peer Percentile Does and Doesn't Mean

**It does mean:**
- Your TEF estimate is higher or lower than X% of comparable organizations (in the same revenue band)
- The comparison is across all sector/geography combinations at default technology settings
- It provides relative context for absolute numbers that are hard to interpret in isolation

**It doesn't mean:**
- A high percentile doesn't mean you'll be breached — TEF measures attempts, not outcomes
- It doesn't account for your specific control posture — two organizations with the same TEF percentile can have very different susceptibility
- The peer grid uses default technology settings, so if you've specified VPN exposure, you're being compared to a grid that mostly doesn't have VPN exposure

**No percentile showing?** The peer grid needs to be built for your scenario:

```bash
tef-estimator data peer-grid --rebuild
```

### Downstream Usage

The TEF output feeds into a full FAIR analysis:

1. **Estimate TEF** using this tool for your target scenario (ransomware, BEC)
2. **Extract distribution parameters** (lognormal mu/sigma from Tier 2)
3. **Note the dominant vector** from the vector breakdown
4. **Assess susceptibility** per vector (control effectiveness assessment is separate)
5. **Compute LEF** = TEF distribution x susceptibility distribution
6. **Combine with loss magnitude** to get the full risk distribution

The vector decomposition means you can (and should) estimate susceptibility *per vector* rather than as a single blended number. A manufacturing company might have excellent patch management (low exploitation susceptibility) but weak credential controls (high credential susceptibility). The decomposed TEF lets you apply different susceptibility to each vector for a more accurate LEF.

### Common Questions

**Q: Why is BEC TEF so much higher than ransomware?**

BEC campaigns are cheaper to execute (no malware development, no infrastructure), harder to attribute (spoofed email vs deployed malware), and target a wider population (any company that processes invoices). The base rate for BEC attempts is roughly 10-20x higher than ransomware. However, BEC loss magnitudes are typically much smaller and susceptibility varies widely — a company with strong out-of-band verification procedures has very low BEC susceptibility regardless of TEF.

**Q: My estimate seems too low / too high. What should I do?**

Run `tef-estimator explain` to see the full calculation trace. Check which multipliers are driving the result. If you have internal incident data that contradicts the estimate, use `--base-rate` to override the triangulated base rate with your own. The sensitivity analysis (`tef-estimator sensitivity`) shows which parameters drive the most uncertainty.

**Q: How often should I refresh the estimate?**

The output is labelled "point-in-time; refresh quarterly." Refresh by updating bundled reference data. Run `tef-estimator refresh check` to validate data freshness. Reference data (IRIS, Beazley, Coalition) updates annually when new reports are published; snapshot data (DShield, KEV, EPSS, Ransomware.live) can be refreshed via `tef-estimator refresh`.

**Q: Can I use this for a scenario not listed (e.g., insider threat, data exfiltration)?**

Not yet with built-in scenarios. You can create a custom scenario by implementing the `ScenarioDefinition` protocol — see the Data Sources Guide for instructions. The engine is scenario-agnostic; it will run any scenario that provides the required data.

**Q: What if I disagree with a specific multiplier?**

Good — challenge is part of the process. The full audit trail (`--full`) shows every multiplier with its source citation. For the base rate, use `--base-rate` to override. For dampening, susceptibility prior, and credibility k, adjust them in the UI Configuration panel or create `~/.tef-estimator/config.yaml` with your values. For vector proportions, create a modified scenario.

## Connecting to Susceptibility Assessment

The vector decomposition scopes the downstream susceptibility assessment:

1. **Run the TEF estimate** for your target scenario and profile.
2. **Look at the vector breakdown** to identify your dominant vector (e.g., credential at 56%).
3. **Prioritize your susceptibility assessment** on the controls for your dominant vector — that's where reducing susceptibility has the largest impact on loss event frequency.

## Key Concepts Reference

| Term | Definition |
|------|-----------|
| **TEF** | Threat Event Frequency — how often adversaries *attempt* harmful actions |
| **LEF** | Loss Event Frequency — how often those attempts result in actual loss (TEF x susceptibility) |
| **PERT** | A distribution defined by three points: low (optimistic), mode (most likely), high (pessimistic). Used throughout for uncertainty ranges. |
| **Positioned estimate** | The main TEF output — a base rate adjusted by profile factors, bounded by floor and ceiling |
| **Floor** | Minimum TEF based on observed loss events (IRIS data). Conservative because only captures disclosed events. |
| **Ceiling** | Maximum plausible TEF based on scanning telemetry and operational tempo. Usually very high and not useful for positioning. |
| **Dampening** | Adjustment for correlation between factors (within-vector, default k=0.70) and between vectors (cross-vector, default k=0.85); configurable via `config.yaml` and UI |
| **Peer percentile** | Where your estimate falls relative to all profiles in the same revenue band |
| **Scenario** | A threat type (ransomware, BEC) with its own vector proportions, base rate, and sector/revenue adjustments |
