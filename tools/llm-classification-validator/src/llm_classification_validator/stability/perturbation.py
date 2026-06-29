"""Perturbation generation and data model.

Perturbations are meaningful modifications to inputs that should cause
predictable changes in the LLM's classification output. Unlike
paraphrases (which should not change the output), perturbations test
whether the LLM detects when the input semantics actually change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExpectedDirection:
    """What label change is expected from a perturbation.

    For each label dimension being tracked, indicates whether the
    perturbation is expected to cause a change, and optionally what
    the new value should be.
    """

    changes_expected: dict[str, bool] = field(default_factory=dict)
    expected_values: dict[str, str] = field(default_factory=dict)

    def expects_any_change(self) -> bool:
        """True if any dimension is expected to change."""
        return any(self.changes_expected.values())


@dataclass
class PerturbationVariant:
    """A meaningfully modified version of an input text."""

    item_id: str
    variant_id: str
    perturbation_type: str
    text: str
    expected_direction: ExpectedDirection
    metadata: dict[str, Any] = field(default_factory=dict)
