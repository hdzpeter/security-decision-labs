"""Tests for PERT, lognormal, and dampening utilities."""

import math

import numpy as np
import pytest

from tef_estimator.data.common import PERTRange
from tef_estimator.distributions import (
    LognormalParams,
    dampen_composite,
    pert_distribution,
    pert_sample,
)


class TestPERTDistribution:
    def test_basic_pert(self):
        r = PERTRange(0.01, 0.05, 0.10)
        dist = pert_distribution(r)
        assert dist is not None
        # Mean should be close to PERT mean: (a + 4b + c) / 6
        expected_mean = (0.01 + 4 * 0.05 + 0.10) / 6
        assert abs(dist.mean() - expected_mean) < 0.01

    def test_pert_bounds(self):
        r = PERTRange(0.001, 0.01, 0.05)
        dist = pert_distribution(r)
        samples = dist.rvs(size=10_000, random_state=42)
        assert samples.min() >= r.low - 1e-10
        assert samples.max() <= r.high + 1e-10

    def test_pert_invalid_range(self):
        with pytest.raises(ValueError, match="low < high"):
            pert_distribution(PERTRange(0.05, 0.03, 0.01))

    def test_pert_sample_shape(self):
        r = PERTRange(0.01, 0.05, 0.10)
        samples = pert_sample(r, size=500, rng=np.random.default_rng(42))
        assert samples.shape == (500,)

    def test_pert_custom_lambda(self):
        r = PERTRange(0.01, 0.05, 0.10)
        dist_default = pert_distribution(r, lam=4.0)
        dist_tight = pert_distribution(r, lam=8.0)
        # Higher lambda -> tighter around mode -> lower variance
        assert dist_tight.var() < dist_default.var()


class TestLognormalParams:
    def test_median(self):
        lp = LognormalParams(mu=-3.0, sigma=0.5)
        assert abs(lp.median - math.exp(-3.0)) < 1e-10

    def test_p5_p95_ordering(self):
        lp = LognormalParams(mu=-3.0, sigma=0.8)
        assert lp.p5 < lp.median < lp.p95

    def test_from_median_and_range(self):
        lp = LognormalParams.from_median_and_range(
            median=0.02, low=0.005, high=0.10
        )
        assert abs(lp.median - 0.02) < 0.005
        assert lp.sigma >= 0.1  # Minimum sigma

    def test_sample_shape(self):
        lp = LognormalParams(mu=-3.0, sigma=0.5)
        samples = lp.sample(size=1000, rng=np.random.default_rng(42))
        assert samples.shape == (1000,)
        assert np.all(samples > 0)

    def test_mean_property(self):
        lp = LognormalParams(mu=-3.0, sigma=0.5)
        expected = math.exp(-3.0 + 0.5**2 / 2)
        assert abs(lp.mean - expected) < 1e-10


class TestDampening:
    def test_identity_at_k1(self):
        assert dampen_composite(2.5, k=1.0) == 2.5

    def test_no_effect_at_k0(self):
        assert dampen_composite(3.0, k=0.0) == 1.0

    def test_dampening_reduces(self):
        raw = 3.0
        dampened = dampen_composite(raw, k=0.7)
        assert 1.0 < dampened < raw

    def test_cap_enforced(self):
        dampened = dampen_composite(100.0, k=0.9, max_cap=5.0)
        assert dampened == 5.0

    def test_formula(self):
        # Dampened = 1 + (Raw - 1) * k
        raw, k = 2.5, 0.7
        expected = 1.0 + (raw - 1.0) * k
        assert abs(dampen_composite(raw, k) - expected) < 1e-10

    def test_below_one_input(self):
        # If raw < 1, dampening should bring closer to 1 (not further)
        dampened = dampen_composite(0.5, k=0.7)
        assert dampened < 1.0
        assert dampened > 0.5  # Pulled toward 1
