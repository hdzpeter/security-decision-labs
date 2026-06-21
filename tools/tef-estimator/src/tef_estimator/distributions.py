"""
Distribution utilities for Monte Carlo parameterisation.

PERT for input uncertainty, lognormal for TEF output distributions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats

from tef_estimator.data import PERTRange


def pert_distribution(r: PERTRange, lam: float = 4.0) -> stats.rv_continuous:
    """Create a PERT (modified Beta) distribution from a PERTRange.

    Parameters
    ----------
    r : PERTRange
        (min, mode, max) triple.
    lam : float
        Shape parameter controlling concentration around the mode.
        Default 4.0 is standard PERT.

    Returns
    -------
    scipy.stats frozen distribution
    """
    a, b, c = r.low, r.mode, r.high
    if a >= c:
        raise ValueError(f"PERT requires low < high, got ({a}, {c})")

    # PERT alpha/beta parameters
    mu = (a + lam * b + c) / (lam + 2)
    if abs(c - a) < 1e-12:
        # Degenerate — return a constant
        return stats.uniform(loc=a, scale=0)

    alpha_param = ((mu - a) * (2 * b - a - c)) / ((b - mu) * (c - a))
    if alpha_param <= 0:
        alpha_param = 1.0  # Fallback for edge cases
    beta_param = alpha_param * (c - mu) / (mu - a)
    if beta_param <= 0:
        beta_param = 1.0

    return stats.beta(alpha_param, beta_param, loc=a, scale=c - a)


def pert_sample(r: PERTRange, size: int = 10_000, rng: np.random.Generator | None = None) -> np.ndarray:
    """Draw samples from a PERT distribution."""
    dist = pert_distribution(r)
    if rng is None:
        rng = np.random.default_rng()
    return dist.rvs(size=size, random_state=rng)


@dataclass(frozen=True)
class LognormalParams:
    """Lognormal distribution parameters for Monte Carlo consumers.

    mu and sigma are the parameters of the underlying normal distribution
    (i.e., ln(X) ~ Normal(mu, sigma)).
    """
    mu: float
    sigma: float

    @property
    def median(self) -> float:
        return math.exp(self.mu)

    @property
    def mean(self) -> float:
        return math.exp(self.mu + self.sigma**2 / 2)

    @property
    def p5(self) -> float:
        return math.exp(self.mu - 1.645 * self.sigma)

    @property
    def p95(self) -> float:
        return math.exp(self.mu + 1.645 * self.sigma)

    def sample(self, size: int = 10_000, rng: np.random.Generator | None = None) -> np.ndarray:
        if rng is None:
            rng = np.random.default_rng()
        return rng.lognormal(self.mu, self.sigma, size=size)

    @classmethod
    def from_median_and_range(cls, median: float, low: float, high: float) -> LognormalParams:
        """Derive lognormal params from a positioned estimate and its range.

        Parameters
        ----------
        median : float
            Positioned point estimate (becomes the lognormal median).
        low : float
            Lower bound of the range (targets ~5th percentile).
        high : float
            Upper bound (targets ~95th percentile).
        """
        mu = math.log(median)
        # Use arithmetic mean of the two implied sigmas for robustness
        sigma_from_low = (mu - math.log(max(low, 1e-10))) / 1.645
        sigma_from_high = (math.log(max(high, 1e-10)) - mu) / 1.645
        sigma = max(0.1, (sigma_from_low + sigma_from_high) / 2)
        return cls(mu=round(mu, 3), sigma=round(sigma, 3))


def dampen_composite(raw_composite: float, k: float, max_cap: float = 5.0) -> float:
    """Apply dampening to a raw multiplicative composite.

    Dampened = 1 + (Raw - 1) × k, capped at max_cap.

    Parameters
    ----------
    raw_composite : float
        Product of all multipliers.
    k : float
        Dampening coefficient (0 = no effect beyond base, 1 = full independence).
    max_cap : float
        Hard ceiling on the dampened composite.
    """
    dampened = 1.0 + (raw_composite - 1.0) * k
    return min(dampened, max_cap)
