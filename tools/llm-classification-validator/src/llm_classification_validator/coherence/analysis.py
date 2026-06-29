"""Coherence analysis orchestration.

Computes inter-rater agreement across multiple raters for a set of items
classified into categorical labels.
"""

from __future__ import annotations

from llm_classification_validator.coherence.bootstrap import bootstrap_ci
from llm_classification_validator.coherence.kappa import (
    build_ratings_matrix,
    cohens_kappa,
    fleiss_kappa,
)
from llm_classification_validator.config import CoherenceConfig
from llm_classification_validator.models import DimensionReport, ItemIssue, MetricResult, Verdict
from llm_classification_validator.verdict import (
    aggregate_verdicts,
    compute_verdict_from_threshold,
    interpret_kappa,
)


def run_coherence_analysis(
    raters: dict[str, list[str]],
    config: CoherenceConfig | None = None,
    item_ids: list[str] | None = None,
) -> DimensionReport:
    """Run coherence analysis on classification labels from multiple raters.

    Parameters
    ----------
    raters:
        A dict mapping rater ID to their list of labels. All label lists
        must be the same length (one label per item). At least 2 raters
        are required.
    config:
        Configuration with thresholds and bootstrap settings.
    item_ids:
        Optional list of item identifiers (same length as label lists).
        If provided, per-item disagreements are reported as ItemIssues.

    Returns
    -------
    DimensionReport with metrics including:
        - pairwise Cohen's kappa for each rater pair
        - mean Cohen's kappa across all pairs
        - Fleiss' kappa for all raters
        - bootstrap CI for mean kappa
    """
    if config is None:
        config = CoherenceConfig()

    metrics: list[MetricResult] = []
    rater_ids = sorted(raters.keys())

    if len(rater_ids) < 2:
        return DimensionReport(
            dimension="coherence",
            verdict=Verdict.FAIL,
            metrics=[],
            details={"error": "At least 2 raters required"},
        )

    n_items = len(raters[rater_ids[0]])
    for rid in rater_ids:
        if len(raters[rid]) != n_items:
            return DimensionReport(
                dimension="coherence",
                verdict=Verdict.FAIL,
                metrics=[],
                details={"error": f"Rater '{rid}' has {len(raters[rid])} items, expected {n_items}"},
            )

    # Pairwise Cohen's kappa
    pairwise_kappas: list[float] = []
    for i, rid_a in enumerate(rater_ids):
        for rid_b in rater_ids[i + 1:]:
            kappa = cohens_kappa(raters[rid_a], raters[rid_b])
            pairwise_kappas.append(kappa)
            metrics.append(MetricResult(
                dimension="coherence",
                metric_name=f"cohens_kappa_{rid_a}_vs_{rid_b}",
                value=kappa,
                interpretation=interpret_kappa(kappa),
            ))

    # Mean pairwise kappa
    mean_kappa = sum(pairwise_kappas) / len(pairwise_kappas) if pairwise_kappas else 0.0
    metrics.append(MetricResult(
        dimension="coherence",
        metric_name="mean_kappa",
        value=mean_kappa,
        interpretation=interpret_kappa(mean_kappa),
    ))

    # Fleiss' kappa
    all_rater_labels = [raters[rid] for rid in rater_ids]
    matrix, categories = build_ratings_matrix(all_rater_labels)
    fleiss = fleiss_kappa(matrix) if matrix else 0.0
    metrics.append(MetricResult(
        dimension="coherence",
        metric_name="fleiss_kappa",
        value=fleiss,
        interpretation=interpret_kappa(fleiss),
    ))

    # Bootstrap CI for mean kappa (resample over pairwise values)
    point, ci_lower, ci_upper = bootstrap_ci(
        pairwise_kappas,
        iterations=config.bootstrap.iterations,
        confidence=config.bootstrap.confidence,
        seed=config.bootstrap.seed,
    )
    metrics.append(MetricResult(
        dimension="coherence",
        metric_name="mean_kappa_ci_lower",
        value=ci_lower,
        interpretation=f"{config.bootstrap.confidence:.0%} CI lower bound",
    ))
    metrics.append(MetricResult(
        dimension="coherence",
        metric_name="mean_kappa_ci_upper",
        value=ci_upper,
        interpretation=f"{config.bootstrap.confidence:.0%} CI upper bound",
    ))

    # Verdict
    verdicts: list[Verdict] = []
    for threshold in config.thresholds:
        if threshold.metric == "mean_kappa":
            verdicts.append(compute_verdict_from_threshold(mean_kappa, threshold))
        elif threshold.metric == "fleiss_kappa":
            verdicts.append(compute_verdict_from_threshold(fleiss, threshold))

    overall = aggregate_verdicts(verdicts) if verdicts else Verdict.SKIPPED

    # Per-item disagreement tracking
    item_issues: list[ItemIssue] = []
    if item_ids and len(item_ids) == n_items:
        for idx in range(n_items):
            labels_at_idx = {rid: raters[rid][idx] for rid in rater_ids}
            unique_labels = set(labels_at_idx.values())
            if len(unique_labels) > 1:
                disagreements = ", ".join(f"{rid}={lbl}" for rid, lbl in labels_at_idx.items())
                item_issues.append(ItemIssue(
                    item_id=item_ids[idx],
                    dimension="coherence",
                    severity="warning",
                    message=f"Rater disagreement: {disagreements}",
                ))

    return DimensionReport(
        dimension="coherence",
        verdict=overall,
        metrics=metrics,
        item_issues=item_issues,
        details={"n_items": n_items, "n_raters": len(rater_ids)},
    )
