"""
FAIR Risk Aggregation
Combines multiple risk scenarios into portfolio-level metrics
"""

import numpy as np
from typing import List, Dict, Optional
from dataclasses import dataclass
from fair_calculator import FAIRInputs, FAIRCalculator, FAIRResults


@dataclass
class ScenarioMetadata:
    """Metadata for a risk scenario"""
    id: str
    name: str
    asset: str
    threat_actor: str
    attack_vector: str
    adverse_outcome: str
    industry: str


@dataclass
class AggregatedRiskResults:
    """Results from aggregating multiple scenarios"""
    # Total portfolio risk
    total_ale_mean: float
    total_ale_p10: float
    total_ale_p50: float
    total_ale_p90: float
    total_ale_p95: float
    total_ale_p99: float
    
    # Individual scenario contributions
    scenario_contributions: Dict[str, float]  # scenario_id -> ALE P50
    
    # Top risk drivers
    top_scenarios: List[tuple]  # List of (scenario_id, ale_p50, pct_of_total)
    
    # Correlation info
    assumed_correlation: float
    
    # Distribution
    total_ale_samples: Optional[np.ndarray] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON"""
        return {
            'total_ale': {
                'mean': float(self.total_ale_mean),
                'p10': float(self.total_ale_p10),
                'p50': float(self.total_ale_p50),
                'p90': float(self.total_ale_p90),
                'p95': float(self.total_ale_p95),
                'p99': float(self.total_ale_p99),
            },
            'scenario_contributions': {
                k: float(v) for k, v in self.scenario_contributions.items()
            },
            'top_scenarios': [
                {
                    'scenario_id': sid,
                    'ale_p50': float(ale),
                    'pct_of_total': float(pct)
                }
                for sid, ale, pct in self.top_scenarios
            ],
            'assumed_correlation': float(self.assumed_correlation),
        }


class FAIRAggregator:
    """Aggregates multiple FAIR scenarios into portfolio-level risk"""
    
    def __init__(self, n_simulations: int = 100000, random_state: Optional[int] = None):
        self.n_simulations = n_simulations
        self.random_state = random_state
        self.calculator = FAIRCalculator(n_simulations, random_state)
    
    def aggregate_independent(self, 
                             scenario_inputs: Dict[str, FAIRInputs],
                             scenario_metadata: Optional[Dict[str, ScenarioMetadata]] = None) -> AggregatedRiskResults:
        """
        Aggregate scenarios assuming statistical independence.
        
        This is conservative but realistic when scenarios involve:
        - Different assets
        - Different threat actors
        - Different attack vectors
        
        Args:
            scenario_inputs: Dict of scenario_id -> FAIRInputs
            scenario_metadata: Optional metadata for each scenario
        
        Returns:
            Aggregated risk results
        """
        # Calculate individual scenarios
        individual_results = {}
        for scenario_id, inputs in scenario_inputs.items():
            individual_results[scenario_id] = self.calculator.calculate(inputs)
        
        # Sum ALE samples (independence assumption)
        total_ale_samples = np.zeros(self.n_simulations)
        scenario_contributions = {}
        
        for scenario_id, results in individual_results.items():
            total_ale_samples += results.ale_samples
            scenario_contributions[scenario_id] = results.ale_p50
        
        # Compute aggregate statistics
        total_ale_mean = np.mean(total_ale_samples)
        total_ale_p10 = np.percentile(total_ale_samples, 10)
        total_ale_p50 = np.percentile(total_ale_samples, 50)
        total_ale_p90 = np.percentile(total_ale_samples, 90)
        total_ale_p95 = np.percentile(total_ale_samples, 95)
        total_ale_p99 = np.percentile(total_ale_samples, 99)
        
        # Rank scenarios by contribution
        sorted_scenarios = sorted(
            scenario_contributions.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        top_scenarios = [
            (sid, ale, (ale / total_ale_p50) * 100 if total_ale_p50 > 0 else 0)
            for sid, ale in sorted_scenarios
        ]
        
        return AggregatedRiskResults(
            total_ale_mean=total_ale_mean,
            total_ale_p10=total_ale_p10,
            total_ale_p50=total_ale_p50,
            total_ale_p90=total_ale_p90,
            total_ale_p95=total_ale_p95,
            total_ale_p99=total_ale_p99,
            scenario_contributions=scenario_contributions,
            top_scenarios=top_scenarios,
            assumed_correlation=0.0,
            total_ale_samples=total_ale_samples,
        )
    
    def aggregate_with_correlation(self,
                                   scenario_inputs: Dict[str, FAIRInputs],
                                   correlation: float = 0.3) -> AggregatedRiskResults:
        """
        Aggregate scenarios with assumed correlation between them.
        
        Use when scenarios share:
        - Common threat actors
        - Common attack vectors
        - Same time periods
        - Correlated economic factors
        
        Args:
            scenario_inputs: Dict of scenario_id -> FAIRInputs
            correlation: Assumed correlation coefficient (0 to 1)
        
        Returns:
            Aggregated risk results
        """
        if not (0 <= correlation <= 1):
            raise ValueError("Correlation must be between 0 and 1")
        
        # Calculate individual scenarios
        individual_results = {}
        for scenario_id, inputs in scenario_inputs.items():
            individual_results[scenario_id] = self.calculator.calculate(inputs)
        
        # Create correlated samples using Gaussian copula approach
        n_scenarios = len(scenario_inputs)
        
        # Generate correlated normal random variables
        mean = np.zeros(n_scenarios)
        # Correlation matrix: correlation everywhere except diagonal (which is 1)
        cov = np.full((n_scenarios, n_scenarios), correlation)
        np.fill_diagonal(cov, 1.0)
        
        # Generate correlated uniform random variables via normal copula
        rng = np.random.RandomState(self.random_state)
        normal_samples = rng.multivariate_normal(mean, cov, self.n_simulations)
        uniform_samples = stats.norm.cdf(normal_samples)
        
        # Transform uniform samples to match each scenario's ALE distribution
        total_ale_samples = np.zeros(self.n_simulations)
        scenario_contributions = {}
        
        for i, (scenario_id, results) in enumerate(individual_results.items()):
            # Use empirical quantiles to transform uniform to scenario distribution
            quantiles = uniform_samples[:, i]
            ale_samples_correlated = np.percentile(
                results.ale_samples,
                quantiles * 100
            )
            
            total_ale_samples += ale_samples_correlated
            scenario_contributions[scenario_id] = results.ale_p50
        
        # Compute aggregate statistics
        total_ale_mean = np.mean(total_ale_samples)
        total_ale_p10 = np.percentile(total_ale_samples, 10)
        total_ale_p50 = np.percentile(total_ale_samples, 50)
        total_ale_p90 = np.percentile(total_ale_samples, 90)
        total_ale_p95 = np.percentile(total_ale_samples, 95)
        total_ale_p99 = np.percentile(total_ale_samples, 99)
        
        # Rank scenarios
        sorted_scenarios = sorted(
            scenario_contributions.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        top_scenarios = [
            (sid, ale, (ale / total_ale_p50) * 100 if total_ale_p50 > 0 else 0)
            for sid, ale in sorted_scenarios
        ]
        
        return AggregatedRiskResults(
            total_ale_mean=total_ale_mean,
            total_ale_p10=total_ale_p10,
            total_ale_p50=total_ale_p50,
            total_ale_p90=total_ale_p90,
            total_ale_p95=total_ale_p95,
            total_ale_p99=total_ale_p99,
            scenario_contributions=scenario_contributions,
            top_scenarios=top_scenarios,
            assumed_correlation=correlation,
            total_ale_samples=total_ale_samples,
        )
    
    def calculate_diversification_benefit(self,
                                         scenario_inputs: Dict[str, FAIRInputs]) -> Dict:
        """
        Calculate the benefit of diversification (reduction in risk from independence).
        
        Compares:
        - Sum of individual P90s (perfect correlation)
        - Aggregated P90 (independence)
        
        Returns:
            Dictionary with diversification metrics
        """
        # Calculate individual scenarios
        individual_sum_p90 = 0
        for inputs in scenario_inputs.values():
            results = self.calculator.calculate(inputs)
            individual_sum_p90 += results.ale_p90
        
        # Calculate aggregate (independent)
        agg_results = self.aggregate_independent(scenario_inputs)
        
        # Diversification benefit
        diversification_benefit = individual_sum_p90 - agg_results.total_ale_p90
        diversification_benefit_pct = (diversification_benefit / individual_sum_p90 * 100) if individual_sum_p90 > 0 else 0
        
        return {
            'sum_of_individual_p90': individual_sum_p90,
            'aggregate_p90_independent': agg_results.total_ale_p90,
            'diversification_benefit': diversification_benefit,
            'diversification_benefit_pct': diversification_benefit_pct,
        }


# Add missing import
from scipy import stats


if __name__ == "__main__":
    print("FAIR Risk Aggregation Example\n")
    
    # Define 3 different scenarios
    scenarios = {
        'ransomware': FAIRInputs(
            tef_p10=2, tef_p50=5, tef_p90=12,
            tef_model='poisson',
            susc_p10=10, susc_p50=30, susc_p90=60,
            productivity_p10=50000, productivity_p50=180000, productivity_p90=500000,
            response_p10=30000, response_p50=95000, response_p90=250000,
            replacement_p10=10000, replacement_p50=40000, replacement_p90=120000,
            fines_p10=0, fines_p50=50000, fines_p90=500000,
            slef_p10=20, slef_p50=35, slef_p90=60,
        ),
        
        'data_breach': FAIRInputs(
            tef_p10=1, tef_p50=3, tef_p90=8,
            tef_model='poisson',
            susc_p10=5, susc_p50=15, susc_p90=40,
            productivity_p10=20000, productivity_p50=80000, productivity_p90=300000,
            response_p10=50000, response_p50=150000, response_p90=500000,
            replacement_p10=5000, replacement_p50=20000, replacement_p90=80000,
            fines_p10=100000, fines_p50=500000, fines_p90=2000000,
            reputation_p10=100000, reputation_p50=400000, reputation_p90=1500000,
            slef_p10=40, slef_p50=60, slef_p90=85,
        ),
        
        'ddos': FAIRInputs(
            tef_p10=5, tef_p50=12, tef_p90=25,
            tef_model='poisson',
            susc_p10=20, susc_p50=50, susc_p90=80,
            productivity_p10=10000, productivity_p50=50000, productivity_p90=200000,
            response_p10=5000, response_p50=15000, response_p90=50000,
            replacement_p10=0, replacement_p50=5000, replacement_p90=20000,
            slef_p10=0, slef_p50=10, slef_p90=30,
            competitive_adv_p10=0, competitive_adv_p50=50000, competitive_adv_p90=300000,
        ),
    }
    
    # Aggregate assuming independence
    aggregator = FAIRAggregator(n_simulations=100000, random_state=42)
    
    print("=" * 60)
    print("INDEPENDENT AGGREGATION")
    print("=" * 60)
    
    results_independent = aggregator.aggregate_independent(scenarios)
    
    print(f"\nTotal Portfolio ALE (USD):")
    print(f"  Mean:  ${results_independent.total_ale_mean:,.0f}")
    print(f"  P50:   ${results_independent.total_ale_p50:,.0f}")
    print(f"  P90:   ${results_independent.total_ale_p90:,.0f}")
    print(f"  P99:   ${results_independent.total_ale_p99:,.0f}")
    
    print(f"\nTop Risk Scenarios:")
    for i, (sid, ale, pct) in enumerate(results_independent.top_scenarios, 1):
        print(f"  {i}. {sid}: ${ale:,.0f} ({pct:.1f}% of total)")
    
    # Aggregate with correlation
    print("\n" + "=" * 60)
    print("CORRELATED AGGREGATION (ρ=0.3)")
    print("=" * 60)
    
    results_correlated = aggregator.aggregate_with_correlation(scenarios, correlation=0.3)
    
    print(f"\nTotal Portfolio ALE (USD):")
    print(f"  Mean:  ${results_correlated.total_ale_mean:,.0f}")
    print(f"  P50:   ${results_correlated.total_ale_p50:,.0f}")
    print(f"  P90:   ${results_correlated.total_ale_p90:,.0f}")
    print(f"  P99:   ${results_correlated.total_ale_p99:,.0f}")
    
    # Diversification benefit
    print("\n" + "=" * 60)
    print("DIVERSIFICATION BENEFIT")
    print("=" * 60)
    
    div_benefit = aggregator.calculate_diversification_benefit(scenarios)
    print(f"\nSum of Individual P90s: ${div_benefit['sum_of_individual_p90']:,.0f}")
    print(f"Aggregate P90 (Independent): ${div_benefit['aggregate_p90_independent']:,.0f}")
    print(f"Diversification Benefit: ${div_benefit['diversification_benefit']:,.0f}")
    print(f"Diversification Benefit: {div_benefit['diversification_benefit_pct']:.1f}%")
