"""Analysis tools: metrics collection, narrative tracing, validation."""

from .metrics import MetricsState, create_data_collector
from .narrative import NarrativeCollector, LossEventNarrative, VarianceNarrative, BreachNarrative

__all__ = [
    "MetricsState",
    "create_data_collector",
    "NarrativeCollector",
    "LossEventNarrative",
    "VarianceNarrative",
    "BreachNarrative",
]
