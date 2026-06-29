"""Rule engine: registry, decorator, and evaluation.

Users define rules as decorated functions that accept a single item
(a dict or any object representing one LLM output) and return a list
of RuleResult. Batch rules accept the full list of items.

Example usage:

    from llm_classification_validator.consistency import rule, RuleRegistry

    registry = RuleRegistry()

    @registry.rule("S-001", "Label is non-empty", severity="error")
    def label_present(item: dict) -> list[RuleResult]:
        passed = bool(item.get("label"))
        return [RuleResult(
            rule_id="S-001",
            rule_name="Label is non-empty",
            category="structural",
            severity="error",
            passed=passed,
            item_id=item.get("id"),
            message="OK" if passed else "Label is missing",
        )]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from llm_classification_validator.models import RuleResult


# Type aliases
PerItemRuleFn = Callable[[Any], list[RuleResult]]
BatchRuleFn = Callable[[list[Any]], list[RuleResult]]


@dataclass
class Rule:
    """Metadata and callable for a registered rule."""

    rule_id: str
    name: str
    category: str
    severity: str
    is_batch: bool
    fn: PerItemRuleFn | BatchRuleFn


class RuleRegistry:
    """Registry for validation rules.

    Rules are registered via the ``rule`` decorator method. They can be
    per-item (applied to each output independently) or batch (applied
    to the entire list at once for cross-item checks).
    """

    def __init__(self) -> None:
        self._per_item_rules: list[Rule] = []
        self._batch_rules: list[Rule] = []

    def rule(
        self,
        rule_id: str,
        name: str,
        category: str = "structural",
        severity: str = "error",
        batch: bool = False,
    ) -> Callable[[Any], Any]:
        """Decorator to register a validation rule.

        Parameters
        ----------
        rule_id:
            Unique identifier for the rule (e.g. "S-001").
        name:
            Human-readable rule name.
        category:
            Rule category (e.g. "structural", "semantic", "cross_item").
        severity:
            "error", "warning", or "info".
        batch:
            If True, the function receives the full list of items.
            If False (default), it receives one item at a time.
        """

        def decorator(func: Any) -> Any:
            r = Rule(
                rule_id=rule_id,
                name=name,
                category=category,
                severity=severity,
                is_batch=batch,
                fn=func,
            )
            if batch:
                self._batch_rules.append(r)
            else:
                self._per_item_rules.append(r)
            return func

        return decorator

    def run_all(
        self,
        items: list[Any],
        category: str | None = None,
    ) -> list[RuleResult]:
        """Run all registered rules against a list of items.

        Parameters
        ----------
        items:
            The LLM outputs to validate.
        category:
            If provided, only rules in this category are run.

        Returns
        -------
        list[RuleResult]
        """
        results: list[RuleResult] = []

        # Per-item rules
        for rule_def in self._per_item_rules:
            if category and rule_def.category != category:
                continue
            for item in items:
                results.extend(rule_def.fn(item))

        # Batch rules
        for rule_def in self._batch_rules:
            if category and rule_def.category != category:
                continue
            results.extend(rule_def.fn(items))

        return results

    @property
    def rules(self) -> list[Rule]:
        """All registered rules."""
        return self._per_item_rules + self._batch_rules


# Convenience: a module-level default registry
_default_registry = RuleRegistry()


def rule(
    rule_id: str,
    name: str,
    category: str = "structural",
    severity: str = "error",
    batch: bool = False,
) -> Callable[[Any], Any]:
    """Register a rule on the default module-level registry."""
    return _default_registry.rule(
        rule_id=rule_id,
        name=name,
        category=category,
        severity=severity,
        batch=batch,
    )


def get_default_registry() -> RuleRegistry:
    """Return the default module-level registry."""
    return _default_registry
