"""
FAIR Distribution Fitting and Sampling
Converts P10/P50/P90 percentile inputs to probability distributions
"""

import numpy as np
from scipy import stats, optimize
from typing import Tuple, Optional
import warnings


class DistributionFitter:


    @staticmethod
    def fit_lognormal_from_two_quantiles(
        x_q1: float,
        q1: float,
        x_q2: float,
        q2: float,
    ) -> Tuple[float, float, float]:
        """
        Fit a lognormal distribution from two (x, q) points.

        Args:
            x_q1: value at quantile q1 (must be > 0)
            q1: probability in (0, 1)
            x_q2: value at quantile q2 (must be > 0, and x_q2 >= x_q1)
            q2: probability in (0, 1), q2 > q1

        Returns:
            (loc, mu, sigma) parameters for scipy.stats.lognorm
        """
        if not (0.0 < q1 < 1.0 and 0.0 < q2 < 1.0):
            raise ValueError("Quantiles q1 and q2 must lie in (0, 1).")

        z1 = stats.norm.ppf(q1)
        z2 = stats.norm.ppf(q2)
        if z1 == z2:
            raise ValueError("Quantile probabilities must differ.")

        x_q1 = max(1e-6, x_q1)
        x_q2 = max(1e-6, x_q2)

        sigma = (np.log(x_q2) - np.log(x_q1)) / (z2 - z1)
        sigma = max(1e-6, sigma)
        mu = np.log(x_q1) - z1 * sigma

        # We use loc=0 for these cost distributions
        return 0.0, mu, sigma

    @staticmethod
    def fit_lognormal(p10: float, p50: float, p90: float) -> Tuple[float, float, float]:
        """
        Fit lognormal distribution from percentiles.
        
        Returns:
            (loc, mu, sigma) where:
            - loc: location parameter (shift)
            - mu: mean of underlying normal
            - sigma: std dev of underlying normal
        """
        if p10 <= 0 or p50 <= 0 or p90 <= 0:
            raise ValueError("Lognormal requires all percentiles > 0")
        
        if not (p10 < p50 < p90):
            raise ValueError("Percentiles must satisfy p10 < p50 < p90")
        
        # Use median and 10/90 percentile spacing to estimate parameters
        # For lognormal: ln(X) ~ N(mu, sigma)
        # P50 = exp(mu)
        mu = np.log(p50)
        
        # P10 = exp(mu + z_10 * sigma)
        # P90 = exp(mu + z_90 * sigma)
        # where z_10 ≈ -1.282, z_90 ≈ 1.282
        z_10 = stats.norm.ppf(0.10)
        z_90 = stats.norm.ppf(0.90)
        
        # Solve for sigma using P90/P10 ratio
        sigma = (np.log(p90) - np.log(p10)) / (z_90 - z_10)
        
        # Adjust mu to match median exactly
        mu = np.log(p50)
        
        return 0.0, mu, sigma
    
    @staticmethod
    def fit_beta_pert(p10: float, p50: float, p90: float, 
                      lower_bound: float = 0.0, upper_bound: float = 1.0) -> Tuple[float, float]:
        """
        Fit Beta-PERT distribution from percentiles.
        
        PERT formula: mean = (min + 4*mode + max) / 6
        
        Args:
            p10, p50, p90: Percentile values (will be scaled to [0,1])
            lower_bound: Actual lower bound of the variable
            upper_bound: Actual upper bound of the variable
            
        Returns:
            (alpha, beta) parameters for scipy.stats.beta
        """
        if not (p10 < p50 < p90):
            raise ValueError("Percentiles must satisfy p10 < p50 < p90")
        
        if not (lower_bound <= p10 and p90 <= upper_bound):
            raise ValueError(f"Percentiles must be within [{lower_bound}, {upper_bound}]")
        
        # Scale to [0, 1]
        range_width = upper_bound - lower_bound
        p10_scaled = (p10 - lower_bound) / range_width
        p50_scaled = (p50 - lower_bound) / range_width
        p90_scaled = (p90 - lower_bound) / range_width
        
        # Use method of moments with PERT assumptions
        # Assume p50 is the mode for PERT
        mode = p50_scaled
        min_val = 0.0
        max_val = 1.0
        
        # PERT mean
        mean = (min_val + 4 * mode + max_val) / 6
        
        # PERT variance (standard formula)
        variance = ((mean - min_val) * (max_val - mean)) / 7
        
        # Convert to Beta parameters
        if variance <= 0 or mean <= 0 or mean >= 1:
            # Fallback to uniform-ish
            return 2.0, 2.0
        
        # Beta distribution: mean = alpha / (alpha + beta)
        #                   var = alpha*beta / ((alpha+beta)^2 * (alpha+beta+1))
        alpha_plus_beta = mean * (1 - mean) / variance - 1
        alpha = mean * alpha_plus_beta
        beta = (1 - mean) * alpha_plus_beta
        
        # Ensure valid parameters
        alpha = max(0.5, alpha)
        beta = max(0.5, beta)
        
        return alpha, beta
    
    @staticmethod
    def fit_poisson_from_percentiles(p10: float, p50: float, p90: float) -> float:
        """
        Fit Poisson distribution from percentiles.
        
        Returns:
            lambda (rate parameter)
        """
        if p10 < 0 or p50 < 0 or p90 < 0:
            raise ValueError("Poisson requires non-negative percentiles")
        
        if not (p10 <= p50 <= p90):
            raise ValueError("Percentiles must satisfy p10 <= p50 <= p90")
        
        # For Poisson, use median as approximation for lambda
        # This is reasonable for lambda > 5
        # For smaller lambda, we need to search
        
        def objective(lam):
            """Minimize distance from target percentiles"""
            if lam <= 0:
                return 1e10
            
            dist = stats.poisson(lam)
            pred_p10 = dist.ppf(0.10)
            pred_p50 = dist.ppf(0.50)
            pred_p90 = dist.ppf(0.90)
            
            # Weighted squared error
            error = (
                (pred_p10 - p10) ** 2 +
                4 * (pred_p50 - p50) ** 2 +  # Weight median more
                (pred_p90 - p90) ** 2
            )
            return error
        
        # Initial guess: use median
        initial_guess = max(1.0, p50)
        
        # Optimize
        result = optimize.minimize_scalar(
            objective, 
            bounds=(0.1, max(100, p90 * 2)),
            method='bounded'
        )
        
        return max(0.1, result.x)
    
    @staticmethod
    def fit_zero_inflated_poisson(p10: float, p50: float, p90: float, 
                                   p_zero: float) -> Tuple[float, float]:
        """
        Fit zero-inflated Poisson (ZIP) from percentiles.
        
        Args:
            p10, p50, p90: Percentiles
            p_zero: Probability of structural zero (user-specified)
            
        Returns:
            (p_zero, lambda) for the ZIP distribution
        """
        if not (0 <= p_zero < 1):
            raise ValueError("p_zero must be in [0, 1)")
        
        # If P50 = 0, we have high zero-inflation
        if p50 == 0:
            # Most of the mass is at zero
            # Fit lambda from P90 conditional on non-zero
            if p90 == 0:
                return p_zero, 0.1  # Degenerate case
            
            # Rough estimate: P90 of ZIP ≈ P90 of Poisson component
            lambda_param = max(0.1, p90 / 2)
            return p_zero, lambda_param
        
        # Otherwise, adjust percentiles for non-zero component
        # P(X <= x | X > 0) = [P(X <= x) - p_zero] / (1 - p_zero)
        
        # Approximate lambda from median of non-zero component
        lambda_param = max(0.1, p50)
        
        return p_zero, lambda_param


