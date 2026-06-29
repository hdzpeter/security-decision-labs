"""Tests for Dimension 2: Consistency (rule engine)."""

import pytest

from llm_classification_validator.consistency.rules import RuleRegistry
from llm_classification_validator.consistency.report import run_consistency_check
from llm_classification_validator.config import ConsistencyConfig
from llm_classification_validator.models import RuleResult


class TestRuleRegistry:
    def test_register_and_run_per_item(self):
        registry = RuleRegistry()

        @registry.rule("R-001", "Label present", category="structural", severity="error")
        def label_present(item: dict) -> list[RuleResult]:
            passed = bool(item.get("label"))
            return [RuleResult(
                rule_id="R-001",
                rule_name="Label present",
                category="structural",
                severity="error",
                passed=passed,
                item_id=item.get("id"),
                message="OK" if passed else "Label missing",
            )]

        items = [
            {"id": "1", "label": "A"},
            {"id": "2", "label": ""},
            {"id": "3", "label": "C"},
        ]
        results = registry.run_all(items)
        assert len(results) == 3
        assert results[0].passed is True
        assert results[1].passed is False
        assert results[2].passed is True

    def test_register_batch_rule(self):
        registry = RuleRegistry()

        @registry.rule("B-001", "No duplicates", category="cross_item", severity="error", batch=True)
        def no_duplicate_ids(items: list[dict]) -> list[RuleResult]:
            ids = [i.get("id") for i in items]
            unique = len(ids) == len(set(ids))
            return [RuleResult(
                rule_id="B-001",
                rule_name="No duplicates",
                category="cross_item",
                severity="error",
                passed=unique,
                item_id=None,
                message="OK" if unique else "Duplicate IDs found",
            )]

        items = [{"id": "1"}, {"id": "2"}, {"id": "1"}]
        results = registry.run_all(items)
        assert len(results) == 1
        assert results[0].passed is False

    def test_filter_by_category(self):
        registry = RuleRegistry()

        @registry.rule("S-001", "Structural check", category="structural")
        def structural(item):
            return [RuleResult("S-001", "Structural check", "structural", "error",
                               True, None, "OK")]

        @registry.rule("M-001", "Semantic check", category="semantic")
        def semantic(item):
            return [RuleResult("M-001", "Semantic check", "semantic", "warning",
                               True, None, "OK")]

        results = registry.run_all([{"x": 1}], category="structural")
        assert len(results) == 1
        assert results[0].rule_id == "S-001"

    def test_rules_property(self):
        registry = RuleRegistry()

        @registry.rule("R-001", "Test", batch=False)
        def r1(item):
            return []

        @registry.rule("B-001", "Batch", batch=True)
        def b1(items):
            return []

        assert len(registry.rules) == 2


class TestConsistencyReport:
    def test_all_pass(self):
        registry = RuleRegistry()

        @registry.rule("R-001", "Always passes")
        def always_pass(item):
            return [RuleResult("R-001", "Always passes", "structural", "error",
                               True, None, "OK")]

        report = run_consistency_check([{"a": 1}, {"a": 2}], registry)
        assert report.verdict.value == "PASS"
        pass_rate = next(m for m in report.metrics if m.metric_name == "pass_rate")
        assert pass_rate.value == pytest.approx(1.0)

    def test_error_causes_fail(self):
        registry = RuleRegistry()

        @registry.rule("R-001", "Always fails", severity="error")
        def always_fail(item):
            return [RuleResult("R-001", "Always fails", "structural", "error",
                               False, None, "bad")]

        config = ConsistencyConfig(fail_on_error=True)
        report = run_consistency_check([{"a": 1}], registry, config=config)
        assert report.verdict.value == "FAIL"

    def test_warning_causes_marginal(self):
        registry = RuleRegistry()

        @registry.rule("W-001", "Warns", severity="warning")
        def warns(item):
            return [RuleResult("W-001", "Warns", "structural", "warning",
                               False, None, "minor issue")]

        config = ConsistencyConfig(fail_on_error=True, fail_on_warning=False)
        report = run_consistency_check([{"a": 1}], registry, config=config)
        # No errors, but a failure exists -> MARGINAL
        assert report.verdict.value == "MARGINAL"
