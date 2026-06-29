"""Minimal pair and ambiguity case definitions and evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from llm_classification_validator.adversarial.scorer import (
    combined_score,
    pass_rate,
    score_ambiguity,
    score_discrimination,
)
from llm_classification_validator.config import AdversarialConfig
from llm_classification_validator.models import DimensionReport, MetricResult, CaseResult, Verdict
from llm_classification_validator.verdict import compute_verdict


@dataclass
class MinimalPair:
    """A pair of inputs that should be classified differently.

    Used to test whether the LLM can discriminate between subtly
    different inputs that belong to different categories.
    """

    pair_id: str
    input_a: str
    input_b: str
    expected_label_a: str | None = None
    expected_label_b: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AmbiguityCase:
    """An input whose correct classification is legitimately ambiguous.

    Tests whether the LLM assigns a label within the set of acceptable
    answers, rather than demanding a single correct answer.
    """

    case_id: str
    input_text: str
    acceptable_labels: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


# Type for a classifier function: takes input text, returns label string
ClassifierFn = Callable[[str], str]


def run_adversarial_analysis(
    classifier: ClassifierFn,
    minimal_pairs: list[MinimalPair] | None = None,
    ambiguity_cases: list[AmbiguityCase] | None = None,
    config: AdversarialConfig | None = None,
) -> DimensionReport:
    """Run adversarial edge-case analysis.

    Parameters
    ----------
    classifier:
        A function that takes an input string and returns a label string.
        This abstracts the LLM classification step.
    minimal_pairs:
        Pairs of inputs that should produce different labels.
    ambiguity_cases:
        Inputs with multiple acceptable labels.
    config:
        Thresholds for verdict computation.

    Returns
    -------
    DimensionReport
    """
    if config is None:
        config = AdversarialConfig()

    disc_results: list[CaseResult] = []
    amb_results: list[CaseResult] = []

    disc_case_details: list[dict] = []

    # Minimal pair tests
    if minimal_pairs:
        for pair in minimal_pairs:
            label_a = classifier(pair.input_a)
            label_b = classifier(pair.input_b)
            result = score_discrimination(
                label_a, label_b,
                pair.expected_label_a, pair.expected_label_b,
            )
            result.test_id = pair.pair_id
            disc_results.append(result)
            disc_case_details.append({
                "test_id": pair.pair_id,
                "input_a": pair.input_a,
                "input_b": pair.input_b,
                "expected_a": pair.expected_label_a,
                "expected_b": pair.expected_label_b,
                "actual_a": label_a,
                "actual_b": label_b,
                "passed": result.passed,
            })

    amb_case_details: list[dict] = []

    # Ambiguity tests
    if ambiguity_cases:
        for case in ambiguity_cases:
            label = classifier(case.input_text)
            result = score_ambiguity(label, case.acceptable_labels)
            result.test_id = case.case_id
            amb_results.append(result)
            amb_case_details.append({
                "test_id": case.case_id,
                "input": case.input_text,
                "acceptable": case.acceptable_labels,
                "actual": label,
                "passed": result.passed,
            })

    disc_score = pass_rate(disc_results)
    amb_score = pass_rate(amb_results)
    comb = combined_score(
        disc_results, amb_results,
        config.discrimination_weight, config.ambiguity_weight,
    )

    metrics = [
        MetricResult(
            dimension="adversarial",
            metric_name="discrimination_score",
            value=disc_score,
            interpretation=f"{sum(1 for r in disc_results if r.passed)}/{len(disc_results)} pairs discriminated",
        ),
        MetricResult(
            dimension="adversarial",
            metric_name="ambiguity_score",
            value=amb_score,
            interpretation=f"{sum(1 for r in amb_results if r.passed)}/{len(amb_results)} within acceptable set",
        ),
        MetricResult(
            dimension="adversarial",
            metric_name="combined_score",
            value=comb,
        ),
    ]

    # Verdict: only check types that have test cases
    verdicts: list[Verdict] = []
    if disc_results:
        verdicts.append(compute_verdict(
            disc_score, config.discrimination_target, config.discrimination_minimum,
        ))
    if amb_results:
        verdicts.append(compute_verdict(
            amb_score, config.ambiguity_target, config.ambiguity_minimum,
        ))
    if disc_results and amb_results:
        verdicts.append(compute_verdict(
            comb, config.combined_target, config.combined_minimum,
        ))

    if not verdicts:
        overall = Verdict.SKIPPED
    elif any(v == Verdict.FAIL for v in verdicts):
        overall = Verdict.FAIL
    elif any(v == Verdict.MARGINAL for v in verdicts):
        overall = Verdict.MARGINAL
    else:
        overall = Verdict.PASS

    return DimensionReport(
        dimension="adversarial",
        verdict=overall,
        metrics=metrics,
        details={
            "discrimination_cases": disc_case_details,
            "ambiguity_cases": amb_case_details,
        },
    )
