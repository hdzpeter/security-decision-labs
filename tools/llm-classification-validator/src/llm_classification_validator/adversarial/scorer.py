"""Scoring logic for discrimination and ambiguity tests."""

from __future__ import annotations

from llm_classification_validator.models import CaseResult


def score_discrimination(
    label_a: str,
    label_b: str,
    expected_a: str | None = None,
    expected_b: str | None = None,
) -> CaseResult:
    """Score whether two inputs were correctly classified differently.

    The test passes if:
    1. label_a != label_b (discrimination), AND
    2. If expected values are provided, the labels match them.

    Parameters
    ----------
    label_a, label_b:
        The labels assigned by the LLM to the two inputs.
    expected_a, expected_b:
        The expected correct labels (optional). If None, only
        discrimination (label_a != label_b) is checked.

    Returns
    -------
    CaseResult
    """
    discriminated = label_a != label_b

    correct_a = label_a == expected_a if expected_a else True
    correct_b = label_b == expected_b if expected_b else True

    passed = discriminated and correct_a and correct_b

    parts: list[str] = []
    if not discriminated:
        parts.append(f"failed to discriminate, both mapped to '{label_a}'")
    else:
        parts.append("discriminated correctly")
    if not correct_a and expected_a:
        parts.append(f"input_a: expected '{expected_a}', got '{label_a}'")
    if not correct_b and expected_b:
        parts.append(f"input_b: expected '{expected_b}', got '{label_b}'")

    return CaseResult(
        test_type="discrimination",
        test_id="",
        passed=passed,
        details="; ".join(parts),
    )


def score_ambiguity(
    actual_label: str,
    acceptable_labels: list[str],
) -> CaseResult:
    """Score whether a label falls within the acceptable set.

    For genuinely ambiguous inputs, the LLM should produce a label
    that is within the set of reasonable answers.

    Parameters
    ----------
    actual_label:
        The label assigned by the LLM.
    acceptable_labels:
        The set of acceptable labels.

    Returns
    -------
    CaseResult
    """
    passed = actual_label in acceptable_labels if acceptable_labels else True

    if passed:
        details = f"'{actual_label}' is in acceptable set"
    else:
        details = f"'{actual_label}' not in acceptable set {acceptable_labels}"

    return CaseResult(
        test_type="ambiguity",
        test_id="",
        passed=passed,
        details=details,
    )


def pass_rate(results: list[CaseResult]) -> float:
    """Fraction of tests that passed."""
    if not results:
        return 0.0
    return sum(1 for r in results if r.passed) / len(results)


def combined_score(
    discrimination_results: list[CaseResult],
    ambiguity_results: list[CaseResult],
    discrimination_weight: float = 0.6,
    ambiguity_weight: float = 0.4,
) -> float:
    """Compute a weighted combined score from both test types.

    Parameters
    ----------
    discrimination_results:
        Results from discrimination/minimal-pair tests.
    ambiguity_results:
        Results from ambiguity tests.
    discrimination_weight:
        Weight for discrimination score (default 0.6).
    ambiguity_weight:
        Weight for ambiguity score (default 0.4).

    Returns
    -------
    float
        Weighted average score in [0, 1].
    """
    numerator = 0.0
    total_weight = 0.0

    if discrimination_results:
        numerator += pass_rate(discrimination_results) * discrimination_weight
        total_weight += discrimination_weight

    if ambiguity_results:
        numerator += pass_rate(ambiguity_results) * ambiguity_weight
        total_weight += ambiguity_weight

    if total_weight == 0.0:
        return 0.0

    return numerator / total_weight
