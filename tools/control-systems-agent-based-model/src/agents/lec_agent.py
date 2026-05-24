"""src/agents/lec_agent.py

Loss Event Control (LEC) agent.

Efficacy Method semantics (from JSON):
- "comparison to threat sophistication": params are efficacy [0-1] (resistance/avoidance/deterrence)
  - behavior: compare_sophistication - compare set-and-hold efficacy against threat sophistication
- "random draw, success/failure outcome": params are probability [0-1] (visibility/recognition)
  - behavior: bernoulli_trial - sample probability, perform Bernoulli trial
- "timing interval for detection sweep": params are detection time in hours (monitoring)
  - behavior: sample_time_interval - sample detection interval in hours
- "timing interval for loss termination": params are termination time in hours (event_termination)
  - behavior: sample_time_interval - sample termination time in hours
- "timing interval for recovery": params are recovery time in hours (resilience)
  - behavior: sample_time_interval - sample recovery time in hours
"""

from __future__ import annotations

from typing import Dict, Any, Optional

from ..config import get_config
from ..data.distributions import beta_pert, bernoulli_trial
from .base import BaseControlAgent

cfg = get_config()


def _require(key: str):
    v = cfg.get(key, None)
    if v is None:
        raise ValueError(f"Missing required config key: {key}")
    return v