class DistributionSampler:
    """Samples from fitted distributions"""
    
    @staticmethod
    def sample_lognormal(loc: float, mu: float, sigma: float, 
                        size: int = 10000, random_state: Optional[int] = None) -> np.ndarray:
        """Sample from lognormal distribution"""
        rng = np.random.RandomState(random_state)
        return stats.lognorm.rvs(s=sigma, scale=np.exp(mu), loc=loc, size=size, random_state=rng)

    @staticmethod
    def sample_zero_inflated_lognormal(
        loc: float,
        mu: float,
        sigma: float,
        p_zero: float,
        size: int = 10000,
        random_state: Optional[int] = None,
    ) -> np.ndarray:
        """
        Sample from a zero-inflated lognormal distribution.

        X = 0                    with probability p_zero
        X ~ Lognormal(loc, mu, sigma)  with probability 1 - p_zero

        For numerical stability, p_zero is clamped to [0.0, 0.49].
        """
        # Clamp for mathematical stability; you don't need to clamp at call sites
        p_zero_clamped = float(np.clip(p_zero, 0.0, 0.49))

        rng = np.random.RandomState(random_state)
        is_zero = rng.binomial(1, p_zero_clamped, size=size).astype(bool)

        samples = stats.lognorm.rvs(
            s=sigma,
            scale=np.exp(mu),
            loc=loc,
            size=size,
            random_state=rng,
        )
        samples[is_zero] = 0.0
        return samples
    
    @staticmethod
    def sample_beta(alpha: float, beta: float, lower_bound: float, upper_bound: float,
                   size: int = 10000, random_state: Optional[int] = None) -> np.ndarray:
        """Sample from Beta distribution and scale to [lower_bound, upper_bound]"""
        rng = np.random.RandomState(random_state)
        samples = stats.beta.rvs(alpha, beta, size=size, random_state=rng)
        # Scale from [0,1] to [lower_bound, upper_bound]
        return lower_bound + samples * (upper_bound - lower_bound)
    
    @staticmethod
    def sample_poisson(lambda_param: float, size: int = 10000, 
                      random_state: Optional[int] = None) -> np.ndarray:
        """Sample from Poisson distribution"""
        rng = np.random.RandomState(random_state)
        return stats.poisson.rvs(lambda_param, size=size, random_state=rng)
    
    @staticmethod
    def sample_zero_inflated_poisson(p_zero: float, lambda_param: float,
                                    size: int = 10000, random_state: Optional[int] = None) -> np.ndarray:
        """Sample from zero-inflated Poisson"""
        rng = np.random.RandomState(random_state)
        
        # Draw from Bernoulli for structural zeros
        is_zero = rng.binomial(1, p_zero, size=size)
        
        # Draw from Poisson for non-structural zeros
        poisson_samples = stats.poisson.rvs(lambda_param, size=size, random_state=rng)
        
        # Combine: if is_zero=1, then 0, else Poisson
        samples = np.where(is_zero, 0, poisson_samples)
        
        return samples


