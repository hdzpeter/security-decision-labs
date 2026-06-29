"""Convergent validity analysis.

Compares LLM-produced labels against an independently derived reference
(typically a transitive mapping through a third framework) using Jaccard
set similarity and Cohen's kappa.
"""

from __future__ import annotations

from llm_classification_validator.coherence.bootstrap import bootstrap_ci
from llm_classification_validator.coherence.kappa import cohens_kappa
from llm_classification_validator.config import ConvergentConfig
from llm_classification_validator.convergent.jaccard import jaccard_similarity
from llm_classification_validator.models import DimensionReport, ItemIssue, MetricResult, Verdict
from llm_classification_validator.verdict import (
    aggregate_verdicts,
    compute_verdict_from_threshold,
    interpret_kappa,
)


def run_convergent_analysis(
    predicted_labels: list[str],
    reference_labels: list[str],
    predicted_sets: list[set[str]] | None = None,
    reference_sets: list[set[str]] | None = None,
    config: ConvergentConfig | None = None,
    item_ids: list[str] | None = None,
) -> DimensionReport:
    """Run convergent validity analysis.

    Supports two modes of comparison, used independently or together:

    1. **Categorical**: predicted_labels vs reference_labels via Cohen's kappa.
    2. **Set-based**: predicted_sets vs reference_sets via Jaccard similarity.

    The reference labels are typically derived from independent sources
    (e.g., a transitive mapping through a third framework composed from
    peer-reviewed crosswalks), not from the LLM itself.

    Parameters
    ----------
    predicted_labels:
        LLM-produced categorical labels (one per item).
    reference_labels:
        Independently derived categorical labels (one per item).
    predicted_sets:
        LLM-produced label sets (one set per item). Optional.
    reference_sets:
        Independently derived label sets (one set per item). Optional.
    config:
        Thresholds and bootstrap settings.

    Returns
    -------
    DimensionReport
    """
    if config is None:
        config = ConvergentConfig()

    metrics: list[MetricResult] = []
    verdicts: list[Verdict] = []

    # Categorical agreement
    if predicted_labels and reference_labels:
        if len(predicted_labels) != len(reference_labels):
            return DimensionReport(
                dimension="convergent",
                verdict=Verdict.FAIL,
                metrics=[],
                details={"error": "Label list length mismatch"},
            )

        kappa = cohens_kappa(predicted_labels, reference_labels)
        metrics.append(MetricResult(
            dimension="convergent",
            metric_name="kappa",
            value=kappa,
            interpretation=interpret_kappa(kappa),
        ))

        # Exact match accuracy
        n = len(predicted_labels)
        matches = sum(1 for p, r in zip(predicted_labels, reference_labels) if p == r)
        accuracy = matches / n if n > 0 else 0.0
        metrics.append(MetricResult(
            dimension="convergent",
            metric_name="accuracy",
            value=accuracy,
            interpretation=f"{matches}/{n} exact matches",
        ))

        for t in config.thresholds:
            if t.metric == "kappa":
                verdicts.append(compute_verdict_from_threshold(kappa, t))

    # Set-based agreement
    if predicted_sets and reference_sets:
        if len(predicted_sets) != len(reference_sets):
            return DimensionReport(
                dimension="convergent",
                verdict=Verdict.FAIL,
                metrics=[],
                details={"error": "Set list length mismatch"},
            )

        jaccards = [
            jaccard_similarity(p, r)
            for p, r in zip(predicted_sets, reference_sets)
        ]
        mean_jac = sum(jaccards) / len(jaccards) if jaccards else 0.0
        metrics.append(MetricResult(
            dimension="convergent",
            metric_name="jaccard",
            value=mean_jac,
            interpretation=f"mean Jaccard over {len(jaccards)} items",
        ))

        # Bootstrap CI
        point, ci_lower, ci_upper = bootstrap_ci(
            jaccards,
            iterations=config.bootstrap.iterations,
            confidence=config.bootstrap.confidence,
            seed=config.bootstrap.seed,
        )
        metrics.append(MetricResult(
            dimension="convergent",
            metric_name="jaccard_ci_lower",
            value=ci_lower,
        ))
        metrics.append(MetricResult(
            dimension="convergent",
            metric_name="jaccard_ci_upper",
            value=ci_upper,
        ))

        for t in config.thresholds:
            if t.metric == "jaccard":
                verdicts.append(compute_verdict_from_threshold(mean_jac, t))

    overall = aggregate_verdicts(verdicts) if verdicts else Verdict.SKIPPED

    # Per-item mismatch tracking
    item_issues: list[ItemIssue] = []
    if predicted_labels and reference_labels:
        ids = item_ids or [str(i) for i in range(len(predicted_labels))]
        for idx, (pred, ref) in enumerate(zip(predicted_labels, reference_labels)):
            if pred != ref and idx < len(ids):
                item_issues.append(ItemIssue(
                    item_id=ids[idx],
                    dimension="convergent",
                    severity="error",
                    message=f"Label mismatch: predicted {pred}, transitive reference {ref}",
                ))
    if predicted_sets and reference_sets:
        ids = item_ids or [str(i) for i in range(len(predicted_sets))]
        for idx, (pred, ref) in enumerate(zip(predicted_sets, reference_sets)):
            missed = ref - pred
            extra = pred - ref
            if missed and idx < len(ids):
                item_issues.append(ItemIssue(
                    item_id=ids[idx],
                    dimension="convergent",
                    severity="warning",
                    message=f"Missing vs reference: {', '.join(sorted(missed))}",
                ))
            if extra and idx < len(ids):
                item_issues.append(ItemIssue(
                    item_id=ids[idx],
                    dimension="convergent",
                    severity="info",
                    message=f"Extra vs reference: {', '.join(sorted(extra))}",
                ))

    return DimensionReport(
        dimension="convergent",
        verdict=overall,
        metrics=metrics,
        item_issues=item_issues,
    )
