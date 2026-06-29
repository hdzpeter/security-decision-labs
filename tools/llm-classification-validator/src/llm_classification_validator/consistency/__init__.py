"""Dimension 2: Rule-based consistency validation.

Provides a rule engine for defining and running deterministic validation
rules against LLM classification outputs.
"""

from llm_classification_validator.consistency.rules import (
    Rule,
    RuleRegistry,
    rule,
)
from llm_classification_validator.consistency.report import run_consistency_check

__all__ = [
    "Rule",
    "RuleRegistry",
    "rule",
    "run_consistency_check",
]
