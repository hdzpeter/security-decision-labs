"""
FAIR Risk Calculation Engine
Implements Monte Carlo simulation for FAIR risk quantification
"""

import numpy as np
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from fair_distributions import DistributionFitter, DistributionSampler, validate_percentiles


@dataclass
class FAIRInputs:
    """Structured inputs for FAIR calculation"""
    # TEF (Threat Event Frequency)
    tef_p10: float
    tef_p50: float
    tef_p90: float
    tef_model: str = 'poisson'  # 'poisson' or 'lognormal'
    tef_decompose: bool = False
    contact_freq_p10: Optional[float] = None
    contact_freq_p50: Optional[float] = None
    contact_freq_p90: Optional[float] = None
    prob_action_p10: Optional[float] = None
    prob_action_p50: Optional[float] = None
    prob_action_p90: Optional[float] = None
    zero_inflation: bool = False
    p_zero: float = 0.0
    
    # Susceptibility
    susc_p10: float = 0.0
    susc_p50: float = 50.0
    susc_p90: float = 100.0
    
    # Loss Magnitude - Primary
    productivity_p10: float = 0.0
    productivity_p50: float = 0.0
    productivity_p90: float = 0.0
    productivity_p_zero: Optional[float] = None

    response_p10: float = 0.0
    response_p50: float = 0.0
    response_p90: float = 0.0
    response_p_zero: Optional[float] = None

    replacement_p10: float = 0.0
    replacement_p50: float = 0.0
    replacement_p90: float = 0.0
    replacement_p_zero: Optional[float] = None
    
    # Loss Magnitude - Secondary
    fines_p10: float = 0.0
    fines_p50: float = 0.0
    fines_p90: float = 0.0
    fines_p_zero: Optional[float] = None

    competitive_adv_p10: float = 0.0
    competitive_adv_p50: float = 0.0
    competitive_adv_p90: float = 0.0
    competitive_adv_p_zero: Optional[float] = None

    reputation_p10: float = 0.0
    reputation_p50: float = 0.0
    reputation_p90: float = 0.0
    reputation_p_zero: Optional[float] = None
    
    # SLEF (Secondary Loss Event Frequency)
    slef_p10: float = 0.0
    slef_p50: float = 0.0
    slef_p90: float = 0.0
    
    # Metadata
    time_horizon_years: float = 1.0
    currency: str = 'USD'


@dataclass
class FAIRResults:
    """Results from FAIR Monte Carlo simulation"""
    # Raw samples
    tef_samples: np.ndarray
    susceptibility_samples: np.ndarray
    lef_samples: np.ndarray
    lm_samples: np.ndarray
    ale_samples: np.ndarray
    
    # Summary statistics
    ale_mean: float
    ale_p10: float
    ale_p50: float
    ale_p90: float
    ale_p95: float
    ale_p99: float
    
    lef_mean: float
    lef_p10: float
    lef_p50: float
    lef_p90: float
    
    lm_mean: float
    lm_p10: float
    lm_p50: float
    lm_p90: float
    
    # Loss form breakdowns (P50 values)
    productivity_p50: float
    response_p50: float
    replacement_p50: float
    fines_p50: float
    competitive_adv_p50: float
    reputation_p50: float
    
    # Metadata
    n_simulations: int
    time_horizon_years: float
    currency: str
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'ale': {
                'mean': float(self.ale_mean),
                'p10': float(self.ale_p10),
                'p50': float(self.ale_p50),
                'p90': float(self.ale_p90),
                'p95': float(self.ale_p95),
                'p99': float(self.ale_p99),
            },
            'lef': {
                'mean': float(self.lef_mean),
                'p10': float(self.lef_p10),
                'p50': float(self.lef_p50),
                'p90': float(self.lef_p90),
            },
            'lm': {
                'mean': float(self.lm_mean),
                'p10': float(self.lm_p10),
                'p50': float(self.lm_p50),
                'p90': float(self.lm_p90),
            },
            'loss_forms': {
                'productivity': float(self.productivity_p50),
                'response': float(self.response_p50),
                'replacement': float(self.replacement_p50),
                'fines': float(self.fines_p50),
                'competitive_advantage': float(self.competitive_adv_p50),
                'reputation': float(self.reputation_p50),
            },
            'metadata': {
                'n_simulations': self.n_simulations,
                'time_horizon_years': self.time_horizon_years,
                'currency': self.currency,
            }
        }


