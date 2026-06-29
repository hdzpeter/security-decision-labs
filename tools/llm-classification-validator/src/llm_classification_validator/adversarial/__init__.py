"""Dimension 4: Adversarial edge case testing.

Tests whether an LLM can discriminate between similar-but-different inputs
(minimal pairs) and handle genuinely ambiguous cases within acceptable bounds.
"""

from llm_classification_validator.adversarial.scorer import (
    combined_score,
    pass_rate,
    score_discrimination,
)
from llm_classification_validator.adversarial.pairs import (
    MinimalPair,
    AmbiguityCase,
    run_adversarial_analysis,
)

__all__ = [
    "AmbiguityCase",
    "MinimalPair",
    "combined_score",
    "pass_rate",
    "run_adversarial_analysis",
    "score_discrimination",
]
