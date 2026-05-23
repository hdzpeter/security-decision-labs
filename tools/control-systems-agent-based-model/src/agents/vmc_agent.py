"""src/agents/vmc_agent.py

Variance Management Control (VMC) agent.

Efficacy Method semantics (from JSON):
- "time interval for variance detection sweep": params are detection interval in hours
  - behavior: sample_time_interval - sample detection sweep interval
- "variance probability adjustment factor": params are probability adjustment [0-1]
  - behavior: bernoulli_trial - use as factor for variance detection probability
- "variance probability adjustment": same as above (alternate spelling)
- "time interval for variance correction": params are remediation time in hours
  - behavior: sample_time_interval - sample remediation duration
"""

from __future__ import annotations

from typing import Dict, Any, Optional

from ..config import get_config
from ..data.distributions import beta_pert, bernoulli_trial, uniform as uniform_sample
from .base import BaseControlAgent

cfg = get_config()


def _require(key: str):
    v = cfg.get(key, None)
    if v is None:
        raise ValueError(f"Missing required config key: {key}")
    return v


class VMCAgent(BaseControlAgent):
    """Variance Management Control agent."""

    def __init__(self, model, unique_id: str, params: Dict[str, Any]):
        self.control_type = params.get("Control_Type", params.get("Control Type", "VMC"))

        # Parse efficacy method semantics (set by Loader)
        self._efficacy_method_type = params.get("_efficacy_method_type", "efficacy")
        self._efficacy_semantic_type = params.get("_efficacy_semantic_type", "efficacy")
        self._efficacy_behavior = params.get("_efficacy_behavior", "compare_sophistication")
        self._efficacy_time_type = params.get("_efficacy_time_type", None)
        self._efficacy_method_raw = params.get("_efficacy_method_raw", "")

        # For time-based VMCs, store time distribution params separately
        # These should NOT be interpreted as efficacy [0-1] but as hours
        if self._efficacy_semantic_type == "time_hours":
            self._time_dist = self._parse_time_dist_params(params)

        # For probability-based VMCs (variance probability adjustment),
        # store probability distribution params for Bernoulli trials
        if self._efficacy_semantic_type == "probability":
            self._prob_dist = self._parse_prob_dist_params(params)

        super().__init__(model, unique_id, params)

    def _parse_time_dist_params(self, params: Dict[str, Any]) -> Dict[str, float]:
        """Parse params as time distribution (hours), not efficacy [0-1]."""
        # Get YAML fallback defaults (no hardcoded values in code)
        yaml_defaults = cfg.get("controls.defaults.vmc.defaults.time_dist", {})
        return {
            "min": float(params.get("Param 1", params.get("Efficacy Param 1", yaml_defaults.get("min", 24)))),
            "mode": float(params.get("Param 2", params.get("Efficacy Param 2", yaml_defaults.get("mode", 168)))),
            "max": float(params.get("Param 3", params.get("Efficacy Param 3", yaml_defaults.get("max", 720)))),
            "confidence": float(params.get("Param 4", params.get("Efficacy Param 4", yaml_defaults.get("confidence", 4)))),
        }

    def _parse_prob_dist_params(self, params: Dict[str, Any]) -> Dict[str, float]:
        """Parse params as probability distribution [0-1] for variance adjustment."""
        # For probability VMCs, params are [0-1] factors
        return {
            "min": float(params.get("Param 1", params.get("Efficacy Param 1", 0.0))),
            "mode": float(params.get("Param 2", params.get("Efficacy Param 2", 0.5))),
            "max": float(params.get("Param 3", params.get("Efficacy Param 3", 1.0))),
            "confidence": float(params.get("Param 4", params.get("Efficacy Param 4", 4))),
        }

    def sample_detection_interval_hours(self) -> float:
        """
        Sample detection interval for monitoring VMCs (detection_time method type).

        Returns hours between detection sweeps, sampled from Beta-PERT distribution
        using JSON params. Falls back to global YAML default if not a detection VMC.
        """
        if self._efficacy_time_type != "detection_time" or not hasattr(self, "_time_dist"):
            return float(_require("time.vmc_monitoring_interval_hours"))

        d = self._time_dist
        return float(beta_pert(d["min"], d["mode"], d["max"], d["confidence"], rng=self._rng()))

    def sample_remediation_time_hours(self) -> float:
        """
        Sample remediation time for remediation VMCs (remediation_time method type).

        Returns remediation duration in hours, sampled from Beta-PERT distribution
        using JSON params. Falls back to YAML default if not a remediation VMC.
        """
        if self._efficacy_time_type != "remediation_time" or not hasattr(self, "_time_dist"):
            return float(_require("controls.defaults.remediation_hours"))

        d = self._time_dist
        return float(beta_pert(d["min"], d["mode"], d["max"], d["confidence"], rng=self._rng()))

    def sample_variance_probability_factor(self) -> Optional[float]:
        """
        Sample variance probability adjustment factor for probability VMCs.

        Returns a factor [0-1] sampled from Beta-PERT distribution, or None if
        this is not a probability-based VMC.
        """
        if self._efficacy_semantic_type != "probability" or not hasattr(self, "_prob_dist"):
            return None

        d = self._prob_dist
        return float(beta_pert(d["min"], d["mode"], d["max"], d["confidence"], rng=self._rng()))

    def perform_detection_trial(self, base_probability: float = 1.0) -> bool:
        """
        Perform a variance detection trial for probability-based VMCs.

        For VMCs with "variance probability adjustment factor" method, samples
        the factor and uses it to scale the base detection probability.

        Args:
            base_probability: The base detection probability before adjustment

        Returns:
            True if detection succeeds, False otherwise
        """
        if self._efficacy_behavior == "bernoulli_trial" and hasattr(self, "_prob_dist"):
            # Sample the adjustment factor
            factor = self.sample_variance_probability_factor()
            if factor is not None:
                adjusted_prob = min(1.0, max(0.0, base_probability * factor))
                return bernoulli_trial(adjusted_prob, rng=self._rng())

        # For non-probability VMCs, use base probability directly
        return bernoulli_trial(base_probability, rng=self._rng())

    def sample_change_freq_hours(self) -> float:
        """Sample from this VMC's change frequency distribution (hours).

        Used to degrade time-based VMC intervals when variant: the change
        frequency sample is added to the base interval, making sweeps or
        remediations less frequent while the VMC is degraded.
        """
        cf = self.change_freq_dist_params
        dist = str(cf["dist_type"]).strip().lower()
        if dist == "uniform":
            return float(uniform_sample(cf["param1"], cf["param2"], rng=self._rng()))
        return float(beta_pert(cf["param1"], cf["param2"], cf["param3"], cf["param4"], rng=self._rng()))

    def _calculate_remediation_duration(self) -> int:
        """
        Calculate remediation duration for this VMC.

        For remediation_time VMCs, samples from the time distribution.
        When variant, adds a change frequency sample to the base duration
        (degraded VMC takes longer to remediate controls).
        Otherwise falls back to explicit Remediation_Hours param or YAML default.
        """
        # First check if this is a remediation-time VMC
        if self._efficacy_time_type == "remediation_time" and hasattr(self, "_time_dist"):
            base = max(1, int(self.sample_remediation_time_hours()))
            if str(getattr(self, "state", "normal")).lower() == "variant":
                base += max(0, int(self.sample_change_freq_hours()))
            return base

        # Fall back to explicit param or YAML default
        return int(
            self.params.get("Remediation_Hours", _require("controls.defaults.remediation_hours"))
            or _require("controls.defaults.remediation_hours")
        )

    def get_behavior_type(self) -> str:
        """Return the behavior type for this VMC based on its Efficacy Method."""
        return self._efficacy_behavior

    def get_semantic_type(self) -> str:
        """Return the semantic type for this VMC's parameters."""
        return self._efficacy_semantic_type

    def _calculate_variant_efficacy(self) -> float:
        """Calculate variant efficacy, fixing inverted semantics for time-based VMCs.

        For time-based VMCs (detection_time, remediation_time), the base class
        formula Uniform(0, IntEff) is inverted: lower values mean *better*
        performance (shorter intervals), so the base formula accidentally
        improves the VMC when variant. Instead, add a change frequency sample
        to IntEff so the variant value is *larger* (longer interval = worse).

        For probability-based and other VMCs, the base class formula is correct
        (lower values = worse detection probability).
        """
        if self._efficacy_semantic_type == "time_hours":
            return float(self.intended_efficacy) + abs(self.sample_change_freq_hours())
        return super()._calculate_variant_efficacy()

    def on_change_event(self, change_type: str) -> bool:
        if self.state == "normal":
            self._pending_change_type = change_type
            self.become_variant()
            return True
        return False
