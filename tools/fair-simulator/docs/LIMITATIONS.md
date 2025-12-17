# FAIR Risk Quantification Tool – Scope & Limitations

This prototype is designed as a **learning and exploration tool** for FAIR practitioners, not as a drop-in replacement for a fully governed commercial platform.

## 1. What the Tool Does

The tool helps with:

- Monte Carlo simulation of FAIR factors:
  - TEF, Susceptibility, Loss Magnitude, SLEF
- Calculation of:
  - LEF (events/year)
  - LM (currency/event)
  - ALE (currency/year)
- Sensitivity analysis:
  - Local “what-if” analysis around a baseline factor (P50)
- Portfolio aggregation:
  - Independent and correlated aggregation of scenario ALE
  - Portfolio metrics: total ALE, expected events, weighted average LM
- Benchmark insights:
  - IRIS/industry-style LEF/LM reference values by industry and revenue tier

## 2. What the Tool Does *Not* Do

The tool intentionally does **not** automate:

- Scenario selection and scoping
  - Humans must define the adverse outcome, asset, threat community, and path.
- Data derivation:
  - Converting telemetry (e.g., logs, scans, phishing stats) into TEF/Susceptibility inputs. This is perhaps the scope of future work.
- Control modeling:
  - Mapping specific controls or projects to precise changes in TEF/Susceptibility/LM. Again, perhaps the scope of future work.
- Telemetry ingestion:
  - There is no direct integration with CMDB, SIEM, BAS, or ticketing systems.
- Capital or budget decisions:
  - Outputs are *inputs* to decision-making, not automated recommendations.

Many of these steps remain analyst-driven and should involve expert judgment, governance, and peer review.

## 3. Calibration & Real-World Alignment

- The engine is logically consistent and uses standard distributions (Poisson, Lognormal, Beta-PERT).
- However, **it is not calibrated to any specific environment** by default.
- Users must:
  - Align TEF/Susceptibility to observed incident patterns where possible.
  - Use benchmarks as *anchors*, not ground truth.
  - Periodically review whether modeled frequencies and magnitudes are broadly consistent with experience.

## 4. Multi-Year Time Horizons

**How the tool scales risk over time:**

When analyzing risk over multi-year periods (e.g., 2-year, 5-year horizons):

- **LEF scales linearly:** 
  - If annual LEF = 5 events/year, then 2-year LEF = 10 events
  - Assumes constant threat activity over the time horizon
  
- **ALE scales linearly:**
  - If annual ALE = $1M, then 2-year ALE = $2M
  - Since ALE = LEF × LM, and LM is per-event, this follows from LEF scaling

We are making a critical (and not always realistic) assumption of stationary risk profiles that assumes:
- Threat landscape remains constant
- Susceptibility stays the same
- Loss magnitude per event doesn't change
- No control improvements or degradation

This means the approach remains valid for short-term planning where environment is stable
but not for multi-year scenarios with planned control improvements, major architecture changes, or evolving threat landscape

**Possible options for future work:**
- For long horizons with planned changes: Model separate scenarios for "before controls" and "after controls" periods
- Consider sensitivity analysis on time-dependent factors

## 5. Secondary Loss Event Frequency (SLEF) Modeling

**The Pragmatic Single-SLEF Approach:**

This tool uses a **simplified secondary loss model** with a single SLEF parameter representing the probability that a primary loss event triggers additional loss forms (e.g., fines, legal costs, reputation damage).

**How It Works:**
```
For each primary loss event:
  - Generate primary loss (e.g., response costs)
  - Roll dice: Does secondary loss occur? (probability = SLEF)
  - If yes: Generate secondary loss magnitude
  - Total loss = Primary + Secondary (if triggered)
```

**What This Approximates:**
- Multiple distinct secondary loss forms (fines, lawsuits, customer churn) as a single "gate"
- Reality: Each secondary form has its own probability and magnitude
- Model: One aggregate probability (SLEF) and one aggregate magnitude

**Limitations:**
- Cannot distinguish between "10% chance of fine + 30% chance of lawsuit"
- Cannot model correlations between secondary forms
- Oversimplifies scenarios with many loss cascades

**Potential for future work:**
 extending to multiple SLEF parameters (SLEF_fines, SLEF_legal, SLEF_reputation) with independent probabilities and magnitudes for more realistic modeling.

## 6. Zero-Probability Edge Cases (p_zero Handling)

**The Challenge:**

When TEF or Susceptibility approaches zero (e.g., TEF = 0.01 attempts/year), the Poisson-driven LEF calculation can produce scenarios where LEF = 0 for some Monte Carlo iterations.

The tool uses a **hybrid Poisson-Bernoulli approach**:
```python
# For very low TEF × Susceptibility scenarios:
if expected_events < threshold:
    # Model as Bernoulli: "Does ANY event occur?"
    p_any = 1 - exp(-expected_events)  # Poisson(λ) probability of ≥1 event
    events = 1 if random() < p_any else 0
else:
    # Standard Poisson sampling
    events = poisson(expected_events)
```

**What This Means:**

- For **rare scenarios** (LEF < ~0.1): Model becomes "event happens or it doesn't"
- For **typical scenarios** (LEF ≥ 0.1): Standard Poisson distribution
- **Prevents mathematical artifacts** where p_zero dominates and ALE collapses to near-zero

**Practical Impact:**

| Annual LEF | p_zero (no events) | Interpretation |
|------------|-------------------|----------------|
| 0.01 | ~99% | Extremely rare, likely zero events this year |
| 0.1 | ~90% | Rare, but non-negligible chance |
| 1.0 | ~37% | Roughly one event expected |
| 5.0 | ~0.7% | Multiple events almost certain |



Without p_zero handling, ultra-rare scenarios can produce misleading ALE estimates where the mean ALE seems significant, but 99% of simulations show $0 loss, which may lead to overweighting the mean vs. the "nothing happens" reality.


## 7. Interpretation Limits

- ALE and percentiles are **scenario-level expectations**, not promises.
- Tail percentiles (P95, P99) in particular should be treated as:
  - “Stress-test scenarios” rather than precise forecasts.
- The model does not track:
  - Dynamic feedback loops (e.g., control improvements after an incident).
  - Time-varying exposures (e.g., seasonality).

## 8. Audience & Intended Use

This tool is intended to help FAIR practitioners **understand** and **visualize** the impact of their modeling choices.

It is **not** intended to serve as a fully governed, auditable production risk engine without additional processes (governance, model risk management, and calibration to a specific environment).

Use it as a **transparent sandbox and teaching tool**.