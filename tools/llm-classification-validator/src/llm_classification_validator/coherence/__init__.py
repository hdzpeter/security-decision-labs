"""Dimension 1: Inter-rater agreement (coherence).

Measures whether multiple raters (LLM runs, human experts, or a mix)
produce consistent classifications for the same items.
"""

from llm_classification_validator.coherence.kappa import (
    build_ratings_matrix,
    cohens_kappa,
    fleiss_kappa,
)
from llm_classification_validator.coherence.bootstrap import bootstrap_ci
from llm_classification_validator.coherence.analysis import run_coherence_analysis
from llm_classification_validator.coherence.sampling import (
    SamplePlan,
    check_sample_sufficiency,
    compute_sample_plan,
)

__all__ = [
    "SamplePlan",
    "build_ratings_matrix",
    "bootstrap_ci",
    "check_sample_sufficiency",
    "cohens_kappa",
    "compute_sample_plan",
    "fleiss_kappa",
    "run_coherence_analysis",
]
