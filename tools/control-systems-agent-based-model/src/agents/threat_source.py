"""src/agents/threat_source.py

Threat Source agent.

Behavior:
* ThreatSource governs the *arrival* of threat contacts.
* Each scheduled contact spawns a ThreatAgent instance (from a template) that attempts
  a contact immediately (next tick) and can then be used for downstream state
  (e.g., compromise edges / lateral movement).

Scenario spreadsheets express contact frequency on the "Threat Sources" sheet using:
  - Contact Frequency Dist Type
  - Param 1..4

The hospital_ransomware scenarios provide Beta-PERT parameters that represent an
expected number of contacts per month. We therefore:
  - Re-sample a contacts-per-month value at month boundaries
  - Convert it to an exponential inter-arrival rate within the month

All randomness uses model.random for reproducibility.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, List
import logging

from mesa import Agent

from ..config import get_config
from ..data.distributions import exponential, beta_pert

logger = logging.getLogger(__name__)
cfg = get_config()


def _require(path: str):
    v = cfg.get(path, None)
    if v is None:
        raise ValueError(f"Missing required config key: {path}")
    return v


class ThreatSourceAgent(Agent):
    _agent_type = "ThreatSource"

    def __init__(self, model: Any, unique_id: str, params: Dict[str, Any]):
        # Mesa 3.x: Agent(model), Mesa 2.x: Agent(unique_id, model)
        try:
            super().__init__(model)
            self.unique_id = unique_id
        except TypeError:
            super().__init__(unique_id, model)
        self.params = params or {}

        # Contact frequency behavior (from scenario params).
        # Expected columns: "Contact Frequency Dist Type" + "Param 1..4".
        self.freq_dist_type = str(self.params.get("Contact Frequency Dist Type") or "").strip().lower()
        self.freq_p1 = self.params.get("Param 1")
        self.freq_p2 = self.params.get("Param 2")
        self.freq_p3 = self.params.get("Param 3")
        self.freq_p4 = self.params.get("Param 4")

        if not self.freq_dist_type:
            # Fall back to a sane default if scenario omitted it.
            self.freq_dist_type = "beta pert"
            self.freq_dist_type = "beta pert"

        self._hours_per_month = float(_require("time.hours_per_month"))
        if self._hours_per_month <= 0:
            raise ValueError("time.hours_per_month must be > 0")

        # Month boundary tracking
        self._month_start_tick: int = int(getattr(self.model.schedule, "steps", 0))
        self._contacts_per_month: float = 0.0
        self._resample_contacts_per_month()

        # ThreatAgent template list (from JSON or YAML). Loader builds these in model_data.
        self.threat_templates: List[Dict[str, Any]] = self.params.get("Threat Templates", []) or []

        self.next_contact_tick: Optional[int] = None
        self._schedule_next_contact()

    def _rng(self):
        streams = getattr(self.model, "streams", None)
        if streams is not None:
            return streams.agent_rng("contacts", str(self.unique_id))
        r = getattr(self.model, "random", None)
        if r is None:
            raise ValueError("Model must provide model.random RNG")
        return r

    def _resample_contacts_per_month(self) -> None:
        """Re-sample contacts-per-month using scenario distribution parameters."""
        dist = (self.freq_dist_type or "").strip().lower()
        if "beta" in dist and "pert" in dist:
            try:
                mn = float(self.freq_p1)
                md = float(self.freq_p2)
                mx = float(self.freq_p3)
                lam = float(self.freq_p4)
            except Exception:
                # Fallback: minimal 1 contact/month
                mn, md, mx, lam = 1.0, 1.0, 1.0, 4.0
            self._contacts_per_month = max(0.0, float(beta_pert(mn, md, mx, lam, rng=self._rng())))
        else:
            # Unknown dist types: treat Param 2 as a mean contacts/month if present
            try:
                self._contacts_per_month = max(0.0, float(self.freq_p2))
            except Exception:
                self._contacts_per_month = 0.0

        self._month_start_tick = int(getattr(self.model.schedule, "steps", 0))

    def _schedule_next_contact(self) -> None:
        """Schedule next contact within the current month, resampling at month boundaries."""
        tick = int(getattr(self.model.schedule, "steps", 0))

        # Month boundary: if we've advanced >= one month, resample
        if tick - self._month_start_tick >= int(self._hours_per_month):
            self._resample_contacts_per_month()

        # No contacts this month: schedule a check at the next month boundary
        # (step() will resample and skip if still zero)
        if self._contacts_per_month <= 0.0:
            next_boundary = self._month_start_tick + int(self._hours_per_month)
            # Only schedule if in the future; avoid stalling on the current tick
            if next_boundary <= tick:
                next_boundary = tick + int(self._hours_per_month)
                self._month_start_tick = tick
            self.next_contact_tick = next_boundary
            return

        # Exponential inter-arrival (Poisson process).
        # Use contacts_per_month to derive the rate, but allow the interval
        # to extend past the current month.  Monthly resampling still occurs
        # because _schedule_next_contact detects month boundaries when called
        # after the next spawn.
        mean = float(self._hours_per_month) / float(self._contacts_per_month)
        dt = float(exponential(mean, rng=self._rng()))
        self.next_contact_tick = tick + max(1, int(dt))

    def step(self):
        tick = int(getattr(self.model.schedule, "steps", 0))
        if self.next_contact_tick is None or tick < int(self.next_contact_tick):
            return

        # If contacts_per_month is zero, this was a month-boundary check.
        # Resample and reschedule without spawning.
        if self._contacts_per_month <= 0.0:
            self._schedule_next_contact()
            return

        # Spawn a threat agent using the model's factory (if present)
        if hasattr(self.model, "spawn_threat_agent"):
            try:
                self.model.spawn_threat_agent(threat_source=self)
            except Exception:
                logger.exception("Failed to spawn threat agent from %s", self.unique_id)

        self._schedule_next_contact()
