"""
Base class for vector-level TEF estimation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from tef_estimator.data.common import PERTRange

if TYPE_CHECKING:
    from tef_estimator.data.scenarios.base import ScenarioDefinition
    from tef_estimator.profile import OrganizationProfile
    from tef_estimator.trace import CalculationTrace


@dataclass
class VectorEstimate:
    """Output of a single-vector TEF estimation.

    positioned_median is the lognormal median (exp(μ)) of the output
    distribution — equivalently, the PERT mode before credibility
    blending, or the Bühlmann blended estimate after.
    """
    vector_name: str
    floor: float
    ceiling: float
    positioned_low: float
    positioned_median: float
    positioned_high: float
    primary_drivers: list[str]
    data_sources: list[str]
    notes: list[str] = field(default_factory=list)
    trace: CalculationTrace | None = None

    # Bühlmann credibility blending (None if no telemetry provided)
    prior_median: float | None = None
    observed_frequency: float | None = None
    credibility_z: float | None = None

    @property
    def telemetry_key(self) -> str:
        return self.vector_name.lower().replace(" ", "_")

    @property
    def positioned_range(self) -> PERTRange:
        return PERTRange(self.positioned_low, self.positioned_median, self.positioned_high)

    def enforce_bounds(self) -> None:
        """Ensure positioned estimate respects the observed floor."""
        self.positioned_low = max(self.positioned_low, self.floor)
        self.positioned_median = max(self.positioned_median, self.floor)
        self.positioned_high = max(self.positioned_high, self.floor)


class VectorEngine(Protocol):
    """Protocol for vector estimation engines."""

    def estimate(
        self,
        profile: OrganizationProfile,
        base_rate: PERTRange,
        scenario: ScenarioDefinition,
    ) -> VectorEstimate:
        ...