class FAIRCalculator:
    """FAIR risk calculation engine with Monte Carlo simulation"""
    PERCENT_FIELDS = {
        "susc_p10", "susc_p50", "susc_p90",
        "slef_p10", "slef_p50", "slef_p90",
        # include PoA if we want to use TEF decomposition with a % input name later:
        "poa_p10", "poa_p50", "poa_p90",
    }


    def __init__(self, n_simulations: int = 100000, random_state: Optional[int] = None):
        self.n_simulations = n_simulations
        self.random_state = random_state
        self.rng = np.random.RandomState(random_state)
    
    def calculate(self, inputs: FAIRInputs) -> FAIRResults:
        """
        Run FAIR Monte Carlo simulation.
        
        Process:
        1. Sample TEF distribution
        2. Sample Susceptibility distribution
        3. Calculate LEF = TEF × Susceptibility
        4. Sample loss magnitude distributions (6 forms)
        5. Calculate lm = Primary + (Secondary × SLEF)
        6. Calculate ALE = LEF × lm
        """
        # Validate inputs
        self._validate_inputs(inputs)
        
        # 1. Sample TEF
        tef_samples = self._sample_tef(inputs)
        
        # 2. Sample Susceptibility
        susc_samples = self._sample_susceptibility(inputs)
        
        # 3. Calculate LEF = TEF × Susceptibility
        lef_samples = tef_samples * (susc_samples / 100.0)
        
        # 4. Sample loss magnitudes
        loss_samples = self._sample_loss_magnitudes(inputs)
        
        # 5. Calculate lm
        lm_samples = self._calculate_lm(loss_samples, inputs)
        
        # 6. Calculate ALE = LEF × lm
        ale_samples = lef_samples * lm_samples
        
        # Adjust for time horizon
        if inputs.time_horizon_years != 1.0:
            ale_samples = ale_samples * inputs.time_horizon_years
            lef_samples = lef_samples * inputs.time_horizon_years
        
        # Compute summary statistics
        results = FAIRResults(
            tef_samples=tef_samples,
            susceptibility_samples=susc_samples,
            lef_samples=lef_samples,
            lm_samples=lm_samples,
            ale_samples=ale_samples,
            
            ale_mean=np.mean(ale_samples),
            ale_p10=np.percentile(ale_samples, 10),
            ale_p50=np.percentile(ale_samples, 50),
            ale_p90=np.percentile(ale_samples, 90),
            ale_p95=np.percentile(ale_samples, 95),
            ale_p99=np.percentile(ale_samples, 99),
            
            lef_mean=np.mean(lef_samples),
            lef_p10=np.percentile(lef_samples, 10),
            lef_p50=np.percentile(lef_samples, 50),
            lef_p90=np.percentile(lef_samples, 90),
            
            lm_mean=np.mean(lm_samples),
            lm_p10=np.percentile(lm_samples, 10),
            lm_p50=np.percentile(lm_samples, 50),
            lm_p90=np.percentile(lm_samples, 90),
            
            productivity_p50=np.percentile(loss_samples['productivity'], 50),
            response_p50=np.percentile(loss_samples['response'], 50),
            replacement_p50=np.percentile(loss_samples['replacement'], 50),
            fines_p50=np.percentile(loss_samples['fines'], 50),
            competitive_adv_p50=np.percentile(loss_samples['competitive_advantage'], 50),
            reputation_p50=np.percentile(loss_samples['reputation'], 50),
            
            n_simulations=self.n_simulations,
            time_horizon_years=inputs.time_horizon_years,
            currency=inputs.currency,
        )
        
        return results

    def _apply_variation(value: float, pct: float, is_percent: bool) -> float:
        """Multiply by (1±pct%) and clamp if percentage."""
        new_val = value * (1.0 + pct / 100.0)
        if is_percent:
            # Clamp strictly to [0, 100]
            return max(0.0, min(100.0, new_val))
        # Non-percent inputs are bounded below by 0
        return max(0.0, new_val)

    def _validate_inputs(self, inputs: FAIRInputs):
        """Validate FAIR inputs"""
        # Validate TEF
        is_valid, errors = validate_percentiles(
            inputs.tef_p10, inputs.tef_p50, inputs.tef_p90, min_val=0
        )
        if not is_valid:
            raise ValueError(f"Invalid TEF percentiles: {errors}")
        
        # Validate Susceptibility
        is_valid, errors = validate_percentiles(
            inputs.susc_p10, inputs.susc_p50, inputs.susc_p90, 
            min_val=0, max_val=100, is_probability=True
        )
        if not is_valid:
            raise ValueError(f"Invalid Susceptibility percentiles: {errors}")
        
        # Validate SLEF if secondary losses exist
        has_secondary = any([
            inputs.fines_p50 > 0,
            inputs.competitive_adv_p50 > 0,
            inputs.reputation_p50 > 0
        ])
        
        if has_secondary:
            is_valid, errors = validate_percentiles(
                inputs.slef_p10, inputs.slef_p50, inputs.slef_p90,
                min_val=0, max_val=100, is_probability=True
            )
            if not is_valid:
                raise ValueError(f"Invalid SLEF percentiles: {errors}")
    
    def _sample_tef(self, inputs: FAIRInputs) -> np.ndarray:
        """Sample Threat Event Frequency distribution"""
        if inputs.tef_decompose:
            # TEF = Contact Frequency × Probability of Action
            # Sample Contact Frequency
            if inputs.tef_model == 'poisson':
                lambda_cf = DistributionFitter.fit_poisson_from_percentiles(
                    inputs.contact_freq_p10, inputs.contact_freq_p50, inputs.contact_freq_p90
                )
                cf_samples = DistributionSampler.sample_poisson(
                    lambda_cf, self.n_simulations, self.random_state
                )
            else:  # lognormal
                loc, mu, sigma = DistributionFitter.fit_lognormal(
                    inputs.contact_freq_p10, inputs.contact_freq_p50, inputs.contact_freq_p90
                )
                cf_samples = DistributionSampler.sample_lognormal(
                    loc, mu, sigma, self.n_simulations, self.random_state
                )
            
            # Sample Probability of Action
            alpha, beta = DistributionFitter.fit_beta_pert(
                inputs.prob_action_p10, inputs.prob_action_p50, inputs.prob_action_p90,
                0, 100
            )
            poa_samples = DistributionSampler.sample_beta(
                alpha, beta, 0, 100, self.n_simulations, self.random_state + 1 if self.random_state else None
            ) / 100.0
            
            # Combine: TEF = CF × PoA
            tef_samples = cf_samples * poa_samples
        
        else:
            # Direct TEF estimation
            if inputs.zero_inflation:
                p_zero, lambda_param = DistributionFitter.fit_zero_inflated_poisson(
                    inputs.tef_p10, inputs.tef_p50, inputs.tef_p90, inputs.p_zero
                )
                tef_samples = DistributionSampler.sample_zero_inflated_poisson(
                    p_zero, lambda_param, self.n_simulations, self.random_state
                )
            elif inputs.tef_model == 'poisson':
                lambda_param = DistributionFitter.fit_poisson_from_percentiles(
                    inputs.tef_p10, inputs.tef_p50, inputs.tef_p90
                )
                tef_samples = DistributionSampler.sample_poisson(
                    lambda_param, self.n_simulations, self.random_state
                )
            else:  # lognormal
                loc, mu, sigma = DistributionFitter.fit_lognormal(
                    max(0.01, inputs.tef_p10), 
                    max(0.01, inputs.tef_p50), 
                    max(0.01, inputs.tef_p90)
                )
                tef_samples = DistributionSampler.sample_lognormal(
                    loc, mu, sigma, self.n_simulations, self.random_state
                )
        
        return tef_samples
    
    def _sample_susceptibility(self, inputs: FAIRInputs) -> np.ndarray:
        """Sample Susceptibility distribution (Beta-PERT)"""
        alpha, beta = DistributionFitter.fit_beta_pert(
            inputs.susc_p10, inputs.susc_p50, inputs.susc_p90, 0, 100
        )
        samples = DistributionSampler.sample_beta(
            alpha, beta, 0, 100, self.n_simulations, 
            self.random_state + 10 if self.random_state else None
        )
        return samples

    def _sample_loss_magnitudes(self, inputs: FAIRInputs) -> Dict[str, np.ndarray]:
        """Sample all 6 forms of loss (lognormal distributions with optional zero-inflation)."""
        loss_samples: Dict[str, np.ndarray] = {}

        def sample_loss(
                p10: float,
                p50: float,
                p90: float,
                seed_offset: int,
                p_zero: Optional[float] = None,
        ) -> np.ndarray:
            """
            Sample a single loss form.

            - If p50 == 0      -> always zero
            - If p10 == 0      -> treat as zero-inflated lognormal
            - If p10 > 0       -> standard 3-point lognormal fit
            """
            # All-zero distribution if median is zero
            if p50 == 0:
                return np.zeros(self.n_simulations)

            rng_seed = (self.random_state + seed_offset) if self.random_state is not None else None

            # Zero-inflated case when P10 == 0 but median > 0
            if p10 == 0:
                # Default zero-rate is 10% if not overridden
                local_p_zero = 0.10 if p_zero is None else float(p_zero)

                # Map overall percentiles (50th and 90th) to conditional percentiles
                # of the positive component:
                #   q* = (q - p_zero) / (1 - p_zero)
                denom = max(1e-6, 1.0 - local_p_zero)
                q50_star = (0.50 - local_p_zero) / denom
                q90_star = (0.90 - local_p_zero) / denom

                # Keep q* in a valid open interval
                q50_star = float(np.clip(q50_star, 1e-6, 1 - 1e-6))
                q90_star = float(np.clip(q90_star, q50_star + 1e-6, 1 - 1e-6))

                # Use the overall p50/p90 as the positive quantiles
                x50_star = max(1.0, p50)
                x90_star = max(1.0, p90)

                loc, mu, sigma = DistributionFitter.fit_lognormal_from_two_quantiles(
                    x_q1=x50_star,
                    q1=q50_star,
                    x_q2=x90_star,
                    q2=q90_star,
                )

                return DistributionSampler.sample_zero_inflated_lognormal(
                    loc=loc,
                    mu=mu,
                    sigma=sigma,
                    p_zero=local_p_zero,
                    size=self.n_simulations,
                    random_state=rng_seed,
                )

            # Standard lognormal fit if P10 > 0
            p10_adj = max(1e-6, p10)
            p50_adj = max(1e-6, p50)
            p90_adj = max(1e-6, p90)

            loc, mu, sigma = DistributionFitter.fit_lognormal(p10_adj, p50_adj, p90_adj)
            return DistributionSampler.sample_lognormal(
                loc=loc,
                mu=mu,
                sigma=sigma,
                size=self.n_simulations,
                random_state=rng_seed,
            )

        # Primary losses
        loss_samples["productivity"] = sample_loss(
            inputs.productivity_p10,
            inputs.productivity_p50,
            inputs.productivity_p90,
            seed_offset=20,
            p_zero=inputs.productivity_p_zero,
        )
        loss_samples["response"] = sample_loss(
            inputs.response_p10,
            inputs.response_p50,
            inputs.response_p90,
            seed_offset=21,
            p_zero=inputs.response_p_zero,
        )
        loss_samples["replacement"] = sample_loss(
            inputs.replacement_p10,
            inputs.replacement_p50,
            inputs.replacement_p90,
            seed_offset=22,
            p_zero=inputs.replacement_p_zero,
        )

        # Secondary losses
        loss_samples["fines"] = sample_loss(
            inputs.fines_p10,
            inputs.fines_p50,
            inputs.fines_p90,
            seed_offset=23,
            p_zero=inputs.fines_p_zero,
        )
        loss_samples["competitive_advantage"] = sample_loss(
            inputs.competitive_adv_p10,
            inputs.competitive_adv_p50,
            inputs.competitive_adv_p90,
            seed_offset=24,
            p_zero=inputs.competitive_adv_p_zero,
        )
        loss_samples["reputation"] = sample_loss(
            inputs.reputation_p10,
            inputs.reputation_p50,
            inputs.reputation_p90,
            seed_offset=25,
            p_zero=inputs.reputation_p_zero,
        )

        return loss_samples

    def _calculate_lm(self, loss_samples: Dict[str, np.ndarray], 
                       inputs: FAIRInputs) -> np.ndarray:
        """
        Calculate Single Loss Event Exposure.
        LM = Primary Loss + (Secondary Loss × SLEF)
        """
        # Primary loss (evaluated for every event; may be $0)
        primary = (
            loss_samples['productivity'] +
            loss_samples['response'] +
            loss_samples['replacement']
        )
        
        # Secondary loss (conditional on SLEF)
        secondary = (
            loss_samples['fines'] +
            loss_samples['competitive_advantage'] +
            loss_samples['reputation']
        )
        
        # Sample SLEF
        if inputs.slef_p50 > 0:
            alpha, beta = DistributionFitter.fit_beta_pert(
                inputs.slef_p10, inputs.slef_p50, inputs.slef_p90, 0, 100
            )
            slef_samples = DistributionSampler.sample_beta(
                alpha, beta, 0, 100, self.n_simulations,
                self.random_state + 30 if self.random_state else None
            ) / 100.0
        else:
            slef_samples = np.zeros(self.n_simulations)
        
        # LM = Primary + (Secondary × SLEF)
        lm = primary + (secondary * slef_samples)
        
        return lm
    
    def sensitivity_analysis(self, inputs: FAIRInputs, 
                           factor: str, 
                           variation_pct: float = 20.0) -> Dict:
        """
        Perform sensitivity analysis on a single FAIR factor.
        
        Args:
            inputs: Base FAIR inputs
            factor: Which factor to vary (e.g., 'tef_p50', 'susc_p50', 'productivity_p50')
            variation_pct: Percentage to vary the factor (+/-)
        
        Returns:
            Dictionary with ALE results at -variation%, baseline, +variation%
        """
        # Get baseline
        baseline_results = self.calculate(inputs)
        baseline_ale = baseline_results.ale_p50
        # is_percent = factor in self.PERCENT_FIELDS

        # down_inputs = self.copy.deepcopy(inputs)
        # setattr(
        #     down_inputs, factor,
        #     self._apply_variation(getattr(inputs, factor), -variation_pct, is_percent)
        # )
        #
        # up_inputs = self.copy.deepcopy(inputs)
        # setattr(
        #     up_inputs, factor,
        #     self._apply_variation(getattr(inputs, factor), variation_pct, is_percent)
        # )
        # Vary factor downward
        inputs_down = self._adjust_factor(inputs, factor, -variation_pct)
        results_down = self.calculate(inputs_down)
        
        # Vary factor upward
        inputs_up = self._adjust_factor(inputs, factor, variation_pct)
        results_up = self.calculate(inputs_up)
        
        # Calculate elasticity: % change in ALE / % change in factor
        elasticity_down = ((results_down.ale_p50 - baseline_ale) / baseline_ale) / (-variation_pct / 100)
        elasticity_up = ((results_up.ale_p50 - baseline_ale) / baseline_ale) / (variation_pct / 100)
        
        return {
            'factor': factor,
            'baseline_ale': baseline_ale,
            'ale_down': results_down.ale_p50,
            'ale_up': results_up.ale_p50,
            'elasticity_down': elasticity_down,
            'elasticity_up': elasticity_up,
            'average_elasticity': (elasticity_down + elasticity_up) / 2,
        }
    
    def _adjust_factor(self, inputs: FAIRInputs, factor: str, pct_change: float) -> FAIRInputs:
        """Create a copy of inputs with one factor adjusted"""
        import copy
        inputs_copy = copy.deepcopy(inputs)
        
        current_value = getattr(inputs_copy, factor)
        new_value = current_value * (1 + pct_change / 100)
        # Clip percentage-based factors to [0, 100] range
        is_percent = factor in ['vulnerability', 'slef']
        if is_percent:
            new_value = np.clip(new_value, 0, 100)
        else:
            # Prevent negative values for non-percentage factors
            new_value = max(0, new_value)

        setattr(inputs_copy, factor, new_value)
        
        return inputs_copy


