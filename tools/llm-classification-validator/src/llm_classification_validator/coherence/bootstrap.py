"""Bootstrap confidence interval computation -- standard library only."""

from __future__ import annotations

import random
from typing import Callable, Sequence


def bootstrap_ci(
    data: Sequence[float],
    statistic: Callable[[Sequence[float]], float] | None = None,
    iterations: int = 1000,
    confidence: float = 0.90,
    seed: int | None = 42,
) -> tuple[float, float, float]:
    """Compute a bootstrap confidence interval for a statistic.

    Parameters
    ----------
    data:
        The observed data points.
    statistic:
        A callable that computes a summary statistic from a sample.
        Defaults to the arithmetic mean.
    iterations:
        Number of bootstrap resamples.
    confidence:
        Confidence level (e.g. 0.90 for a 90% CI).
    seed:
        Random seed for reproducibility. Pass None for
        non-deterministic behaviour.

    Returns
    -------
    (point_estimate, ci_lower, ci_upper):
        The point estimate from the original data and the lower/upper
        bounds of the confidence interval.
    """
    if not data:
        return 0.0, 0.0, 0.0

    if statistic is None:
        statistic = _mean

    rng = random.Random(seed)
    n = len(data)
    data_list = list(data)

    point_estimate = statistic(data_list)

    bootstrap_stats: list[float] = []
    for _ in range(iterations):
        sample = rng.choices(data_list, k=n)
        bootstrap_stats.append(statistic(sample))

    bootstrap_stats.sort()

    alpha = 1.0 - confidence
    lower_idx = int((alpha / 2) * iterations)
    upper_idx = int((1.0 - alpha / 2) * iterations) - 1

    # Clamp indices
    lower_idx = max(0, min(lower_idx, iterations - 1))
    upper_idx = max(0, min(upper_idx, iterations - 1))

    return point_estimate, bootstrap_stats[lower_idx], bootstrap_stats[upper_idx]


def _mean(values: Sequence[float]) -> float:
    """Compute the arithmetic mean of a sequence of floats."""
    if not values:
        return 0.0
    return sum(values) / len(values)
