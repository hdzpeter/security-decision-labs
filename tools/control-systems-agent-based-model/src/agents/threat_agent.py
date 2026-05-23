"""src/agents/threat_agent.py

Threat agent.

Responsibilities:
- Represents an instantiated threat actor created by ThreatSourceAgent.
- For threat agents spawned as contact-instances (IDs like TRT1__inst_N), the agent performs
  exactly ONE contact attempt at its scheduled tick and then removes itself from the schedule.
  ThreatSource governs contact arrivals.

For compatibility with earlier experimentation, "template" threat agents (not __inst_)
may still use a contact-frequency schedule (config-driven) and can make repeated attempts.

Lateral Movement:
- External threats initially target only external TAs (network_layer == "external").
- After breaching an external TA, the threat can move laterally to connected TAs.
- Lateral movement is sequential (one TA at a time per tick).
- Lateral movement is one-hop only (from breached external TA to connected TAs).
- Implicit TA-to-TA connectivity is configurable (default: all TAs connected).

All randomness uses model.random for reproducibility.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, Optional

from mesa import Agent

from ..config import get_config

logger = logging.getLogger(__name__)
cfg = get_config()


def _require(key: str):
    v = cfg.get(key, None)
    if v is None:
        raise ValueError(f"Missing required config key: {key}")
    return v


class ThreatAgent(Agent):
    _agent_type = "ThreatAgent"

    def __init__(self, model: Any, unique_id: str, params: Dict[str, Any]):
        # Mesa 3.x: Agent(model), Mesa 2.x: Agent(unique_id, model)
        try:
            super().__init__(model)
            self.unique_id = unique_id
        except TypeError:
            super().__init__(unique_id, model)

        self.params = params or {}

        # "Instance" agents are spawned per contact by ThreatSourceAgent.
        # Single-shot to avoid runaway contact volumes.
        self.single_shot: bool = ("__inst_" in str(unique_id))

        # Lateral movement state: track which TAs have been breached and pending lateral targets
        self._breached_tas: set = set()  # TAs this threat has successfully breached
        self._lateral_targets: list = []  # Queue of TAs to target via lateral movement
        self._lateral_movement_active: bool = False  # True after initial external breach

        # Origin: external/internal (config-driven default)
        origin_default = _require("excel_loader.defaults.threat_agent.origin")
        self.origin = str(self.params.get("Origin", self.params.get("origin", origin_default))).strip().lower()

        self.next_contact_tick: Optional[int] = None

        # Loss-related parameters from JSON (used by loss event processor)
        # Mean Event Velocity for Losses: records affected per hour during breach
        self.mean_velocity_hours: Optional[float] = None
        velocity_val = self.params.get("Mean_Velocity_Hours")
        if velocity_val is not None:
            self.mean_velocity_hours = float(velocity_val)

        # Loss Rate Exponent: controls loss magnitude scaling
        self.exp_loss_rate: Optional[float] = None
        exp_val = self.params.get("Exp_Loss_Rate")
        if exp_val is not None:
            self.exp_loss_rate = float(exp_val)

        if self.single_shot:
            # Attempt contact on the next tick after creation.
            self.next_contact_tick = int(getattr(self.model.schedule, "steps", 0)) + 1
            self.contact_freq = None
        else:
            # Backwards-compatible: allow repeated contact attempts using config defaults.
            contacts_per_year = float(
                self.params.get(
                    "Contacts_Per_Year",
                    self.params.get("Contacts Per Year", _require("threats.contact_frequency_defaults.contacts_per_year")),
                )
            )
            dist_type = str(
                self.params.get(
                    "Contact_Freq_Dist_Type",
                    self.params.get("Contact Freq Dist Type", _require("threats.contact_frequency_defaults.dist_type")),
                )
            ).strip()

            hours_per_year_key = str(_require("threats.contact_frequency_defaults.hours_per_year_key")).strip()
            hours_per_year = float(_require(hours_per_year_key))

            self.contact_freq = {
                "contacts_per_year": float(contacts_per_year),
                "dist_type": dist_type,
                "hours_per_year": float(hours_per_year),
            }
            self._schedule_next_contact()

    # -------------------------
    # Sampling helpers
    # -------------------------

    def _rng(self):
        streams = getattr(self.model, "streams", None)
        if streams is not None:
            return streams.agent_rng("threat", str(self.unique_id))
        r = getattr(self.model, "random", None)
        if r is None:
            raise ValueError("Model must provide model.random RNG")
        return r

    def _u(self) -> float:
        return float(self._rng().random())

    def _sample_next_contact_tick(self) -> int:
        """Sample next contact tick (1 tick == 1 hour)."""
        dist = str(self.contact_freq["dist_type"]).strip().lower()
        cpy = float(self.contact_freq["contacts_per_year"])
        if cpy <= 0.0:
            return int(getattr(self.model.schedule, "steps", 0)) + 1

        hpy = float(self.contact_freq["hours_per_year"])
        rate = cpy / max(hpy, 1e-9)  # contacts per hour
        u = min(max(self._u(), 1e-12), 1.0 - 1e-12)

        if dist in ("poisson", "exponential"):
            hours = -math.log(1.0 - u) / max(rate, 1e-12)
        elif dist in ("uniform",):
            mean = 1.0 / max(rate, 1e-12)
            mult = float(_require("threats.contact_frequency_defaults.uniform_max_multiplier"))
            hours = float(self._u()) * (max(0.0, mult) * mean)
        else:
            hours = -math.log(1.0 - u) / max(rate, 1e-12)

        return int(getattr(self.model.schedule, "steps", 0)) + int(max(1.0, hours))

    def _schedule_next_contact(self) -> None:
        if self.contact_freq is None:
            self.next_contact_tick = None
            return
        self.next_contact_tick = self._sample_next_contact_tick()

    # -------------------------
    # Threat sophistication
    # -------------------------

    def sample_sophistication(self) -> float:
        """Sample threat sophistication (0..1) from params or YAML defaults.

        persistent/dedicated threats use max sophistication (param3)
        directly instead of sampling from Beta-PERT.
        """
        p1 = float(self.params.get("Sophistication Param 1", self.params.get("Sophistication_Param_1", _require("threats.sophistication_defaults.param1"))))
        p2 = float(self.params.get("Sophistication Param 2", self.params.get("Sophistication_Param_2", _require("threats.sophistication_defaults.param2"))))
        p3 = float(self.params.get("Sophistication Param 3", self.params.get("Sophistication_Param_3", _require("threats.sophistication_defaults.param3"))))
        p4 = float(self.params.get("Sophistication Param 4", self.params.get("Sophistication_Param_4", _require("threats.sophistication_defaults.param4"))))

        # persistent/dedicated threats use max sophistication directly
        if cfg.get("threats.persistent_use_max_sophistication", True):
            threat_type = str(
                self.params.get("Threat_Type", self.params.get("Threat Type", ""))
            ).strip().lower()
            if threat_type in ("persistent", "dedicated", "apt"):
                return float(min(1.0, max(0.0, p3)))

        # Beta-PERT used throughout the model
        from ..data.distributions import beta_pert
        return float(beta_pert(p1, p2, p3, p4, rng=self._rng()))

    # -------------------------
    # Simulation step
    # -------------------------

    def step(self):
        tick = int(getattr(self.model.schedule, "steps", 0))
        if self.next_contact_tick is None or tick < int(self.next_contact_tick):
            return

        try:
            net = getattr(self.model, "network", None)
            if net is None:
                return

            cp = getattr(self.model, "contact_processor", None)
            if cp is None:
                return

            origin = str(self.origin or "external").strip().lower()

            # Check if we have pending lateral movement targets
            if self._lateral_movement_active and self._lateral_targets:
                # Process ONE lateral movement target per tick (sequential)
                target = self._lateral_targets.pop(0)
                target_id = str(getattr(target, "unique_id", ""))

                # Skip if already breached
                if target_id not in self._breached_tas:
                    outcome = cp.process_contact(self, target)
                    if outcome.breached:
                        self._breached_tas.add(target_id)
                        # Note: lateral movement is one-hop only, so we don't queue more targets

                # If more lateral targets remain, schedule next tick
                if self._lateral_targets:
                    self.next_contact_tick = tick + 1
                    return
                else:
                    # Lateral movement complete
                    self._lateral_movement_active = False
                    # Fall through to cleanup for single_shot or reschedule

            else:
                # Initial contact: target external TAs only (for external threats)
                all_tas = net.get_all_tech_assets()
                if not all_tas:
                    return

                if origin == "external":
                    # External threats target only external TAs (network_layer == "external")
                    targets = [a for a in all_tas
                               if str(getattr(a, "network_layer", "")).lower() == "external"]
                else:
                    # Internal threats can access all TAs
                    targets = list(all_tas)

                if not targets:
                    return

                # Process contact against each external TA
                breached_any = False
                for target in targets:
                    target_id = str(getattr(target, "unique_id", ""))
                    if target_id in self._breached_tas:
                        continue

                    outcome = cp.process_contact(self, target)
                    if outcome.breached:
                        self._breached_tas.add(target_id)
                        breached_any = True

                        # Queue lateral movement targets (one hop from this breached TA)
                        implicit_conn = cfg.get("network.implicit_ta_connectivity", True)
                        lateral_targets = net.get_lateral_movement_targets(target_id, implicit_conn)

                        # Filter out already-breached TAs and add to queue
                        for lt in lateral_targets:
                            lt_id = str(getattr(lt, "unique_id", ""))
                            if lt_id not in self._breached_tas and lt not in self._lateral_targets:
                                self._lateral_targets.append(lt)

                # If we breached something and have lateral targets, activate lateral movement
                if breached_any and self._lateral_targets:
                    self._lateral_movement_active = True
                    # Schedule next tick to process lateral movement
                    self.next_contact_tick = tick + 1
                    return

        except Exception:
            logger.exception("Threat contact processing failed for %s", getattr(self, "unique_id", "Threat"))
        finally:
            # Only cleanup/reschedule if not in active lateral movement
            if not self._lateral_movement_active:
                if self.single_shot:
                    # Remove self after all contact attempts complete
                    try:
                        self.model.schedule.remove(self)
                    except Exception:
                        pass
                    # Do not reschedule
                    self.next_contact_tick = None
                else:
                    self._schedule_next_contact()
