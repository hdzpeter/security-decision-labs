"""Consistency report generation from rule results."""

from __future__ import annotations

from typing import Any

from llm_classification_validator.config import ConsistencyConfig
from llm_classification_validator.consistency.rules import RuleRegistry
from llm_classification_validator.models import DimensionReport, ItemIssue, MetricResult, RuleResult, Verdict


def run_consistency_check(
    items: list[Any],
    registry: RuleRegistry,
    config: ConsistencyConfig | None = None,
) -> DimensionReport:
    """Run all rules in a registry and produce a dimension report.

    Parameters
    ----------
    items:
        The LLM outputs to validate.
    registry:
        The rule registry containing the rules to run.
    config:
        Configuration controlling verdict logic.

    Returns
    -------
    DimensionReport
    """
    if config is None:
        config = ConsistencyConfig()

    results = registry.run_all(items)

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    errors = [r for r in results if not r.passed and r.severity == "error"]
    warnings = [r for r in results if not r.passed and r.severity == "warning"]

    pass_rate = passed / total if total > 0 else 1.0

    metrics = [
        MetricResult(
            dimension="consistency",
            metric_name="pass_rate",
            value=pass_rate,
            interpretation=f"{passed}/{total} rules passed",
        ),
        MetricResult(
            dimension="consistency",
            metric_name="error_count",
            value=float(len(errors)),
            interpretation=f"{len(errors)} errors found",
        ),
        MetricResult(
            dimension="consistency",
            metric_name="warning_count",
            value=float(len(warnings)),
            interpretation=f"{len(warnings)} warnings found",
        ),
    ]

    # Verdict
    if config.fail_on_error and errors:
        verdict = Verdict.FAIL
    elif config.fail_on_warning and warnings:
        verdict = Verdict.MARGINAL
    elif failed > 0:
        verdict = Verdict.MARGINAL
    else:
        verdict = Verdict.PASS

    item_issues = []
    for r in results:
        if not r.passed and r.item_id:
            item_issues.append(ItemIssue(
                item_id=r.item_id,
                dimension="consistency",
                severity=r.severity,
                message=f"[{r.rule_id}] {r.message}",
            ))

    return DimensionReport(
        dimension="consistency",
        verdict=verdict,
        metrics=metrics,
        item_issues=item_issues,
        details={
            "total_rules": total,
            "passed": passed,
            "failed": failed,
            "errors": [r.message for r in errors],
            "warnings": [r.message for r in warnings],
        },
    )
