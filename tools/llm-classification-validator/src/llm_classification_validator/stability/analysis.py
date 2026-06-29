"""Stability and sensitivity analysis.

Stability: paraphrased inputs should produce the same labels.
Sensitivity: perturbed inputs should produce predictable label changes.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from llm_classification_validator.coherence.bootstrap import bootstrap_ci
from llm_classification_validator.config import StabilityConfig
from llm_classification_validator.convergent.jaccard import jaccard_similarity
from llm_classification_validator.models import DimensionReport, ItemIssue, MetricResult, Verdict
from llm_classification_validator.stability.paraphrase import ParaphraseVariant
from llm_classification_validator.stability.perturbation import PerturbationVariant
from llm_classification_validator.verdict import aggregate_verdicts, compute_verdict_from_threshold


# Type for a classifier: takes input text, returns a dict of label dimensions.
# Example: {"category": "A", "subcategory": "A.1", "tags": "x,y"}
ClassifierFn = Callable[[str], dict[str, str]]


def run_stability_analysis(
    base_items: dict[str, str],
    classifier: ClassifierFn,
    paraphrases: list[ParaphraseVariant] | None = None,
    perturbations: list[PerturbationVariant] | None = None,
    label_dimensions: list[str] | None = None,
    config: StabilityConfig | None = None,
) -> DimensionReport:
    """Run stability and sensitivity analysis.

    Parameters
    ----------
    base_items:
        Map of item_id to original input text.
    classifier:
        Function that takes input text and returns a dict mapping
        label dimension names to label values.
    paraphrases:
        Paraphrase variants to test stability.
    perturbations:
        Perturbation variants to test sensitivity.
    label_dimensions:
        Which label dimensions to track for agreement. If None,
        uses all dimensions returned by the classifier.
    config:
        Thresholds for verdicts.

    Returns
    -------
    DimensionReport
    """
    if config is None:
        config = StabilityConfig()

    metrics: list[MetricResult] = []
    verdicts: list[Verdict] = []
    item_issues: list[ItemIssue] = []

    # Classify base items
    base_labels: dict[str, dict[str, str]] = {}
    for item_id, text in base_items.items():
        base_labels[item_id] = classifier(text)

    if label_dimensions is None and base_labels:
        label_dimensions = list(next(iter(base_labels.values())).keys())

    # --- Stability (paraphrases) ---
    if paraphrases and label_dimensions:
        para_by_item: dict[str, list[ParaphraseVariant]] = defaultdict(list)
        for p in paraphrases:
            para_by_item[p.item_id].append(p)

        per_dim_matches: dict[str, list[float]] = {d: [] for d in label_dimensions}
        all_jaccards: list[float] = []

        for item_id, variants in para_by_item.items():
            if item_id not in base_labels:
                continue
            base = base_labels[item_id]
            for variant in variants:
                variant_labels = classifier(variant.text)
                # Per-dimension exact match
                changed_dims = []
                for dim in label_dimensions:
                    base_val = base.get(dim, "").strip().lower()
                    var_val = variant_labels.get(dim, "").strip().lower()
                    match = base_val == var_val
                    per_dim_matches[dim].append(1.0 if match else 0.0)
                    if not match:
                        changed_dims.append(f"{dim}: {base.get(dim)}→{variant_labels.get(dim)}")

                if changed_dims:
                    item_issues.append(ItemIssue(
                        item_id=item_id,
                        dimension="stability",
                        severity="warning",
                        message=f"Paraphrase '{variant.variant_id}' changed: {', '.join(changed_dims)}",
                    ))

                # Set-based Jaccard over all label values
                base_set = {f"{k}:{v}" for k, v in base.items()}
                var_set = {f"{k}:{v}" for k, v in variant_labels.items()}
                all_jaccards.append(jaccard_similarity(base_set, var_set))

        total_comparisons = sum(len(v) for v in per_dim_matches.values())
        if total_comparisons > 0:
            # Per-dimension stability
            for dim in label_dimensions:
                vals = per_dim_matches[dim]
                if vals:
                    agreement = sum(vals) / len(vals)
                    metrics.append(MetricResult(
                        dimension="stability",
                        metric_name=f"stability_{dim}",
                        value=round(agreement, 4),
                        interpretation=f"{dim} agreement across paraphrases",
                    ))

            # Overall stability (mean across dimensions)
            all_match_values = [v for vals in per_dim_matches.values() for v in vals]
            overall_stability = sum(all_match_values) / len(all_match_values) if all_match_values else 0.0
            metrics.append(MetricResult(
                dimension="stability",
                metric_name="stability",
                value=round(overall_stability, 4),
                interpretation="overall paraphrase stability",
            ))

            # Mean Jaccard
            mean_jac = sum(all_jaccards) / len(all_jaccards) if all_jaccards else 0.0
            metrics.append(MetricResult(
                dimension="stability",
                metric_name="stability_jaccard",
                value=round(mean_jac, 4),
            ))

            # Bootstrap CI for overall stability
            point, ci_lower, ci_upper = bootstrap_ci(
                all_match_values,
                iterations=config.bootstrap.iterations,
                confidence=config.bootstrap.confidence,
                seed=config.bootstrap.seed,
            )
            metrics.append(MetricResult(
                dimension="stability",
                metric_name="stability_ci_lower",
                value=ci_lower,
            ))
            metrics.append(MetricResult(
                dimension="stability",
                metric_name="stability_ci_upper",
                value=ci_upper,
            ))

            for t in config.thresholds:
                if t.metric == "stability":
                    verdicts.append(compute_verdict_from_threshold(overall_stability, t))

    # --- Sensitivity (perturbations) ---
    if perturbations and label_dimensions:
        pert_by_item: dict[str, list[PerturbationVariant]] = defaultdict(list)
        for p in perturbations:
            pert_by_item[p.item_id].append(p)

        change_detected: list[float] = []
        direction_correct: list[float] = []
        noop_false_changes: list[float] = []

        for item_id, variants in pert_by_item.items():
            if item_id not in base_labels:
                continue
            base = base_labels[item_id]

            for variant in variants:
                var_labels = classifier(variant.text)
                ed = variant.expected_direction

                # Check which dimensions changed
                any_changed = False
                expected_change_detected = False
                direction_ok: bool | None = None

                for dim in label_dimensions:
                    base_val = base.get(dim, "").strip().lower()
                    var_val = var_labels.get(dim, "").strip().lower()
                    changed = base_val != var_val

                    if changed:
                        any_changed = True

                    if ed.changes_expected.get(dim, False) and changed:
                        expected_change_detected = True
                        expected_val = ed.expected_values.get(dim)
                        if expected_val is not None:
                            direction_ok = var_val == expected_val.strip().lower()
                        else:
                            direction_ok = True

                if ed.expects_any_change():
                    change_detected.append(1.0 if expected_change_detected else 0.0)
                    if not expected_change_detected:
                        item_issues.append(ItemIssue(
                            item_id=item_id,
                            dimension="stability",
                            severity="error",
                            message=f"Perturbation '{variant.variant_id}' ({variant.perturbation_type}): expected change not detected",
                        ))
                    if expected_change_detected and direction_ok is not None:
                        direction_correct.append(1.0 if direction_ok else 0.0)
                        if not direction_ok:
                            item_issues.append(ItemIssue(
                                item_id=item_id,
                                dimension="stability",
                                severity="warning",
                                message=f"Perturbation '{variant.variant_id}': change detected but wrong direction",
                            ))
                else:
                    # Noop: any change is a false positive
                    noop_false_changes.append(1.0 if any_changed else 0.0)
                    if any_changed:
                        item_issues.append(ItemIssue(
                            item_id=item_id,
                            dimension="stability",
                            severity="error",
                            message=f"Perturbation '{variant.variant_id}' (noop): false change detected",
                        ))

        # Aggregate sensitivity metrics
        if change_detected:
            cdr = sum(change_detected) / len(change_detected)
            metrics.append(MetricResult(
                dimension="stability",
                metric_name="change_detection",
                value=round(cdr, 4),
                interpretation="fraction of expected changes detected",
            ))
            for t in config.thresholds:
                if t.metric == "change_detection":
                    verdicts.append(compute_verdict_from_threshold(cdr, t))

        if direction_correct:
            da = sum(direction_correct) / len(direction_correct)
            metrics.append(MetricResult(
                dimension="stability",
                metric_name="direction_accuracy",
                value=round(da, 4),
                interpretation="fraction of detected changes in correct direction",
            ))
            for t in config.thresholds:
                if t.metric == "direction_accuracy":
                    verdicts.append(compute_verdict_from_threshold(da, t))

        if noop_false_changes:
            fcr = sum(noop_false_changes) / len(noop_false_changes)
            metrics.append(MetricResult(
                dimension="stability",
                metric_name="false_change_rate",
                value=round(fcr, 4),
                interpretation="false change rate on noop perturbations",
            ))
            # False change rate: lower is better, so invert the threshold logic
            if fcr <= config.false_change_max:
                verdicts.append(Verdict.PASS)
            else:
                verdicts.append(Verdict.FAIL)

    overall = aggregate_verdicts(verdicts) if verdicts else Verdict.SKIPPED

    return DimensionReport(
        dimension="stability",
        verdict=overall,
        metrics=metrics,
        item_issues=item_issues,
    )
