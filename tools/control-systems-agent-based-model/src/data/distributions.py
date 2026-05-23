"""src/data/distributions.py

Random sampling utilities.

The simulation should always pass `rng=model.random`.
Tests/calibration can pass `rng=random.Random(seed)`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol
import math


class RNG(Protocol):
    def random(self) -> float: ...
    def uniform(self, a: float, b: float) -> float: ...
    def triangular(self, low: float, high: float, mode: float) -> float: ...
    def betavariate(self, alpha: float, beta: float) -> float: ...
    def expovariate(self, lambd: float) -> float: ...
    def gauss(self, mu: float, sigma: float) -> float: ...


class DistributionType(str, Enum):
    BETA_PERT = "beta_pert"
    BETA = "beta"
    UNIFORM = "uniform"
    TRIANGULAR = "triangular"
    EXPONENTIAL = "exponential"
    POISSON = "poisson"
    WEIBULL = "weibull"
    LOGNORMAL = "lognormal"


def _require_rng(rng: Optional[RNG]) -> RNG:
    if rng is None:
        raise ValueError(
            "RNG is required for sampling. Pass `rng=model.random` (simulation) or "
            "`rng=random.Random(seed)` (tests/calibration)."
        )
    return rng


def _clamp01(p: float) -> float:
    return max(0.0, min(1.0, float(p)))


def bernoulli_trial(p: float, *, rng: Optional[RNG]) -> bool:
    """Return True with probability p."""
    r = _require_rng(rng)
    pp = _clamp01(float(p))
    if pp <= 0.0:
        return False
    if pp >= 1.0:
        return True
    return float(r.random()) < pp


def uniform(a: float, b: float, *, rng: Optional[RNG]) -> float:
    """Uniform sample in [min(a,b), max(a,b)]."""
    r = _require_rng(rng)
    aa = float(a)
    bb = float(b)
    if bb < aa:
        aa, bb = bb, aa
    return float(r.uniform(aa, bb))


def triangular(a: float, b: float, c: float, *, rng: Optional[RNG]) -> float:
    """Triangular(low=a, high=b, mode=c) with clamping."""
    r = _require_rng(rng)
    aa = float(a)
    bb = float(b)
    cc = float(c)
    if bb < aa:
        aa, bb = bb, aa
    cc = min(max(cc, aa), bb)
    return float(r.triangular(aa, bb, cc))


def beta_sample(alpha: float, beta: float, *, rng: Optional[RNG]) -> float:
    """Beta(alpha, beta) sample."""
    r = _require_rng(rng)
    a = float(alpha)
    b = float(beta)
    if a <= 0.0 or b <= 0.0:
        raise ValueError("alpha and beta must be > 0 for beta_sample")
    return float(r.betavariate(a, b))


def beta_pert(minimum: float, mode: float, maximum: float, confidence: float, *, rng: Optional[RNG]) -> float:
    """Beta-PERT distribution.

    Args:
        minimum, mode, maximum: endpoints and mode of the distribution
        confidence: lambda (shape; must be > 0)
        rng: required RNG

    Returns:
        A sample in [minimum, maximum].
    """
    r = _require_rng(rng)

    mn = float(minimum)
    md = float(mode)
    mx = float(maximum)
    lam = float(confidence)

    if mx < mn:
        mn, mx = mx, mn
    md = min(max(md, mn), mx)

    if mx == mn:
        return mn
    if lam <= 0.0:
        raise ValueError("confidence (lambda) must be > 0 for beta_pert")

    alpha = 1.0 + lam * (md - mn) / (mx - mn)
    beta = 1.0 + lam * (mx - md) / (mx - mn)

    x = beta_sample(alpha, beta, rng=rng)
    return float(mn + x * (mx - mn))


def exponential(mean: float, *, rng: Optional[RNG]) -> float:
    """Exponential with given mean."""
    r = _require_rng(rng)
    m = float(mean)
    if m <= 0.0:
        raise ValueError("mean must be > 0 for exponential")
    return float(r.expovariate(1.0 / m))


def poisson_count(lam: float, *, rng: Optional[RNG]) -> int:
    """Poisson(lam) count using Knuth's method (deterministic under RNG)."""
    r = _require_rng(rng)
    lmb = float(lam)
    if lmb < 0.0:
        raise ValueError("lam must be >= 0 for poisson_count")
    if lmb == 0.0:
        return 0
    L = math.exp(-lmb)
    k = 0
    p = 1.0
    while p > L:
        k += 1
        p *= float(r.random())
    return int(k - 1)


def weibull_time(scale: float, shape: float, *, rng: Optional[RNG]) -> float:
    """Weibull time with given scale (>0) and shape (>0).

    Uses inverse-CDF sampling:
        t = scale * (-ln(1-u))**(1/shape)
    """
    r = _require_rng(rng)
    s = float(scale)
    k = float(shape)
    if s <= 0.0 or k <= 0.0:
        raise ValueError("scale and shape must be > 0 for weibull_time")
    u = min(max(float(r.random()), 1e-12), 1.0 - 1e-12)
    return float(s * (-math.log(1.0 - u)) ** (1.0 / k))


def lognormal_loss(mu: float, sigma: float, *, rng: Optional[RNG]) -> float:
    """Lognormal sample where ln(X) ~ Normal(mu, sigma)."""
    r = _require_rng(rng)
    m = float(mu)
    s = float(sigma)
    if s < 0.0:
        raise ValueError("sigma must be >= 0 for lognormal_loss")
    z = float(r.gauss(0.0, 1.0))
    return float(math.exp(m + s * z))