def validate_percentiles(p10: float, p50: float, p90: float, 
                        min_val: Optional[float] = None,
                        max_val: Optional[float] = None,
                        is_probability: bool = False) -> Tuple[bool, list]:
    """
    Validate percentile inputs.
    
    Returns:
        (is_valid, errors) where errors is a list of error messages
    """
    errors = []
    
    # Monotonicity
    if p10 > p50:
        errors.append("P10 must be ≤ P50")
    if p50 > p90:
        errors.append("P50 must be ≤ P90")
    
    # Bounds
    if min_val is not None:
        if p10 < min_val:
            errors.append(f"P10 must be ≥ {min_val}")
    
    if max_val is not None:
        if p90 > max_val:
            errors.append(f"P90 must be ≤ {max_val}")
    
    # Probability-specific checks
    if is_probability:
        if p10 < 0 or p90 > 100:
            errors.append("Probabilities must be in [0, 100]%")
    
    return len(errors) == 0, errors


if __name__ == "__main__":
    # Test distribution fitting
    print("Testing FAIR Distribution Fitting\n")
    
    # Test Lognormal (for loss magnitudes)
    print("1. Lognormal (Loss Magnitude)")
    p10, p50, p90 = 50000, 150000, 500000
    loc, mu, sigma = DistributionFitter.fit_lognormal(p10, p50, p90)
    samples = DistributionSampler.sample_lognormal(loc, mu, sigma, size=100000)
    print(f"   Input: P10={p10}, P50={p50}, P90={p90}")
    print(f"   Fitted: mu={mu:.3f}, sigma={sigma:.3f}")
    print(f"   Validation: P10={np.percentile(samples, 10):.0f}, P50={np.percentile(samples, 50):.0f}, P90={np.percentile(samples, 90):.0f}")
    
    # Test Beta-PERT (for probabilities)
    print("\n2. Beta-PERT (Susceptibility)")
    p10, p50, p90 = 10, 30, 60  # percentages
    alpha, beta = DistributionFitter.fit_beta_pert(p10, p50, p90, 0, 100)
    samples = DistributionSampler.sample_beta(alpha, beta, 0, 100, size=100000)
    print(f"   Input: P10={p10}%, P50={p50}%, P90={p90}%")
    print(f"   Fitted: alpha={alpha:.3f}, beta={beta:.3f}")
    print(f"   Validation: P10={np.percentile(samples, 10):.1f}%, P50={np.percentile(samples, 50):.1f}%, P90={np.percentile(samples, 90):.1f}%")
    
    # Test Poisson (for TEF)
    print("\n3. Poisson (Threat Event Frequency)")
    p10, p50, p90 = 2, 5, 12
    lambda_param = DistributionFitter.fit_poisson_from_percentiles(p10, p50, p90)
    samples = DistributionSampler.sample_poisson(lambda_param, size=100000)
    print(f"   Input: P10={p10}, P50={p50}, P90={p90}")
    print(f"   Fitted: lambda={lambda_param:.3f}")
    print(f"   Validation: P10={np.percentile(samples, 10):.0f}, P50={np.percentile(samples, 50):.0f}, P90={np.percentile(samples, 90):.0f}")
    
    # Test Zero-Inflated Poisson
    print("\n4. Zero-Inflated Poisson (TEF with possible zero years)")
    p10, p50, p90 = 0, 2, 8
    p_zero = 0.2
    p_zero_fit, lambda_param = DistributionFitter.fit_zero_inflated_poisson(p10, p50, p90, p_zero)
    samples = DistributionSampler.sample_zero_inflated_poisson(p_zero_fit, lambda_param, size=100000)
    print(f"   Input: P10={p10}, P50={p50}, P90={p90}, p_zero={p_zero}")
    print(f"   Fitted: p_zero={p_zero_fit:.3f}, lambda={lambda_param:.3f}")
    print(f"   Validation: P10={np.percentile(samples, 10):.0f}, P50={np.percentile(samples, 50):.0f}, P90={np.percentile(samples, 90):.0f}")
    print(f"   Actual zero rate: {(samples == 0).mean():.1%}")
