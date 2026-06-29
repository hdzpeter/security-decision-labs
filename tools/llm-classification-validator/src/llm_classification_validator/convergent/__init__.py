"""Dimension 3: Convergent validity.

Compares LLM outputs against an independently derived reference
(e.g., a transitive mapping through a third framework) using
set-based (Jaccard) and categorical (kappa) agreement metrics.
"""

from llm_classification_validator.convergent.jaccard import (
    jaccard_distance,
    jaccard_similarity,
    mean_jaccard,
)
from llm_classification_validator.convergent.analysis import run_convergent_analysis

__all__ = [
    "jaccard_distance",
    "jaccard_similarity",
    "mean_jaccard",
    "run_convergent_analysis",
]