class LECAgent(BaseControlAgent):
    """Loss Event Control agent."""

    def __init__(self, model, unique_id: str, params: Dict[str, Any]):
        # These are normalized in Loader now, but keep fallbacks.
        self.control_type = params.get("Control Type", params.get("Control_Type", "LEC"))

        # Prefer "Control Type" from JSON (the actual LEC function like event_termination,
        # monitoring, resilience) over "LEC_Type" which is the YAML default ("resistance").
        # The loader sets LEC_Type to the YAML default for ALL LECs, so it must be checked
        # last, otherwise all LECs would be classified as "resistance".
        lec_type = params.get("Control Type", None) or params.get("LEC_Type", None) or "resistance"
        self.lec_type = str(lec_type).strip().lower()

        self.actor_type = params.get("Actor_Type", params.get("Actor Type", "technology"))
        self.actor_type = str(self.actor_type).strip().lower()

        # Parse efficacy method semantics (set by Loader)
        self._efficacy_method_type = params.get("_efficacy_method_type", "efficacy")
        self._efficacy_semantic_type = params.get("_efficacy_semantic_type", "efficacy")
        self._efficacy_behavior = params.get("_efficacy_behavior", "compare_sophistication")
        self._efficacy_time_type = params.get("_efficacy_time_type", None)
        self._efficacy_method_raw = params.get("_efficacy_method_raw", "")

        # For time-based LECs, store time distribution params separately
        # These are NOT efficacy [0-1] but time in hours
        if self._efficacy_semantic_type == "time_hours":
            self._time_dist = self._parse_time_dist_params(params)

        # For probability-based LECs, store probability distribution params
        # These are [0-1] probabilities for Bernoulli trials
        if self._efficacy_semantic_type == "probability":
            self._prob_dist = self._parse_prob_dist_params(params)

        super().__init__(model, unique_id, params)

    def _parse_time_dist_params(self, params: Dict[str, Any]) -> Dict[str, float]:
        """Parse params as time distribution (hours), not efficacy [0-1]."""
        # Get YAML fallback defaults
        yaml_defaults = cfg.get("controls.defaults.lec.defaults.time_dist", {})
        return {
            "min": float(params.get("Param 1", params.get("Efficacy Param 1", yaml_defaults.get("min", 1)))),
            "mode": float(params.get("Param 2", params.get("Efficacy Param 2", yaml_defaults.get("mode", 24)))),
            "max": float(params.get("Param 3", params.get("Efficacy Param 3", yaml_defaults.get("max", 168)))),
            "confidence": float(params.get("Param 4", params.get("Efficacy Param 4", yaml_defaults.get("confidence", 4)))),
        }

    def _parse_prob_dist_params(self, params: Dict[str, Any]) -> Dict[str, float]:
        """Parse params as probability distribution [0-1]."""
        # Get YAML fallback defaults
        yaml_defaults = cfg.get("controls.defaults.lec.defaults.prob_dist", {})
        return {
            "min": float(params.get("Param 1", params.get("Efficacy Param 1", yaml_defaults.get("min", 0.0)))),
            "mode": float(params.get("Param 2", params.get("Efficacy Param 2", yaml_defaults.get("mode", 0.5)))),
            "max": float(params.get("Param 3", params.get("Efficacy Param 3", yaml_defaults.get("max", 1.0)))),
            "confidence": float(params.get("Param 4", params.get("Efficacy Param 4", yaml_defaults.get("confidence", 4)))),
        }

    def sample_detection_time_hours(self) -> Optional[float]:
        """
        Sample detection time for monitoring LECs (detection_time method type).

        Returns detection time in hours, or None if not a detection-time LEC.
        """
        if self._efficacy_time_type != "detection_time" or not hasattr(self, "_time_dist"):
            return None

        d = self._time_dist
        return float(beta_pert(d["min"], d["mode"], d["max"], d["confidence"], rng=self._rng()))

    def sample_termination_time_hours(self) -> Optional[float]:
        """
        Sample termination time for event_termination LECs (termination_time method type).

        Returns termination time in hours, or None if not a termination-time LEC.
        """
        if self._efficacy_time_type != "termination_time" or not hasattr(self, "_time_dist"):
            return None

        d = self._time_dist
        return float(beta_pert(d["min"], d["mode"], d["max"], d["confidence"], rng=self._rng()))

    def sample_recovery_time_hours(self) -> Optional[float]:
        """
        Sample recovery time for resilience LECs (recovery_time method type).

        Returns recovery time in hours, or None if not a recovery-time LEC.
        """
        if self._efficacy_time_type != "recovery_time" or not hasattr(self, "_time_dist"):
            return None

        d = self._time_dist
        return float(beta_pert(d["min"], d["mode"], d["max"], d["confidence"], rng=self._rng()))

    def sample_success_probability(self) -> Optional[float]:
        """
        Sample success probability for visibility/recognition LECs (probability method type).

        Returns probability [0-1], or None if not a probability-based LEC.
        """
        if self._efficacy_semantic_type != "probability" or not hasattr(self, "_prob_dist"):
            return None

        d = self._prob_dist
        return float(beta_pert(d["min"], d["mode"], d["max"], d["confidence"], rng=self._rng()))

    def perform_bernoulli_trial(self) -> Optional[bool]:
        """
        Perform a Bernoulli trial for probability-based LECs.

        Samples the probability from Beta-PERT distribution, then performs a Bernoulli trial.
        Returns True (success) or False (failure), or None if not a probability-based LEC.
        """
        if self._efficacy_behavior != "bernoulli_trial" or not hasattr(self, "_prob_dist"):
            return None

        p = self.sample_success_probability()
        if p is None:
            return None
        return bernoulli_trial(p, rng=self._rng())

    def get_behavior_type(self) -> str:
        """Return the behavior type for this LEC based on its Efficacy Method."""
        return self._efficacy_behavior

    def get_semantic_type(self) -> str:
        """Return the semantic type for this LEC's parameters."""
        return self._efficacy_semantic_type

    def _calculate_remediation_duration(self) -> int:
        # Prefer sheet param, else YAML default
        return int(
            self.params.get("Remediation_Hours", _require("controls.defaults.remediation_hours"))
            or _require("controls.defaults.remediation_hours")
        )

    def on_change_event(self, change_type: str) -> bool:
        if self.state == "normal":
            self._pending_change_type = change_type
            self.become_variant()
            return True
        return False
