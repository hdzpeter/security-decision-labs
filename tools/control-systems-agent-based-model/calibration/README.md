# Calibration Data

The primary loss magnitude model for **information assets** (data breaches).

**Source**: IRIS 2025 Annual Report (Cyentia Institute / Advisen, N=150,000+
events).

**Parameterization**: Two-point lognormal. For each category:
- μ = ln(median)
- σ = (ln(upper_percentile) - μ) / z_score
  (z = 1.6449 for p95, z = 1.2816 for p90)

**Lookup strategy** (fallback ladder):
1. scenario_type anchor (ransomware / data_breach / insider)
2. Multiply by sector ratio (sector_median / baseline_median)
3. Multiply by revenue ratio (revenue_median / baseline_median)
4. If scenario_type unknown → baseline with sector+revenue scaling

**No dwell-time multiplier**: Dwell time does NOT continuously scale
loss magnitude for information assets. The available empirical data
(IBM CODB 2024: <200 days vs >200 days) provides only a binary split
that cannot calibrate a continuous function. Instead, detection stage
determines outcome class through the stage-gated detection model.

### Empirical outage sampler (`empirical_outage.json`)

The primary loss magnitude model for **process assets** (business
interruption). Replaces the duration-binned CSV outage table.

**Source**: NetDiligence Ransomware Spotlight 2024, Tables 5–6.
- SME (<$2B revenue): avg $1M BI cost, max $100M, N=294 claims
- Large (>$2B revenue): avg $27.9M BI cost, max $111M, N=15 claims

**Parameterization**: Two-point lognormal.
- μ = ln(avg_usd) (avg used as median proxy; true median not reported)
- σ = (ln(max_usd) - μ) / z, where z = invnorm(1 - 1/(2N))

**Duration scaling**: Sampled BI cost is multiplied by
(outage_hours / reference_duration_hours). Reference = 72 hours
(3 days), approximately median ransomware recovery. Linear scaling
is the simplest defensible form given a single anchor per revenue tier.

**Why duration-driven**: BI cost scales directly with outage length
(revenue/hour lost, SLA penalties, emergency staffing). This is the
opposite of information-asset breach loss.

**Calibration sensitivity**: The $1M SME anchor is a 5-year average
across all sectors. The NetDiligence Cyber Claims Study 2025 (V1.1)
reports a range for ransomware SME BI: $751K (2024 single-year) to
$1.4M (5-year average, N=316). Healthcare-specific BI data is not
disaggregated in NetDiligence; the $1M anchor is retained as the
cross-industry default.

## Model configuration

`inputs/model_config.yaml` contains global parameters including:

- `response_concurrency_alpha: 0.15` (limited IR parallelism, estimated
  from incident response timelines in public post-mortems)
- `undetected_time_hours: 144` (median dwell time, M-Trends 2025)
- Detection, threat, and scheduling parameters

All parameter choices with empirical grounding are annotated with their
source in the YAML comments.
