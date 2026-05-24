"""src/agents/dsc_agent.py

Decision Support Control (DSC) agent.

DSC agents influence the probability of "aligned decisions" through the DSC
decision model (expectation_alignment/awareness/capability/situational/incentive).

Efficacy Method semantics (from JSON):
- "random draw to binomial eval": params are probability [0-1]
  - behavior: bernoulli_trial - sample probability, perform Bernoulli trial
  - Used to determine if the DSC successfully influences a decision
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base import BaseControlAgent
from ..config import get_config
from ..data.distributions import beta_pert, bernoulli_trial

cfg = get_config()


def _require(key: str):
    v = cfg.get(key, None)
    if v is None:
        raise ValueError(f"Missing required config key: {key}")
    return v


class DSCAgent(BaseControlAgent):
    """Decision Support Control agent."""

    def __init__(self, model: Any, unique_id: str, params: Dict[str, Any]):
        self.control_type = params.get("Control Type", params.get("Control_Type", "DSC"))

        # Parse efficacy method semantics (set by Loader)
        self._efficacy_method_type = params.get("_efficacy_method_type", "probability")
        self._efficacy_semantic_type = params.get("_efficacy_semantic_type", "probability")
        self._efficacy_behavior = params.get("_efficacy_behavior", "bernoulli_trial")
        self._efficacy_time_type = params.get("_efficacy_time_type", None)
        self._efficacy_method_raw = params.get("_efficacy_method_raw", "")

        # Store probability distribution params for Bernoulli trials
        self._prob_dist = self._parse_prob_dist_params(params)

        super().__init__(model, unique_id, params)

    def _parse_prob_dist_params(self, params: Dict[str, Any]) -> Dict[str, float]:
        """Parse params as probability distribution [0-1] for binomial eval."""
        # DSC uses "Efficacy Param 1..4" columns
        yaml_defaults = cfg.get("controls.defaults.dsc.defaults.prob_dist", {})
        return {
            "min": float(params.get("Efficacy Param 1", yaml_defaults.get("min", 0.0))),
            "mode": float(params.get("Efficacy Param 2", yaml_defaults.get("mode", 0.5))),
            "max": float(params.get("Efficacy Param 3", yaml_defaults.get("max", 1.0))),
            "confidence": float(params.get("Efficacy Param 4", yaml_defaults.get("confidence", 4))),
        }

    def sample_success_probability(self) -> float:
        """
        Sample success probability for this DSC's binomial eval.

        Returns probability [0-1] sampled from Beta-PERT distribution using JSON params.
        """
        d = self._prob_dist
        return float(beta_pert(d["min"], d["mode"], d["max"], d["confidence"], rng=self._rng()))

    def perform_binomial_eval(self) -> bool:
        """
        Perform a binomial evaluation for this DSC.

        Samples the probability from Beta-PERT distribution, then performs a Bernoulli trial.
        Returns True if the DSC successfully influences the decision (aligned), False otherwise.
        """
        p = self.sample_success_probability()
        return bernoulli_trial(p, rng=self._rng())

    def get_behavior_type(self) -> str:
        """Return the behavior type for this DSC based on its Efficacy Method."""
        return self._efficacy_behavior

    def get_semantic_type(self) -> str:
        """Return the semantic type for this DSC's parameters."""
        return self._efficacy_semantic_type

    def _calculate_remediation_duration(self) -> int:
        """Remediation effort duration in hours (config-driven)."""
        params = getattr(self, "params", {}) or {}
        for k in ("Remediation_Hours", "Remediation Hours", "remediation_hours"):
            if k in params and params[k] is not None:
                try:
                    return max(1, int(params[k]))
                except Exception:
                    pass

        # Single default for all controls (YAML)
        return max(1, int(_require("controls.defaults.remediation_hours")))

    def on_change_event(self, change_type: str) -> bool:
        """External change event hook (variance introduction handled elsewhere)."""
        if self.state == "normal":
            self._pending_change_type = change_type
            self.become_variant()
            return True
        return False
