"""Dimension 5: Stability and sensitivity.

Tests whether the LLM produces consistent outputs under:
- Paraphrase: semantically equivalent rewrites should yield the same label.
- Perturbation: meaningful changes should yield predictable label shifts.
"""

from llm_classification_validator.stability.paraphrase import (
    PARAPHRASE_STRATEGIES,
    ParaphraseVariant,
)
from llm_classification_validator.stability.perturbation import (
    ExpectedDirection,
    PerturbationVariant,
)
from llm_classification_validator.stability.analysis import run_stability_analysis

__all__ = [
    "ExpectedDirection",
    "PARAPHRASE_STRATEGIES",
    "ParaphraseVariant",
    "PerturbationVariant",
    "run_stability_analysis",
]
