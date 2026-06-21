# TEF Estimator Technical Reference

Version 1.1.3

Complete documentation of every module, design decision, data source, parameter choice, and provenance chain in the TEF estimation engine.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Estimation Pipeline](#2-estimation-pipeline)
3. [Vector Methodology](#3-vector-methodology)
4. [Data Layer](#4-data-layer)
5. [Data Sources and Provenance](#5-data-sources-and-provenance)
6. [Parameter Choices and Rationale](#6-parameter-choices-and-rationale)
7. [Scenario System](#7-scenario-system)
8. [Credibility Blending](#8-credibility-blending)
9. [Output Structure](#9-output-structure)
10. [Validation and Audit Trail](#10-validation-and-audit-trail)

---

## 1. Architecture Overview

### Design Principles

**Separation of data and logic.** Every empirical number is loaded from JSON files. The reference data loads from bundled `data/reference/{source}/extracted.json` and scenario configuration from `data/scenarios/`. No probabilities, multipliers, or calibration constants are hardcoded in Python. This makes the provenance of every number auditable and every assumption replaceable without code changes.

**Scenario-agnostic engine.** The estimation engine (`engine.py`), all four vector computation modules, dampening, floor enforcement, triangulation, and output formatting operate identically regardless of threat type. Scenarios are pure data definitions that implement the `ScenarioDefinition` protocol.

**Three-layer estimation.** Each vector produces a floor (observed lower bound from IRIS incident data), a ceiling (theoretical maximum from scanning/operational tempo telemetry), and a positioned estimate (base rate adjusted by organizational profile multipliers). The positioned estimate is the primary output; floor and ceiling provide sanity-check bounds.

**Three-tier output.** Results are structured into Tier 1 (executive summary), Tier 2 (analyst workspace), and Tier 3 (full audit trail with step-by-step calculation traces, validation checks, and data source citations).

### Module Dependency Graph

```
cli.py / ui.py
    |
    v
engine.py (TEFEngine)
    |
    +---> config.py + config.yaml (TEFConfig: susceptibility, dampening, credibility k)
    +---> vectors/{exploitation,credential,phishing,supply_chain}.py
    |         |
    |         +---> data/common.py (multipliers, enums, floor anchors)
    |         +---> distributions.py (dampening, PERT, lognormal)
    |         +---> trace.py (step-by-step arithmetic)
    |         +---> vectors/base.py (VectorEstimate dataclass)
    |
    +---> credibility.py (Bühlmann blending)
    +---> triangulation.py (three-anchor consensus)
    +---> peer.py (percentile grid)
    +---> result.py (TEFResult, three-tier output)
    +---> profile.py (OrganizationProfile)
    |
    v
data/loader.py
    |
    +---> data/reference/{iris,beazley,coalition,at_bay,greynoise,...}/extracted.json
    +---> data/scenarios/{ransomware,bec}.json
    +---> data/scenarios/{ransomware,bec,custom}.py
```

---

## 2. Estimation Pipeline

### Step-by-Step Flow

For a given `OrganizationProfile` and `ScenarioDefinition`:

**Step 1: Base Rate Resolution**
```
base_rate = scenario.base_rate_triangulation["consensus"]
           or profile.custom_base_rate (if analyst override provided)
```
The consensus is a PERT(low, mode, high) derived from three-anchor triangulation (see Section 10).

**Step 2: Vector Decomposition**
Four independent vector engines each produce a `VectorEstimate`:
```
for each vector in [exploitation, credential, phishing, supply_chain]:
    floor    = IRIS_overall_floor x vector_proportion x adjusted_sector_multiplier
    ceiling  = vector-specific bound (scanning, operational tempo, etc.)
    positioned = base_rate x vector_proportion x dampened(sector x revenue x tech x geo)
```

**Step 3: Bühlmann Credibility Blending with Gamma-Inspired Band Contraction (optional)**
If `profile.telemetry` is provided:
```
for each vector with org-specific observations:
    Z = effective_n / (effective_n + k)          # credibility weight
    blended = Z x adjusted_observed + (1-Z) x positioned_median

    # Gamma-inspired posterior band contraction
    σ_prior = (ln(high) - ln(low)) / (2 × 1.645)    # PERT-implied log-sigma
    CV² = exp(σ_prior²) - 1
    α_pert = 1 / CV²                                # Gamma shape matching PERT width
    N = adjusted_observed × effective_n / 4           # pseudo-events (quarters → years)
    α_post = α_pert + N                              # posterior shape
    σ_post = √(ln(1 + 1/α_post))                    # posterior log-sigma (≤ σ_prior)

    positioned_median = blended
    positioned_low  = exp(ln(blended) - 1.645 × σ_post)
    positioned_high = exp(ln(blended) + 1.645 × σ_post)
    enforce_bounds()
```

The Bühlmann blend is mathematically equivalent to the Gamma-Poisson posterior mean: the credibility weight Z = n/(n+k) is exactly Bayes' rule for a Gamma(α, β) prior updated with Poisson observations. This equivalence motivates the band contraction, which derives bands from the Gamma posterior's coefficient of variation so that more observation periods monotonically narrow the output distribution. The implementation uses two separately calibrated parameters (k for the mean, α_pert for the band) rather than a single coherent Bayesian model (see §8.6 for the full derivation and known limitations).

**Step 4: Cross-Vector Aggregation with Dampening**
```
raw_total = sum(positioned_median for all vectors)
total     = raw_total x vector_k                 # default 0.85, configurable in config.yaml
```

**Step 5: Floor Enforcement**
```
total_floor = IRIS_overall_lower_bound x adjusted_sector_multiplier
total       = max(total, total_floor)
```

**Step 6: Distribution Fitting**
```
lognormal = LognormalParams.from_median_and_range(total_median, total_low, total_high)
```

**Step 7: Triangulation Validation**
```
suggested = triangulate(anchors)
check analyst consensus deviation against suggested
```

**Step 8: Result Assembly**
TEFResult with all three tiers, validation checks, warnings, and traces.

### Dampening Model

Multipliers are correlated (a large firm in financial services probably already has better controls). Naive multiplication overstates risk for heavily-adjusted profiles. The dampening formula compresses the composite:

```
dampened_composite = 1 + (raw_composite - 1) x k
capped at max_composite = 5.0
```

Two dampening levels (defaults from `config.yaml`, adjustable via `~/.tef-estimator/config.yaml` or UI):
- **Within-vector** (`factor_k`, default 0.70): compresses stacked multipliers (sector x revenue x tech x geo) within a single vector. Judgment-based; cannot be derived from VERIS without population denominators.
- **Cross-vector** (`vector_k`, default 0.85): compresses the sum of four vector estimates. Empirically supported by VERIS VCDB co-occurrence analysis (10,037 incidents). See §6.2.1 for derivation methodology and pairwise lift table.

The `max_composite` cap (default 5.0) means no profile can produce more than 5x the base rate through multiplier stacking. Rationale: IRIS overall upper bound (10%) / base rate mode (1%) ~ 10x; 5x allows differentiation while preventing runaway stacking.

---

## 2A. Worked Example: End-to-End Math

This section traces every computation for a single profile through the full pipeline: **manufacturing, \$100M–$1B, US, Fortinet VPN, ransomware scenario**.

### Step 1: Base Rate (Three-Anchor Consensus)

The base rate answers: what fraction of all organizations in the addressable population face at least one threat event of this type per year, before any org-specific adjustment?

Three independent data paths converge. All convert observed LEF (loss events) to TEF (threat events = attempts) via: **TEF = LEF ÷ susceptibility**.

**Anchor 1 — Operational Tempo:**
```
Ransomware.live: ~4,000 leak-site listings/year
Underreporting: 5–10× (not all groups have sites, not all victims posted, many pay before listing)
→ 20,000–40,000 actual loss events/year
÷ 6M US addressable businesses (Census Bureau)
= 0.33–0.67% LEF
÷ susceptibility 10–30% (population average)
= TEF 1.1–6.7%    →    PERT(0.011, 0.025, 0.067)
```

**Anchor 2 — IRIS Back-Calculation:**
```
IRIS 2025 overall LEF = 0.465%
× ransomware share (IRIS Table 1) = 31.7%
= ransomware LEF ≈ 0.147%
÷ susceptibility 10–30%
= TEF 0.49–1.47%    →    PERT(0.005, 0.015, 0.08)
```
High value (8%) reflects very low susceptibility (~2%) for small firms where IRIS undercounts.

**Anchor 3 — Coalition Market-Adjusted:**
```
Coalition 2025 standalone ransomware claims: 0.31%
× 3.70 bias correction (Coalition clients are better-controlled than market; NAIC has 4.4M policies)
= 0.93–1.48% market-adjusted LEF
÷ susceptibility 10–30%
= TEF 3.1–14.8%    →    PERT(0.03, 0.06, 0.15)
```

**Consensus — conservative synthesis:**
```
Anchor modes: 2.5%, 1.5%, 6.0%   →   mean = 3.3%
Consensus: PERT(0.01, 0.03, 0.10)   →   mode 3%, conservative vs. 3.3% mean
```

The susceptibility prior (default 10–30%) represents "the average organization with average controls." It is configurable in `config.yaml` and the UI. When changed, the engine rescales the base rate anchors proportionally. A security-mature organization might use 5–15%; a less mature one might use 20–50%. See §6.4.1.

### Step 2: Vector Decomposition

The base rate is split across 4 initial-access vectors (proportions from multi-source IR reports: Beazley, Verizon, Unit42, Mandiant, CrowdStrike, Sophos):

```
credential:    PERT(0.45, 0.52, 0.58)   ← 52% of ransomware initial access
exploitation:  PERT(0.18, 0.22, 0.28)   ← 22%
phishing:      PERT(0.12, 0.17, 0.22)   ← 17%
supply_chain:  PERT(0.04, 0.06, 0.10)   ← 6%
```

Each vector's starting point:
```
vector_base = base_rate.mode × proportion.mode

credential_base   = 0.03 × 0.52 = 0.0156
exploitation_base = 0.03 × 0.22 = 0.0066
phishing_base     = 0.03 × 0.17 = 0.0051
supply_chain_base = 0.03 × 0.06 = 0.0018
```

### Step 3: The Multiplier Stack

Each vector collects multipliers from 4 independent dimensions. For the example profile:

**Sector multiplier — scenario-adjusted** (from `ransomware.py`):
```
common_mult  = SECTOR_DATA[manufacturing].all_incident_multiplier     # 1.03  (IRIS Fig A1)
sector_share = scenario.sector_shares[manufacturing]                   # 0.51  (IRIS RW Fig 13)
overall_share = scenario.overall_share                                 # 0.317 (IRIS RW Table 1)

adjusted_sector = common_mult × (sector_share / overall_share)
                = 1.03 × (0.51 / 0.317)
                = 1.03 × 1.609
                = 1.657
```
Manufacturing has a near-average all-incident rate (1.03×) but 51% of its incidents are ransomware (vs. 31.7% average), so the scenario adjustment pushes it to 1.66×.

**Revenue multiplier — same pattern:**
```
common_rev_mult  = REVENUE_BAND_DATA[100m_1b].all_incident_multiplier  # 0.80  (IRIS Fig A2)
rev_share        = scenario.revenue_shares[100m_1b]                     # 0.48  (IRIS RW Fig 15)

adjusted_revenue = 0.80 × (0.48 / 0.317) = 0.80 × 1.514 = 1.211
```

**Tech multiplier** (from `at_bay/extracted.json`):
```
Fortinet = vulnerable VPN vendor
→ TECH_MULTIPLIERS["vpn_vulnerable_vendor"] = PERT(1.2, 1.4, 1.6)
```
Source: At-Bay 2025 (VPNs in 80% of ransomware attacks, VPN specifically exploited in 66%) + Beazley (48% of initial access was VPN credentials). The PERT range is judgment-calibrated — these reports give directional data (proportions), not relative risk ratios.

**Geography multiplier** (from `common/extracted.json`):
```
US → GEO_MULTIPLIERS["us"] = PERT(1.1, 1.2, 1.3)
```
Judgment-informed by DBIR 2025 geographic patterns.

### Step 4: Why Dampening Is Needed

The raw multiplicative composite:
```
raw_composite = sector × revenue × tech × geo
              = 1.657 × 1.211 × 1.4 × 1.2
              = 3.37
```

This assumes **full independence**: each factor independently multiplies risk. That's wrong for three reasons:

1. **Confounded factors.** Manufacturing firms tend to be mid-market. The IRIS data that produces the sector multiplier already partially reflects the revenue distribution within manufacturing. Multiplying both double-counts the overlap.

2. **Diminishing marginal impact.** If you're already manufacturing (which implies OT/SCADA exposure), the additional VPN risk is partially already captured in the sector data.

3. **Ceiling effects.** Attacker capacity is finite. Even if every multiplier says "more targeted," there is a maximum rate at which threat actors can actually target you.

The standard approach in insurance pricing is **credibility-weighted compression**: believe the direction of each multiplier but dampen the magnitude of their interaction.

### Step 5: The `dampen_composite` Function

```
dampened = 1.0 + (raw_composite - 1.0) × k
         capped at max_composite = 5.0
```

For this profile:
```
raw = 3.37
k = 0.70   (factor_k, within-vector; from config.yaml)

dampened = 1.0 + (3.37 - 1.0) × 0.70
         = 1.0 + 2.37 × 0.70
         = 1.0 + 1.659
         = 2.659
```

The `(raw - 1)` extracts the **excess above baseline**. `× k` compresses that excess. `+ 1` restores the baseline.

| k value | Meaning |
|---------|---------|
| k = 1.0 | Full independence — no dampening, raw composite used as-is |
| k = 0.0 | All multipliers ignored — everything gets base rate |
| k = 0.70 | Keep 70% of the multiplicative excess above 1.0 |

### Step 6: Positioned Vector Estimate

For the exploitation vector:
```
positioned_median = vector_base × dampened_composite
                = 0.0066 × 2.659
                = 0.01755   (1.76%)
```

The floor for this vector:
```
floor = IRIS_overall_lower_bound × exploitation_proportion × adjusted_sector
      = 0.00465 × 0.22 × 1.657
      = 0.001695   (0.17%)
```

Positioned (1.76%) > floor (0.17%), so floor doesn't bind. Each vector runs this independently with its own tech multiplier selection and vector-specific logic.

### Step 7: Cross-Vector Aggregation

Sum the four vector estimates, then apply cross-vector dampening:
```
raw_total = Σ(positioned_median for all vectors)
dampened_total = raw_total × vector_k
              = raw_total × 0.85  (default from config.yaml)
```

The cross-vector dampening compresses the sum because credential and phishing vectors are strongly correlated (VERIS lift = 8.29). See §6.2.1.

### Step 8: Floor Enforcement

```
overall_floor = 0.00465   (IRIS)
total_floor = overall_floor × adjusted_sector = 0.00465 × 1.657 = 0.0077

total_median = max(total_median, total_floor)
```

For this profile: total_median (6.33%) >> total_floor (0.77%), so the floor doesn't bind.

### Step 9: Lognormal Output

The positioned estimate becomes a lognormal for downstream Monte Carlo consumers:
```
μ = ln(median) = ln(0.0633) = -2.76

σ_low  = (μ - ln(low)) / 1.645        # low targets ~5th percentile
σ_high = (ln(high) - μ) / 1.645       # high targets ~95th percentile
σ = mean(σ_low, σ_high)               # averaged for robustness, floored at 0.1
```

This gives a right-skewed distribution where:
- Median = positioned mode (6.33%)
- P5 ≈ positioned low
- P95 ≈ positioned high

### The Complete Formula

```
For each vector v ∈ {exploitation, credential, phishing, supply_chain}:

    vector_base_v = consensus_base_rate × vector_proportion_v

    raw_composite_v = ∏(sector_mult, revenue_mult, tech_mult, geo_mult)

    dampened_v = 1 + (raw_composite_v - 1) × factor_k           [within-vector compression]

    positioned_v = vector_base_v × dampened_v

    positioned_v = max(positioned_v, floor_v)                    [IRIS floor enforcement]


TEF_total = (Σ positioned_v) × vector_k                         [cross-vector compression]

TEF_total = max(TEF_total, overall_floor × sector_adjustment)    [aggregate floor]

Output: Lognormal(μ = ln(TEF_total), σ = f(range))
```

### Verified Output for This Profile

Manufacturing, \$100M–$1B, US, Fortinet VPN, ransomware:
- **TEF positioned mode: 6.33%** (once every ~16 years)
- Exploitation: ~28% of total
- Credential: ~41% of total
- Phishing: ~21% of total
- Supply chain: ~10% of total
- Base rate dominates sensitivity by ~10× over any other parameter

---

## 3. Vector Methodology

Each of the four initial access vectors has its own threat model, floor/ceiling bounds, and multiplier stack. All vectors share the same estimation formula (see §2) but differ in what data drives each component.

### Exploitation

**Threat model**: Public-facing application/device vulnerability exploitation. ~20-25% of ransomware initial access (multi-source IR reports, CISA advisories, GreyNoise).

**Floor**: IRIS overall lower bound × exploitation proportion × adjusted sector multiplier.

**Ceiling**:
- Edge device present (VPN/RDP): unbounded (DShield confirms continuous scanning)
- Cloud-primary, no edge: 0.01 (no edge attack surface)
- Default: 0.1 (moderate attack surface)

**Multipliers**:
1. Sector (scenario-adjusted from IRIS)
2. Revenue band (scenario-adjusted from IRIS)
3. Technology: vulnerable VPN vendor [1.2, 1.4, 1.6] from At-Bay; exposed RDP [1.1, 1.3, 1.5] from Beazley; cloud-primary [0.5, 0.7, 0.8] (protective)
4. Geography

### Credential

**Threat model**: Stolen/purchased VPN/RDP/SSO credentials from Initial Access Brokers. ~50-55% of ransomware initial access (Beazley Q3 2025). Invisible to scanning telemetry.

**Floor**: IRIS overall lower bound × credential proportion × adjusted sector multiplier.

**Ceiling**: Operational tempo — campaigns/month × credential proportion × 12 / addressable population. Analytically tight because each credential campaign targets a specific organization, unlike scanning which sweeps broadly.

**Multipliers**:
1. Sector (scenario-adjusted)
2. Revenue band (scenario-adjusted)
3. Technology: vulnerable VPN vendor [1.2, 1.4, 1.6] (VPN credentials = 48% of ransomware initial access); non-vulnerable VPN [1.0, 1.2, 1.4]; exposed RDP [1.1, 1.3, 1.5]; no remote access [0.4, 0.6, 0.8] (protective — removes dominant credential pathway)
4. Geography

### Phishing

**Threat model**: Email-based social engineering delivering ransomware loaders. ~15-20% of ransomware initial access (multi-source IR reports). Partially observable — email volume is measurable but campaign initiation is not.

**Floor**: IRIS overall lower bound × phishing proportion × adjusted sector multiplier.

**Ceiling**: 0.05 (Proofpoint campaign volume bound).

Employee count directly affects TEF through Probability of Action: more recipients = higher probability at least one takes the bait within a single campaign.

**Multipliers**:
1. Sector (scenario-adjusted)
2. Revenue band (scenario-adjusted)
3. Technology: large email footprint (≥1000 employees) [1.1, 1.2, 1.3]; small employee count (<50) [0.5, 0.7, 0.9]
4. Geography

### Supply Chain

**Threat model**: Third-party/vendor compromise as attack pathway. ~5-8% of ransomware initial access (IR reports: 30% third-party involvement across all breaches). Not directly observable.

**Floor**: IRIS overall lower bound × supply chain proportion × adjusted sector multiplier.

**Ceiling**: IRIS overall upper bound × 0.30 (IR report third-party involvement rate).

**Multipliers**:
1. Sector (scenario-adjusted)
2. Revenue band (scenario-adjusted)
3. Supply chain provider flag [1.1, 1.3, 1.5]
4. Geography

---

## 4. Data Layer

### Directory Structure

```
data/
  reference/
    iris/extracted.json              # Cyentia IRIS 2025 + Ransomware Spotlight
    beazley/extracted.json           # Beazley Q3 2025 Threat Briefing
    coalition/extracted.json         # Coalition 2025 Cyber Claims Report
    at_bay/extracted.json            # At-Bay 2025 InsurSec Report
    greynoise/extracted.json         # GreyNoise 2025+2026 exploitation reports
    proofpoint/extracted.json        # Proofpoint State of the Phish + Human Factor
    cofense/extracted.json           # Cofense 2026 Annual Report
    naic/extracted.json              # NAIC 2025 Cybersecurity Insurance Market
    recorded_future/extracted.json   # Placeholder (pending monthly extraction)
    common/extracted.json            # Cross-source derived parameters
  scenarios/
    ransomware.json                  # Ransomware scenario-specific parameters
    bec.json                         # BEC scenario-specific parameters
  peer_grid/
    ransomware.json                  # Pre-computed peer percentile grid
    bec.json                         # Pre-computed peer percentile grid
```

### JSON Convention

Every JSON file follows the same conventions:
- `_metadata` block at the top: source, access URL, extracted_date, extracted_by
- `_citation` key on every data section: specific figure/table/page reference
- `_note` keys for explanatory context
- Keys prefixed with `_` are metadata/notes and are filtered out during loading

---

## 5. Data Sources and Provenance

### 5.1 Cyentia IRIS 2025 + Ransomware Spotlight

**File**: `reference/iris/extracted.json`

**Source**: Cyentia IRIS 2025 (150k+ events, 2008-2024) + IRIS Ransomware Spotlight (14k+ events, 2019-2023)

**Extracted**: 2026-05-24

| Field | Citation | Used For |
|-------|----------|----------|
| `sector_multipliers` | IRIS 2025 Figure A1 — all-incident relative frequency by NAICS 2-digit | Sector multiplier in all vector engines; 20 sectors from education (1.60x) to utilities (0.62x) |
| `revenue_band_multipliers` | IRIS 2025 Figure A2 — all-incident relative frequency by revenue band | Revenue multiplier; 6 bands from under_10m (0.60x) to over_100b (3.46x) |
| `floor_anchors` | IRIS Ransomware Spotlight Table 3 | Overall floor (0.00465) and ceiling (0.10) for sanity checks |
| `ransomware_overall_share` | IRIS Ransomware Spotlight Table 1 | 0.317 (31.7% of all incidents are ransomware) -- used as denominator in sector/revenue share adjustment |
| `ransomware_sector_shares` | IRIS Ransomware Spotlight Figure 13 | Per-sector ransomware proportion (hospitality 73%, manufacturing 51%, education 50%...) |
| `ransomware_sector_loss_shares` | IRIS Ransomware Spotlight Figure 13 | Per-sector ransomware loss share (transportation 84%, education 79%, manufacturing 79%...) |
| `ransomware_revenue_shares` | IRIS Ransomware Spotlight Figure 15 | Revenue band ransomware loss share (peaks at $1B-$10B: 53%) |
| `ransomware_revenue_prob_gte2` | IRIS Ransomware Spotlight Table 3 | Annual probability of >=2 ransomware events by revenue band |

**Key design decision**: Sector multipliers are IRIS all-incident multipliers (scenario-independent), then adjusted at runtime by each scenario's sector share. This means the same IRIS data serves all scenarios; scenario-specific differentiation comes from the scenario's `sector_shares`.

### 5.2 Beazley Q3 2025 Threat Briefing

**File**: `reference/beazley/extracted.json`

**Source**: Beazley Q3 2025 Threat Briefing (free download from beazley.com)

**Extracted**: 2026-05-24 

| Field | Citation | Used For |
|-------|----------|----------|
| `initial_access_vectors` | Beazley Q3 2025 | VPN credential proportion: 48%. RDP initial access: 6-10%. |
| `ransomware_trends` | Beazley Q3 2025 | +16% YoY ransomware claims. Healthcare 22% share. |
| `vector_proportions` | Derived from multi-source IR reports (Beazley, Verizon, Unit42, Mandiant, CrowdStrike, Sophos) | The four-vector PERT ranges used in RansomwareScenario: credential [45,52,58]%, exploitation [18,22,28]%, phishing [12,17,22]%, supply_chain [4,6,10]% |

**Key design decision**: Vector proportions are derived from multiple sources (Beazley, Verizon, Unit42, Mandiant, CrowdStrike, Sophos), not from any single report. The ranges capture inter-source disagreement.

### 5.3 Coalition 2025 Cyber Claims Report

**File**: `reference/coalition/extracted.json`

**Source**: Coalition 2025 Cyber Claims Report (2024 data). Free with email form. Secondary confirmation from Risk & Insurance article.

**Extracted**: 2026-05-24 

| Field | Citation | Used For |
|-------|----------|----------|
| `claims_frequency` | Coalition 2025 Claims Report | Global 1.48%, US 1.54% claim frequency |
| `claims_frequency_by_revenue_band` | Coalition 2025 + Risk & Insurance | under_25m: 1.07%, 25m-100m: 3.99%, over_100m: 5.97% |
| `ransomware` | Coalition 2025 | 20% share of claims; standalone frequency 0.31%; avg loss $292K |
| `sector_claims_frequency` | Coalition 2025 | Consumer staples 2.6%, materials 2.2%, industrials 1.64%, healthcare 1.38% |
| `bias_correction` | Derived: Coalition 2025 vs NAIC 2025 | Factor 3.70x -- Coalition policyholders 73% fewer claims than NAIC market average |

**Bias correction rationale**: Coalition's policyholder base is self-selected (actively insured, often with better security). NAIC reports market-wide statistics from statutory filings. The 3.70x factor adjusts Coalition's frequencies to approximate market-representative rates. Derived by comparing Coalition's global claim frequency (1.48%) against NAIC market data.

### 5.4 At-Bay 2025 InsurSec Report

**File**: `reference/at_bay/extracted.json`

**Source**: At-Bay 2025 InsurSec Report (2024 data, email form required). Secondary confirmation from BusinessWire press release.

**Extracted**: 2026-05-24 

| Field | Citation | Used For |
|-------|----------|----------|
| `ransomware_vpn_correlation` | At-Bay 2025 + BusinessWire | VPN involved in 80% of ransomware, VPN specifically exploited in 66% |
| `frequency_trends` | At-Bay 2025 | +16% overall, +19% ransomware, +46% midmarket ransomware |
| `tech_multipliers` | Derived from At-Bay + Beazley VPN/RDP data | 6 technology multipliers loaded by `data/common.py` |

**Technology multipliers** (loaded as TECH_MULTIPLIERS):

| Key | PERT Range | Direction | Rationale |
|-----|-----------|-----------|-----------|
| `rdp_exposed` | [1.1, 1.3, 1.5] | Amplifying | Beazley: RDP 6-10% of RW initial access |
| `vpn_vulnerable_vendor` | [1.2, 1.4, 1.6] | Amplifying | At-Bay: VPNs in 80% of RW attacks |
| `large_email_footprint` | [1.1, 1.2, 1.3] | Amplifying | More employees = higher phishing PoA |
| `cloud_primary_no_edge` | [0.5, 0.7, 0.8] | Protective | No edge attack surface |
| `air_gapped` | [0.2, 0.3, 0.5] | Protective | Minimal external exposure |
| `no_remote_access` | [0.4, 0.6, 0.8] | Protective | Removes dominant credential pathway |

### 5.5 GreyNoise 2025/2026

**File**: `reference/greynoise/extracted.json`

**Source**: GreyNoise 2025 Mass Internet Exploitation Report (2024 data) + 2026 State of the Edge Report (H2 2025 data). Free with email form.

**Extracted**: 2026-05-24 

Key fields used by the engine:

| Field | Citation | Used For |
|-------|----------|----------|
| `global_observation_grid` | State of the Edge 2026 p28 + p6 | 5000+ sensors, 80+ countries, 500M sessions/day, 18.3M malicious sessions/day, 3.8M malicious unique source IPs |
| `ip_classification_rates` | Derived from cross-report comparison | Malicious rate PERT [0.20, 0.28, 0.35] at IP level. Used in exploitation scanning parameters. |
| `ransomware_kev_overlap` | Mass Exploitation 2025 p3 + p6 | 28% of CISA KEV CVEs tracked by GreyNoise associated with ransomware. Used as anchor for `ransomware_proportion_of_scanning`. |
| `vpn_vendor_targeting` | State of the Edge 2026 p8-9 | Palo Alto 16.7M sessions, Cisco 3M, Fortinet 1.6M. Contextualizes `vpn_vulnerable_vendor` multiplier. |
| `edge_infrastructure_targeting` | State of the Edge 2026 p7 | Enterprise VPN 2M sessions, RDP 14.2M sessions. Contextualizes RDP exposure risk. |

**Key derivation**: The `grn_malicious_rate` PERT [0.20, 0.28, 0.35] is an IP-level estimate derived from 3.8M malicious unique IPs / ~13.5M total tagged IPs in 2024. The session-level rate (3.7% = 18.3M/500M daily) is stored separately as `grn_session_malicious_rate`. These feed the exploitation vector's ceiling calculation in scenario JSON files.

### 5.6 Proofpoint 2024/2025

**File**: `reference/proofpoint/extracted.json`

**Source**: Proofpoint 2024 State of the Phish (2023 data; 7,500 end users, 1,050 security pros, 15 countries, 183M simulated phishing messages) + Human Factor 2025 Vol. 1 (March 2024 - Feb 2025; 3.4T emails scanned).

**Extracted**: 2026-05-24

Key fields:

| Field | Citation | Used For |
|-------|----------|----------|
| `simulation_failure_rates` | State of the Phish p20 | Overall average 9.3% failure rate. Link-based: 11%, data entry: 3%, attachment: 17%. |
| `industry_failure_rates_2023` | State of the Phish p21 | Per-sector failure rates: best at 6% (marketing), worst at 12% (construction) |
| `industry_resilience_2023` | State of the Phish p23 | Reporting/failure ratio: aerospace 3.2, financial 3.1, education 1.0 |
| `phishing_ceiling_data` | Derived | Overall failure rate PERT [0.06, 0.09, 0.12]. Used as ceiling bound for phishing vector. |
| `bec_monthly_volumes_millions` | Human Factor 2025 p7 | BEC volumes 78M-175M/month. Contextualizes BEC scenario. |

### 5.7 Cofense 2026

**File**: `reference/cofense/extracted.json`

**Source**: Cofense Annual Report 2026 (2025 data vs 2024).

**Extracted**: 2026-05-24

Key cross-validation data:
- Malware delivery +204% YoY
- RAT abuse +900% YoY
- 76% unique initial infection URLs (but 94% infrastructure reuse)
- Sector bypass rates (3-28% of malicious emails bypass perimeter security)

Used primarily for **cross-validation** of Proofpoint phishing data, not directly in engine calculations.

### 5.8 NAIC 2025

**File**: `reference/naic/extracted.json`

**Source**: NAIC 2025 Report on the Cybersecurity Insurance Market (free PDF). Data from statutory filings.

**Extracted**: 2026-05-24 

Key fields:

| Field | Citation | Used For |
|-------|----------|----------|
| `policies_in_force` | NAIC Figure 6 p8 | 4.37M total US cyber policies (2024). Used to contextualize Coalition's ~300K policyholder base as ~6.9% of market. |
| `claims_data_2024` | NAIC Figure 9 p12 | ~50K claims reported, 9,941 closed with payment, 28,555 closed without. Paid/unpaid ratio 34.8%. |
| `threat_landscape_context` | NAIC p16-18 | Cross-references from DBIR 2025, CrowdStrike, FBI IC3: ransomware 44% of breaches, BEC cumulative $17B losses, 80% credential theft increase. |

The NAIC data provides the **denominator** for Coalition bias correction and the **market-wide claims frequency** that validates the engine's output range.

### 5.9 Recorded Future (Placeholder)

**File**: `reference/recorded_future/extracted.json`

**Status**: Placeholder. Monthly ransomware operational tempo summaries pending extraction.

**Intended Use**: More granular operational tempo data for the credential vector ceiling.

### 5.10 Common Cross-Source Parameters

**File**: `reference/common/extracted.json`

**Source**: Cross-source derived parameters and judgment-based estimates.

**Extracted**: 2026-05-24

| Field | Citation | Status | Used For |
|-------|----------|--------|----------|
| `geo_multipliers` | Judgment-informed by DBIR 2025 patterns | Judgment, pending empirical | US [1.1,1.2,1.3], W.Europe [1.0,1.1,1.2], APAC [0.8,0.9,1.1], Other [0.6,0.8,1.0] |
| `profile_multipliers` | Judgment-informed by IRIS+DBIR | Judgment, pending empirical | critical_infrastructure [1.0,1.2,1.3], supply_chain_provider [1.1,1.3,1.5], recent_ma [1.0,1.2,1.3] |
| `dampening_config` | VERIS VCDB (vector_k) + judgment (factor_k) | vector_k empirically supported; factor_k judgment-based | Defaults: factor_k=0.70, vector_k=0.85, max_composite=5.0, veris_pairwise_lifts. Configurable via `config.yaml`. |
| `credibility_k` | Structural parameter from peer grid variance | Semi-empirical | Defaults: exploitation=6.0, credential=10.0, phishing=10.0, supply_chain=40.0. Configurable via `config.yaml`. |
| `data_vintage` | Metadata | N/A | Records source vintage for each data file |

---

## 6. Parameter Choices and Rationale

### 6.1 Floor Anchors

| Parameter | Value | Source | Rationale |
|-----------|-------|--------|-----------|
| `overall_lower_bound` | 0.00465 | IRIS Ransomware Spotlight | Empirical annual probability of cyber events across the IRIS dataset. No profile should produce a TEF below what the insurance claims data actually observes. |
| `overall_upper_bound` | 0.10 | IRIS Ransomware Spotlight | Empirical upper bound. Used as sanity check ceiling and in max_composite rationale. |

### 6.2 Dampening Parameters

| Parameter | Value | Source | Rationale |
|-----------|-------|--------|-----------|
| `factor_k` | 0.70 (default) | Judgment | Multipliers (sector, revenue, tech, geo) are correlated. A large financial firm likely has better controls, offsetting its higher targeting. k=0.70 means only 70% of the deviation from 1.0 is preserved. Cannot be derived from VERIS: requires population denominators (org count per sector×size bucket) that VCDB does not contain. |
| `vector_k` | 0.85 (default) | VERIS VCDB empirical | Empirically supported by co-occurrence analysis of 10,037 VERIS incidents (1,789 with mapped vectors, 218 multi-vector). See §6.2.1 for derivation. |
| `max_composite` | 5.0 (default) | Judgment | Hard cap on dampened composite. Prevents any single profile from exceeding 5x the base rate through multiplier stacking. IRIS floor (0.47%) to IRIS ceiling (10%) is ~21x; 5x allows meaningful differentiation while preventing runaway stacking. |

All three parameters are configurable via `config.yaml` (bundled defaults) and `~/.tef-estimator/config.yaml` (user overrides), and adjustable at runtime in the web UI Configuration panel.

#### 6.2.1 VERIS Cross-Vector Dampening Derivation

**Script**: `scripts/compute_dampening.py`
**Data**: VERIS Community Database, 10,037 validated incidents

**Method**: For each pair of TEF vectors (exploitation, credential, phishing, supply_chain), compute the lift statistic:

```
lift = P(A ∩ B) / (P(A) × P(B))
```

Where P(X) is the marginal probability of vector X in the incident population. Lift > 1 means vectors co-occur more than independence predicts (complements); lift < 1 means they co-occur less (substitutes). The dampening coefficient k = 1/lift, bounded [0.5, 1.0].

**Findings**: The pairwise correlation structure is **bimodal**, not uniform:

| Pair | Lift | 95% CI | k | Interpretation |
|------|------|--------|---|----------------|
| exploitation × credential | 0.21 | [0.10, 0.34] | 1.0 | Strong substitutes — attackers use one OR the other |
| exploitation × phishing | 0.23 | [0.09, 0.38] | 1.0 | Strong substitutes |
| exploitation × supply_chain | 0.83 | — | 1.0 | Near-independent (low sample) |
| **credential × phishing** | **8.29** | **[7.46, 9.18]** | **0.50** | **Strong complements — phishing IS a credential theft mechanism** |
| credential × supply_chain | 8.98 | [5.57, 12.41] | 0.50 | Strong complements — supply chain attacks often use stolen credentials |
| phishing × supply_chain | 1.33 | — | 0.75 | Weak complements (low sample) |

**Why vector_k = 0.85**: The median pairwise lift is 1.33 (→ k = 0.75), but no single k captures the bimodal structure. The credential-phishing pair (lift 8.3) dominates any mean, while exploitation pairs (lift ~0.2) are nearly independent. k = 0.85 is a defensible aggregate: it dampens the dominant credential-phishing co-occurrence without over-dampening the independent exploitation pairs. The JSON now stores pair-specific lifts (`veris_pairwise_lifts`) for future use if the engine moves to pair-specific dampening.

**Why factor_k remains judgment-based**: Within-vector dampening compresses sector × revenue × tech × geo. To derive this empirically, we would need P(incident | sector=X AND size=Y) / [P(incident | sector=X) × P(incident | size=Y) / P(incident)]. VERIS provides incident counts per sector×size, but not the population denominator (total organizations per sector×size bucket). The within-incident lift (how sector and size co-occur among incidents) conflates the risk interaction effect with population correlation (financial institutions tend to be large). Without population base rates, factor_k cannot be cleanly derived.

**Ransomware-specific**: Only 3 of 804 ransomware incidents with mapped vectors involve multiple vectors (0.4%). Ransomware attackers strongly specialize: 755/804 use exploitation alone. Cross-vector dampening is less impactful for ransomware than for general threats.

**Future improvement**: Replace the single vector_k with a pair-specific dampening matrix. This would apply k ≈ 1.0 between exploitation and credential/phishing (they are alternatives), and k ≈ 0.12 between credential and phishing (they heavily co-occur).

### 6.3 Vector Proportions (Ransomware)

| Vector | PERT [low, mode, high] | Source |
|--------|------------------------|--------|
| Exploitation | [18%, 22%, 28%] | Derived from multi-source IR reports |
| Credential | [45%, 52%, 58%] | Derived from multi-source IR reports |
| Phishing | [12%, 17%, 22%] | Derived from multi-source IR reports |
| Supply Chain | [4%, 6%, 10%] | Derived from multi-source IR reports |

Modes sum to 97% (within the 85-115% tolerance for custom scenarios). The ranges capture inter-source disagreement.

### 6.4 Base Rate Triangulation (Ransomware)

Three independent estimation anchors, each converting observed LEF to TEF via population-level susceptibility division (10–30%):

| Anchor | PERT | Derivation |
|--------|------|------------|
| Operational tempo | [1.1%, 2.5%, 6.7%] | Ransomware.live ~4,000 listings/yr × 5-10× underreporting → 20-40K events ÷ 6M businesses → 0.33-0.67% LEF ÷ susceptibility 10-30% → TEF |
| IRIS back-calculation | [0.5%, 1.5%, 8.0%] | IRIS overall LEF 0.465% × ransomware share 31.7% → 0.147% LEF ÷ susceptibility 10-30% → TEF. Already expressed as TEF. |
| Coalition market-adjusted | [3.0%, 6.0%, 15.0%] | Coalition 0.31% standalone × 3.70 bias correction → 0.93-1.48% market-adjusted LEF ÷ susceptibility 10-30% → TEF |
| **Consensus** | [**1.0%, 3.0%, 10.0%**] | Conservative synthesis: anchor modes 2.5%, 1.5%, 6.0% → mean 3.3% → rounded to 3% |

The wide IRIS range (0.5-8.0%) reflects sensitivity to the assumed susceptibility denominator. The Coalition anchor produces the highest values because its LEF data is already bias-corrected.

#### 6.4.1 Population-Level Susceptibility Prior

The susceptibility used in base rate derivation (10–30%) is a **data-preparation parameter**, not an organizational assessment. Published sources (Coalition claims, IRIS incidents, Ransomware.live listings) report LEF — events that actually happened (TEF × susceptibility = LEF). Converting to TEF requires dividing by susceptibility.

This population-level susceptibility represents "the average organization with average controls." It is NOT the same as org-specific vulnerability in FAIR — org-specific adjustment happens downstream through the multiplier stack (sector, revenue, technology, geography).

Empirical anchors constraining the 10–30% range:
- **Mandiant M-Trends**: ~30% of intrusions lead to ransomware deployment (susceptibility given intrusion)
- **CrowdStrike breakout data**: 20-40% initial access success × 30% deployment success = 6-12% end-to-end
- **Coalition implied**: 0.31% claims frequency (LEF). If TEF = 3% (our consensus mode), implied susceptibility = 0.31/3 = ~10%

The range 10–30% brackets available evidence and matches the BEC methodology.

### 6.5 Sector Multiplier Adjustment

The adjusted sector multiplier for a given scenario is:
```
adjusted = common.all_incident_multiplier x (scenario_sector_share / scenario_overall_share)
```

Example for manufacturing in ransomware:
```
adjusted = 1.03 (IRIS all-incident) x (0.51 / 0.317) = 1.03 x 1.61 = 1.66
```
Manufacturing has a near-average all-incident rate (1.03x) but a disproportionately high ransomware share (51% of its incidents are ransomware, vs. 31.7% average). The adjustment captures scenario-specific sector exposure.

### 6.6 Revenue Band Adjustment

Same formula but using revenue-specific scenario shares. For ransomware, revenue shares peak at \$100M-\$1B (48%) and \$1B-\$10B (53%), then drop sharply at \$10B+ (16%) and >$100B (0.8%). This reflects that the largest enterprises have better defenses, not that they're targeted less.

### 6.7 Coalition Bias Correction Factor

**Value**: 3.70x

**Derivation**: Coalition policyholders experience 73% fewer claims than the NAIC market average. This is expected: actively insured organizations with Coalition as carrier have undergone underwriting assessment, likely have better security hygiene, and may have Coalition's Active Insurance monitoring.

`Market-representative rate = Coalition raw frequency x 3.70`

This factor is used in the ransomware scenario's Coalition anchor in the base rate triangulation.

---

## 7. Scenario System

### 7.1 Built-in Scenarios

**Ransomware** (`data/scenarios/ransomware.py` + `ransomware.json`)
- 4 vectors: exploitation (22%), credential (52%), phishing (17%), supply chain (6%)
- Base rate consensus: 3.0% annual probability (corrected from 1.0% after LEF→TEF susceptibility conversion)
- Overall share: 31.7% of all cyber incidents (IRIS)
- Full sector and revenue share data from IRIS Ransomware Spotlight

**BEC** (`data/scenarios/bec.py` + `bec.json`)
- 4 vectors: phishing (65%), credential (22%), supply chain (10%), exploitation (3%)
- Base rate consensus: 10.0% annual probability (BEC is much more frequent)
- Overall share: 12% of all breaches (DBIR 2025 + FBI IC3)
- BEC-specific sector shares from FBI IC3/Verizon (not IRIS, which doesn't publish BEC-specific data)
- BEC-specific revenue shares: scales less steeply than ransomware; small businesses heavily targeted

### 7.2 Custom Scenarios

**Module**: `data/scenarios/custom.py`

Allows analysts to define threat scenarios via JSON without writing Python. A custom scenario JSON requires 6 fields:

```json
{
  "scenario_name": "Data Exfiltration",
  "scenario_slug": "data_exfil",
  "vector_proportions": {
    "exploitation": [0.10, 0.20, 0.30],
    "credential": [0.30, 0.40, 0.50],
    "phishing": [0.15, 0.25, 0.35],
    "supply_chain": [0.05, 0.15, 0.20]
  },
  "base_rate": {
    "consensus": [0.005, 0.015, 0.04]
  },
  "overall_share": 0.10
}
```

**Validation rules**:
- All 6 required fields must be present
- Vector names must be from {exploitation, credential, phishing, supply_chain}
- At least one vector must be defined
- Vector proportion modes must sum to 0.85-1.15 (allows rounding tolerance)
- `base_rate` must include a `consensus` key

**Optional fields** with sensible defaults:
- `sector_shares`: defaults to None (uses overall_share)
- `revenue_shares`: defaults to overall_share for all bands
- `credential_tempo`: defaults from ransomware baseline
- `exploitation_scanning`: defaults from ransomware baseline
- `output_templates`: defaults with scenario_name substituted
- Additional base rate anchors (e.g., `anchor_1`, `anchor_2`)

**`generate_template(path)`**: Writes a template JSON file that passes validation and runs successfully in the engine.

Keys prefixed with `_` are treated as metadata/notes throughout and filtered during loading.

---

## 8. Credibility Blending

### 8.1 Bühlmann Credibility Theory

**Module**: `credibility.py`

When an organization has its own telemetry data (e.g., WAF logs showing exploitation attempts, email gateway logs showing phishing attempts), the engine can blend this observed frequency with the population-level prior estimate.

The Buhlmann credibility formula:
```
blended = Z x adjusted_observed + (1-Z) x prior
Z = effective_n / (effective_n + k)
```

Where:
- `Z` is the credibility weight (0 to 1)
- `effective_n = observation_periods x detection_coverage`
- `adjusted_observed = raw_observed / detection_coverage`
- `k` is the structural parameter (per vector)

### 8.2 Detection Coverage Adjustment

Detection coverage creates a **two-way adjustment**:
1. **Observation adjusted upward**: If you only detect 60% of attempts, the observed 3/year implies ~5/year actual.
2. **Effective sample size reduced**: Low coverage means higher uncertainty, so credibility grows slower.

### 8.3 Per-Vector k Parameters

| Vector | k | Rationale |
|--------|---|-----------|
| Exploitation | 6.0 | Well-observed via WAF/IDS; credibility grows fast |
| Credential | 10.0 | Moderate observability via auth logs/gateway |
| Phishing | 10.0 | Moderate observability via email gateway |
| Supply Chain | 40.0 | Sparse observation, mostly invisible; credibility grows very slowly |

**Methodology**: k = sigma^2(process) / sigma^2(hypothetical means). sigma^2(hypothetical means) estimated from peer grid TEF variance within revenue bands. Process variance assumed proportional to observation noise based on vector observability characteristics.

### 8.4 Engine Integration

After vector estimation and before cross-vector aggregation:
```python
if profile.telemetry is not None:
    blender = CredibilityBlender()
    for v in vectors:
        obs = profile.telemetry.get(v.vector_name.lower().replace(" ", "_"))
        if obs is not None:
            blend = blender.blend(v.positioned_median, obs)

            # Gamma-inspired posterior band contraction
            log_range = ln(positioned_high) - ln(positioned_low)
            sigma_prior = log_range / (2 * 1.645)
            cv_sq = exp(sigma_prior²) - 1
            alpha_pert = 1 / cv_sq
            n_events = adjusted_observed * effective_n / 4  # convert quarters → years
            alpha_post = alpha_pert + n_events
            sigma_post = sqrt(ln(1 + 1 / alpha_post))

            v.positioned_median = blend.blended
            v.positioned_low  = exp(ln(blended) - 1.645 * sigma_post)
            v.positioned_high = exp(ln(blended) + 1.645 * sigma_post)
            v.enforce_bounds()
```

The credibility blend shifts the point estimate (median) toward the observed rate. The Gamma-inspired posterior contraction narrows the uncertainty band around that shifted estimate — more observation periods produce both a more informed mean and a tighter range. See §8.6 for derivation, empirical contraction rates, and known limitations.

### 8.5 Telemetry Input Format

```python
from tef_estimator.credibility import VectorObservation, OrgTelemetry

telemetry = OrgTelemetry(observations=[
    VectorObservation(
        vector="exploitation",
        annualized_frequency=5.0,    # raw observed rate
        observation_periods=4,        # quarters
        detection_coverage=0.8,       # 80% coverage
    ),
])
```

Or via JSON file (loaded by CLI `--telemetry` flag):
```json
[
  {
    "vector": "exploitation",
    "annualized_frequency": 5.0,
    "observation_periods": 4,
    "detection_coverage": 0.8
  }
]
```

### 8.6 Gamma-Inspired Posterior Band Contraction

#### The Problem

The Bühlmann credibility blend produces a posterior mean that correctly weights population prior against organizational observations. However, the uncertainty band around that estimate also needs to contract with evidence. In prior versions, the positioned band was shifted by a constant ratio (`blended / prior`), which moved the band but preserved its width in log-space. More telemetry produced a better point estimate but identical uncertainty — the output lognormal sigma was invariant to observation volume.

#### Mathematical Motivation

The Bühlmann credibility formula and the Gamma-Poisson conjugate posterior produce the same point estimate. Given a Gamma(α, β) prior on the rate λ, with Poisson observations totaling N events over exposure n:

```
Posterior mean = (α + N) / (β + n) = [β/(β+n)] × (α/β) + [n/(β+n)] × (N/n)
                                    = (1-Z) × prior  + Z × observed
```

where Z = n/(n+β). Setting β = k (the structural credibility parameter) recovers the Bühlmann formula exactly.

This equivalence **motivates** the band contraction approach, but the implementation is not a single coherent Bayesian model — it uses k (calibrated for mean convergence speed) for the point estimate and a separately-fitted α_pert (derived from the PERT range) for the variance. See "Why Two Parameters" and "Limitations" below.

#### Deriving the Posterior Band

The Gamma posterior Gamma(α_post, β_post) has coefficient of variation CV = 1/√α_post. Mapping to a lognormal distribution:

```
σ² = ln(1 + CV²) = ln(1 + 1/α_post)
```

The implementation fits α to match the PERT prior's width rather than using k directly (which was calibrated for mean convergence speed, not prior variance):

1. Compute the PERT-implied log-sigma: `σ_prior = (ln(high) - ln(low)) / (2 × 1.645)`
2. Map to Gamma shape: `CV² = exp(σ²) - 1`, then `α_pert = 1/CV²`
3. Compute observed pseudo-events: `N = adjusted_observed × effective_n / 4` (quarters → years)
4. Update: `α_post = α_pert + N`
5. Posterior sigma: `σ_post = √(ln(1 + 1/α_post))`

At N = 0 (no telemetry), α_post = α_pert, so σ_post = σ_prior, meaning the band is unchanged. As N grows, α_post increases and σ_post decreases monotonically. The band can only contract, never widen.

#### Contraction Rates

The contraction depends on how many pseudo-events accumulate relative to the prior shape α_pert. N = observed_rate × (periods / 4) because `observation_periods` is in quarters but `annualized_frequency` is per year — dividing by 4 converts to a proper event count. Detection coverage cancels in the product (see Limitations below). Computed from the actual credential vector of a Manufacturing / \$100M–$1B / US profile (positioned_low=0.0054, positioned_high=0.29, α_pert≈0.30):

| Observation | N | σ_prior | σ_post | Contraction |
|-------------|---|---------|--------|-------------|
| No telemetry | 0 | 1.21 | 1.21 | 0% |
| 4 quarters (1 yr), rate 0.05 | 0.05 | 1.21 | 1.16 | 4% |
| 8 quarters (2 yr), rate 0.05 | 0.10 | 1.21 | 1.12 | 8% |
| 20 quarters (5 yr), rate 0.05 | 0.25 | 1.21 | 1.02 | 16% |
| 40 quarters (10 yr), rate 0.10 | 1.00 | 1.21 | 0.76 | 38% |

Note: the prior is diffuse (α_pert ≈ 0.30 for a PERT band spanning ~50x), so even modest event counts produce visible contraction. With a typical incident rate of 0.05/year, meaningful contraction (>15%) requires approximately 5 years of observation.

#### Why Two Parameters

The credibility structural parameter k and the PERT-fitted α_pert serve different roles:

- **k** controls how fast the **mean** moves toward the observation. It was calibrated from peer-grid variance ratios and reflects how much population heterogeneity each vector exhibits. Lower k means observations carry more weight faster.
- **α_pert** controls how fast the **band** contracts. It is derived from the prior PERT range (the consensus elicitation from multiple empirical sources) and represents how precisely the rate is known before organizational evidence.

Using k directly as β for the variance would produce an unrealistically diffuse Gamma prior (the PERT is much more informative than k alone implies). Fitting α_pert from the actual PERT range ensures that the prior band matches the elicited expert range and contracts from that calibrated starting point.

This means the system is not a single Bayesian model — it draws on Gamma-Poisson mechanics for the variance update while using Bühlmann credibility (with independently calibrated k) for the mean. The approach is pragmatic: each parameter is fitted to the quantity it controls, at the cost of formal coherence.

#### Limitations

1. **Lognormal approximation at low α.** The PERT bands span ~50–70x (e.g. credential: 0.005 to 0.29), producing α_pert values around 0.22–0.30. At α < 1, the Gamma distribution is monotonically decreasing (no mode) and heavily right-skewed. The lognormal moment-matched approximation (`σ = √(ln(1 + 1/α))`) produces quantiles that diverge from the exact Gamma quantiles — p95 errors of 60–70% at α ≈ 0.30. The contraction direction is correct (more data → tighter σ → tighter Monte Carlo input), but the absolute quantile positions are approximate.

2. **Detection coverage does not affect band contraction.** The pseudo-event count `N = (freq/coverage) × (periods × coverage) / 4 = freq × periods / 4` — coverage cancels algebraically. Coverage correctly affects the **mean** (via Bühlmann Z and adjusted_observed), but the band contracts identically regardless of detection coverage. This is a consequence of the derivation, not a bug: coverage changes the estimated true rate (shifting the band center) but does not change the number of raw observed events.

3. **Zero observed events do not contract the band.** When the observed rate is zero, N = 0 and α_post = α_pert, so σ_post = σ_prior — the multiplicative spread (high/low ratio) stays fixed. The **absolute** band does contract because the Bühlmann blend shifts the mean toward zero, but the relative uncertainty is unchanged. This is correct Bayesian behavior: the CV of a Gamma distribution (1/√α) depends only on the event count, not the exposure time.

4. **Band recentering at telemetry boundary.** The prior PERT band is symmetric in log-space around the geometric mean of its endpoints, not the mode. When telemetry is first provided, the band is reconstructed as a lognormal centered on the blended estimate (≈ the mode at low Z). This recentering shifts both endpoints by ~5% even with near-zero evidence. The alternative — centering on the geometric mean — would cause the band center to diverge from the point estimate, which is harder to explain in practice.

5. **Extreme input guard.** The engine warns when N > 10 × α_pert (observed pseudo-events overwhelm the prior by an order of magnitude). In this regime, the posterior is dominated by the observation and the prior band is effectively discarded — the output will have a very narrow band centered on the observed rate.

6. **Prior shape α is conservative (contraction is slower than warranted).** The formula `σ_prior = (ln(high) − ln(low)) / (2 × 1.645)` treats `positioned_low` and `positioned_high` as the p5/p95 of a lognormal. They are actually products of PERT support bounds (p0/p100) across all multiplier factors — the absolute worst/best-case corners of the parameter space. The actual p5/p95 range is ~1.7× narrower for a single PERT factor and ~2.7× narrower for a product of three. This inflates σ_prior by roughly 1.7–2.7×, making α_pert 3–7× smaller than warranted (e.g. 0.30 instead of ~1–3 for the credential vector). The practical effect: contraction is ~3× slower than a properly calibrated Gamma update would produce — 5 years at rate 0.05 gives 16% contraction versus ~35–40% with corrected α. This is the **conservative direction**: the system requires more evidence before narrowing bands, so it is never overconfident from premature contraction. The proper fix is to moment-match the product of PERT distributions analytically (compute E[∏Xᵢ] and Var[∏Xᵢ] from individual PERT moments, then fit a lognormal), which would give σ_prior that reflects actual uncertainty rather than extreme-corner bounds.

7. **Aggregate lognormal understates the median by ~20%.** The aggregate positioned_median is the sum of four per-vector lognormal medians. For right-skewed distributions, median(X₁+X₂+…+Xₙ) > Σ median(Xᵢ). Monte Carlo simulation shows the sum-of-medians understates the true aggregate median by ~20% and overstates σ by ~30%, producing a fitted lognormal that is shifted left and wider than the true sum distribution. The tail risk (P95) is overstated by ~30% — again the **conservative direction** for a risk tool. The proper fix is the Fenton-Wilkinson approximation: match the first two moments of the sum of lognormals to a single lognormal. This requires storing per-vector μ and σ on VectorEstimate and replacing the current `sum + from_median_and_range` aggregation with moment-matched fitting. The current approach is retained because: (a) the cross-vector dampening (k=0.85) is already an empirical correction for dependence that partially compensates, (b) the fitted lognormal's P5/P95 are derived from the aggregate bounds and are roughly correct even though the median is off, and (c) overstating tail risk is preferable to understating it in a security risk context.

8. **Sensitivity analysis does not vary credibility parameters.** When telemetry is present, the sensitivity analysis varies population-model parameters (base rate, dampening coefficients) but not credibility-specific parameters (k values, detection coverage, observation periods). With telemetry, the estimate is partially anchored to the observed rate, so base_rate sensitivity drops (e.g. from 10× to 3×). The sensitivity output correctly shows this reduced dependence on the prior, but does not reveal the new dominant uncertainty sources — particularly detection coverage and the credibility k — which are now the parameters that would most change the output if varied.

9. **Within-vector dampening is applied before credibility blending.** The credibility prior is the dampened population estimate, not the raw (undampened) composite. This is intentional: dampening corrects for correlated multipliers (a known population-model artifact), and the corrected estimate is our best belief about the population rate. Using the undampened value as the prior would violate the Bühlmann framework assumption that the prior is the true population mean, and would create a discontinuity at the telemetry boundary — providing telemetry that confirms the population rate would paradoxically increase the estimate from the dampened to the undampened value. The practical effect is that for organizations with high population risk factors and clean telemetry, both adjustments push in the same direction (down), yielding a lower estimate than blending from the undampened prior would. This is correct: the prior was overstated, and the telemetry confirms a lower rate.

---

## 9. Output Structure

### 9.1 Three-Tier Model

**Tier 1 (Summary -- the slide)**:
- Positioned median, low, high as annual probability
- Recurrence interval in years
- Vector bar chart data (share of total per vector)
- One-sentence plain language summary
- Peer percentile (if grid available)

**Tier 2 (Analysis -- the analyst workspace)**:
- Lognormal distribution parameters (mu, sigma, p5, median, p95)
- PERT range (min, mode, max)
- Per-vector positioned estimates with primary drivers
- Control priority statement (top vector's #1 control)
- Credibility blending summary (if telemetry provided)

**Tier 3 (Audit -- the challenge layer)**:
- Step-by-step calculation traces per vector
- Triangulation validation
- Validation checks (floor/ceiling, implied LEF at different susceptibilities)
- Contextual warnings
- All data source citations
- Base rate derivation (three-anchor method)
- Explicit statement of what the estimate does NOT include

### 9.2 Output Formats

- **`full_report()`**: Complete text report (Tier 3). All sections.
- **`brief_report()`**: Tier 1 summary. Fits on one slide.
- **`to_dict()`**: JSON-serializable dict with all three tiers.
- **Individual sections**: `vector_breakdown_text()`, `distribution_text()`, `credibility_text()`, `plain_language_summary()`.

### 9.3 Plain Language Summary Template

```
Based on industry data, {scenario} operators attempt to attack organizations
matching your profile roughly once every {recurrence_years} years (range:
{low_yr}-{high_yr} years). The primary attack pathway is {dominant_vector}-based
access ({share}% of estimated frequency), driven by {top_driver}. This measures
how often adversaries TRY -- not how often they succeed. Success probability
depends on your controls (assessed separately).
```

---

## 10. Validation and Audit Trail

### 10.1 Triangulation Validation

Every estimation run validates the analyst's chosen consensus against the independent anchors:
- Convergence check: anchor modes within 10x of each other
- Deviation check: if analyst consensus mode >50% from suggested mode, warns "verify override"
- Per-anchor PERT ranges listed in validation output

### 10.2 Internal Consistency Checks

- `Floor <= Positioned`: positioned estimate respects observed lower bound
- `Positioned <= Ceiling`: positioned estimate below theoretical maximum
- Implied LEF at 5%, 15%, 30% susceptibility compared to IRIS floor
- Vector share percentages (should roughly match input proportions)

### 10.3 Contextual Warnings

| Condition | Warning |
|-----------|---------|
| Floor is binding (positioned within 10% of floor) | "IRIS observed LEF is more informative than the base-rate-plus-adjustments approach" |
| Small/mid-market revenue band | "IRIS under-counts small/mid-market firms due to disclosure requirements. Coalition provides a better anchor." |
| Non-US geography | "IRIS data has a US disclosure bias. Floor is more conservative for non-US firms." |
| Transportation sector | "Low all-incident rate but 84% ransomware loss share. This is a severity signal, not a frequency signal." |
| Always | Dampening coefficient k disclosure |

### 10.4 Calculation Traces

Each vector engine records every arithmetic step:
```
EXPLOITATION VECTOR -- Calculation Trace
----------------------------------------------------------------------
  = IRIS overall floor              0.00465   IRIS 2025 observed LEF
  x Exploitation proportion         0.22000   IR report vector split
  x Sector adjustment               1.65900   IRIS x Ransomware share
  = Base rate (mode)                 0.01000   Three-anchor consensus
  x Exploitation proportion          0.22000   Vector split
  x Sector multiplier               1.65900   IRIS x scenario share
  x Revenue multiplier               0.80000   IRIS x scenario share
  x Vulnerable VPN vendor            1.40000   At-Bay 2025
  x Geography                        1.20000   IRIS geo distribution
  = Raw composite                    2.22000   Product of all multipliers
  dampened() Dampened composite      1.85400   k=0.70, max=5.0
  = Positioned mode                  0.00408   base x proportion x dampened
```

An analyst can substitute their own number at any step and trace the impact downstream.

### 10.5 What the Estimate Explicitly Excludes

Every full report ends with:
- Susceptibility (probability that an attempt succeeds)
- Loss magnitude (financial impact if it does)
- Control effectiveness (reduces susceptibility)
- Attack surface size effect (enters through susceptibility, not TEF)

This is a deliberate design choice: TEF estimates how often adversaries TRY, not how often they SUCCEED. The success probability depends on the organization's controls, which are assessed separately. Combining TEF x Susceptibility yields LEF (Loss Event Frequency), which feeds into the full FAIR loss model.

---

## Appendix: Test Coverage

250 tests across 8 test files covering:
- Engine core: estimation, comparison, sensitivity, warnings, floor enforcement
- All four vector engines: correct multiplier application, floor/ceiling bounds
- Triangulation: consensus computation, convergence, analyst deviation warning
- Credibility blending: blend formula, credibility growth, coverage adjustment, k overrides, engine integration, posterior band contraction (monotonic narrowing with observation volume)
- Custom scenarios: validation, protocol compliance, optional fields, engine integration, template generation
- Distributions: PERT parameterization, lognormal fitting, dampening math
- Profile: validation, derived properties, summary rendering
- Peer percentile: grid computation, percentile calculation
- Result rendering: text reports, JSON serialization, three-tier access

All data loading paths tested. No empirical parameters in test fixtures -- tests use the same JSON-loaded data as production.

---

## Source-to-Vector Mapping

Which sources feed which part of the estimation:

| Source | Exploitation | Credential | Phishing | Supply Chain | Base Rate |
|--------|:---:|:---:|:---:|:---:|:---:|
| IRIS 2025 | floor, multipliers | floor, multipliers | floor, multipliers | floor, multipliers | anchor 2 |
| DBIR 2025/2026 | proportions | proportions | proportions | proportions | dampening k |
| Unit 42 IR 2025/2026 | proportions | proportions | proportions | | |
| M-Trends 2026 (Mandiant) | proportions | | proportions | | |
| CrowdStrike GTR 2026 | proportions | proportions | | | |
| Beazley Q3 2025 | | VPN credential % | | | |
| IBM CODB 2025 | proportions | | | | |
| Coalition 2025 | | | | | anchor 3 |
| At-Bay 2025 | multipliers | multipliers | | | |
| DShield | ceiling | | | | |
| CISA KEV | floor | | | | |
| EPSS | positioning | | | | |
| GreyNoise | ceiling | | | | |
| Ransomware.live | | | | | anchor 1 |
| FBI IC3 (BEC) | | | | | anchor 1 (BEC) |
| NAIC 2025 | | | | | bias correction |
| Proofpoint | | | ceiling | | |
| Cofense | | | validation | | |

Vector proportion benchmarks from all IR report sources are stored in `data/reference/vectors/initial_access_vectors.json` (38 records from 8 sources). Each record includes extraction provenance, source verdicts, bias tags, and quality tier.

---

## Data Acquisition Classification

### Free API — No Authentication

| Source | Endpoint | TEF Vector(s) Fed |
|--------|----------|-------------------|
| DShield / SANS ISC | `isc.sans.edu/api/porthistory/{port}/{start}/{end}/?json` | Exploitation ceiling |
| CISA KEV | `cisa.gov/.../known_exploited_vulnerabilities.json` | Exploitation floor |
| EPSS | `epss.cyentia.com/epss_scores-{date}.csv.gz` | Exploitation positioning |
| Ransomware.live | `api.ransomware.live/v2/victims` | Operational tempo |

### Free API — Requires Free API Key

| Source | Key Env Var | Free Tier Limits | TEF Vector(s) Fed |
|--------|-------------|------------------|-------------------|
| GreyNoise Community v3 | `GREYNOISE_API_KEY` | 50 queries/week | Exploitation ceiling |
| Shodan | `SHODAN_API_KEY` | 100 queries/month | Exploitation denominator |

### Free Download — No Form Required

NAIC, Beazley quarterly briefings, MITRE ATT&CK STIX data.

### Free Download — Email Form Required

Coalition, At-Bay, Proofpoint, Cofense annual reports.

---

## Override Mechanisms

### Configuration File (`config.yaml`)

The primary mechanism for adjusting tunable parameters. All defaults live in the bundled `config.yaml` (single source of truth — no numeric defaults in Python code). To override, create `~/.tef-estimator/config.yaml` with only the values you want to change:

```yaml
# Override susceptibility prior for a more security-mature population
susceptibility_prior:
  low: 0.05
  mode: 0.10
  high: 0.15

# Adjust dampening
dampening:
  factor_k: 0.60
```

User overrides are deep-merged with bundled defaults — omitted keys retain their defaults. The web UI Configuration panel provides runtime adjustment of all parameters (overrides the config file for that session).

**Configurable parameters:**
- `susceptibility_prior`: low/mode/high (population-level LEF→TEF conversion)
- `dampening`: factor_k, vector_k, max_composite
- `credibility_k`: per-vector structural parameters (exploitation, credential, phishing, supply_chain)

### Custom Base Rate

Override the triangulated base rate with your own estimate:

```python
profile = OrganizationProfile(
    sector=Sector.MANUFACTURING,
    revenue_band=RevenueBand.R_100M_1B,
    geography=Geography.US,
    custom_base_rate=0.02,  # 2% annual probability
)
```

Or via CLI: `tef-estimator estimate --sector manufacturing --revenue 100m_1b --geo us --base-rate 0.02`

When a custom base rate is provided, the engine uses `PERT(rate * 0.5, rate, rate * 2.0)` and ignores the scenario's triangulation.

### Custom Dampening

Preferred: set values in `~/.tef-estimator/config.yaml` (see above) or the UI Configuration panel.

For programmatic use, pass a `DampeningConfig` or `TEFConfig` directly:

```python
from tef_estimator.data.common import DampeningConfig

engine = TEFEngine(
    scenario=RansomwareScenario(),
    dampening=DampeningConfig(factor_k=0.60, vector_k=0.90, max_composite=4.0),
)

# Or via TEFConfig (also controls susceptibility prior and credibility k):
from tef_estimator.config import TEFConfig, DampeningParams

cfg = TEFConfig()
cfg.dampening = DampeningParams(factor_k=0.60, vector_k=0.90, max_composite=4.0)
engine = TEFEngine(scenario=RansomwareScenario(), config=cfg)
```

### Custom Base Rate Range

```python
from tef_estimator.data.common import PERTRange

engine = TEFEngine(
    scenario=RansomwareScenario(),
    base_rate_override=PERTRange(0.005, 0.015, 0.04),
)
```

---

## Adding a New Built-in Scenario

1. Create `src/tef_estimator/data/scenarios/my_scenario.json` with the same structure as `ransomware.json`. Required: `base_rate_triangulation` with three anchors plus `consensus`, `vector_proportions`, sector/revenue shares, credential tempo, exploitation scanning, output templates.
2. Create `src/tef_estimator/data/scenarios/my_scenario.py` implementing the `ScenarioDefinition` protocol.
3. Register in CLI: add the scenario to `ScenarioChoice` enum and `SCENARIO_MAP` in `cli.py`.
4. Build the peer grid: `tef-estimator data peer-grid --rebuild`.

The engine does not need modification — it consumes any `ScenarioDefinition` identically.

---

## Open Methodological Questions

1. **Should the base rate PERT be sector-specific from the start?** Currently a single global distribution adjusted by multipliers. An alternative is sector-specific base rates from Coalition claims data, eliminating one layer of multiplication.

2. **How should the exploitation ceiling be presented?** It is so high (~32,000/year for exposed Fortinet) that it provides no useful constraint. Currently kept in Tier 3 only.

3. **What susceptibility prior should IRIS back-calculation use?** U(0.10, 0.40) is a judgment range. Aggregate susceptibility data from real FAIR analyses would calibrate this properly.

4. **Should compare support more than two profiles?** An N-way comparison ("current → after VPN migration → after MFA rollout") would be more powerful for investment prioritisation.

5. **Should pair-specific dampening replace the single vector_k?** VERIS data shows exploitation pairs need k~1.0 while credential-phishing needs k~0.12. A 6-element dampening matrix is more accurate but harder to explain in the audit trail.
