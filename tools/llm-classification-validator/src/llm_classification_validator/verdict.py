"""PASS/MARGINAL/FAIL verdict logic against configurable thresholds."""

from __future__ import annotations

from llm_classification_validator.config import ThresholdConfig
from llm_classification_validator.models import Verdict


def compute_verdict(
    value: float,
    target: float,
    minimum: float,
) -> Verdict:
    """Determine verdict for a single metric value.

    - value >= target: PASS
    - minimum <= value < target: MARGINAL
    - value < minimum: FAIL
    """
    if value >= target:
        return Verdict.PASS
    if value >= minimum:
        return Verdict.MARGINAL
    return Verdict.FAIL


def compute_verdict_from_threshold(
    value: float,
    threshold: ThresholdConfig,
) -> Verdict:
    """Determine verdict using a ThresholdConfig object."""
    return compute_verdict(value, threshold.target, threshold.minimum)


def aggregate_verdicts(verdicts: list[Verdict]) -> Verdict:
    """Aggregate multiple verdicts into an overall verdict.

    Rules:
    - If any verdict is FAIL, overall is FAIL.
    - If any verdict is MARGINAL (and none FAIL), overall is MARGINAL.
    - If all are PASS or SKIPPED, overall is PASS.
    - If all are SKIPPED or ERROR, overall is ERROR.
    """
    if not verdicts:
        return Verdict.SKIPPED

    non_skipped = [v for v in verdicts if v not in (Verdict.SKIPPED, Verdict.ERROR)]
    if not non_skipped:
        return Verdict.ERROR

    if any(v == Verdict.FAIL for v in non_skipped):
        return Verdict.FAIL
    if any(v == Verdict.MARGINAL for v in non_skipped):
        return Verdict.MARGINAL
    return Verdict.PASS


def interpret_kappa(kappa: float) -> str:
    """Return a human-readable interpretation of a kappa value.

    Only flags perfect agreement (1.0). All other interpretations
    depend on the configurable pass/marginal thresholds, not on
    fixed qualitative bins.
    """
    if kappa >= 1.0:
        return "perfect"
    return ""