if __name__ == "__main__":
    # Example FAIR calculation
    print("FAIR Risk Calculation Example\n")
    
    # Define a ransomware scenario
    inputs = FAIRInputs(
        # TEF: 2-5-12 attacks per year (Poisson)
        tef_p10=2, tef_p50=5, tef_p90=12,
        tef_model='poisson',
        
        # Susceptibility: 10-30-60% (controls are moderately effective)
        susc_p10=10, susc_p50=30, susc_p90=60,
        
        # Primary losses (in USD)
        productivity_p10=50000, productivity_p50=180000, productivity_p90=500000,
        response_p10=30000, response_p50=95000, response_p90=250000,
        replacement_p10=10000, replacement_p50=40000, replacement_p90=120000,
        
        # Secondary losses
        fines_p10=0, fines_p50=50000, fines_p90=500000,
        competitive_adv_p10=0, competitive_adv_p50=100000, competitive_adv_p90=1000000,
        reputation_p10=50000, reputation_p50=200000, reputation_p90=800000,
        
        # SLEF: 20-35-60% chance of secondary losses
        slef_p10=20, slef_p50=35, slef_p90=60,
        
        time_horizon_years=1.0,
        currency='USD'
    )
    
    # Run calculation
    calculator = FAIRCalculator(n_simulations=100000, random_state=42)
    results = calculator.calculate(inputs)
    
    # Print results
    print("=" * 60)
    print("FAIR RISK ANALYSIS RESULTS")
    print("=" * 60)
    
    print(f"\nAnnual Loss Expectancy (ALE) in {results.currency}:")
    print(f"  Mean:  ${results.ale_mean:,.0f}")
    print(f"  P10:   ${results.ale_p10:,.0f}")
    print(f"  P50:   ${results.ale_p50:,.0f}")
    print(f"  P90:   ${results.ale_p90:,.0f}")
    print(f"  P95:   ${results.ale_p95:,.0f}")
    print(f"  P99:   ${results.ale_p99:,.0f}")
    
    print(f"\nLoss Event Frequency (LEF) events/year:")
    print(f"  Mean:  {results.lef_mean:.2f}")
    print(f"  P10:   {results.lef_p10:.2f}")
    print(f"  P50:   {results.lef_p50:.2f}")
    print(f"  P90:   {results.lef_p90:.2f}")
    
    print(f"\nSingle Loss Event Exposure (lm) in {results.currency}:")
    print(f"  Mean:  ${results.lm_mean:,.0f}")
    print(f"  P10:   ${results.lm_p10:,.0f}")
    print(f"  P50:   ${results.lm_p50:,.0f}")
    print(f"  P90:   ${results.lm_p90:,.0f}")
    
    print("\nLoss Form Breakdown (P50 values):")
    print(f"  Productivity:          ${results.productivity_p50:,.0f}")
    print(f"  Response:              ${results.response_p50:,.0f}")
    print(f"  Replacement:           ${results.replacement_p50:,.0f}")
    print(f"  Fines & Judgments:     ${results.fines_p50:,.0f}")
    print(f"  Competitive Advantage: ${results.competitive_adv_p50:,.0f}")
    print(f"  Reputation:            ${results.reputation_p50:,.0f}")
    
    # Sensitivity analysis
    print("\n" + "=" * 60)
    print("SENSITIVITY ANALYSIS")
    print("=" * 60)
    
    factors = ['tef_p50', 'susc_p50', 'productivity_p50', 'fines_p50']
    for factor in factors:
        sensitivity = calculator.sensitivity_analysis(inputs, factor, variation_pct=20)
        print(f"\n{factor}:")
        print(f"  Baseline ALE: ${sensitivity['baseline_ale']:,.0f}")
        print(f"  ALE at -20%:  ${sensitivity['ale_down']:,.0f}")
        print(f"  ALE at +20%:  ${sensitivity['ale_up']:,.0f}")
        print(f"  Elasticity:   {sensitivity['average_elasticity']:.2f}")
