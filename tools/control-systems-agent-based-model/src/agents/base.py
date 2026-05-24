"""src/agents/base.py

Base control agent with state machine implementation.

Notes:
- Loader is responsible for filling missing columns using YAML defaults.
- All default behavior comes from YAML.
- All stochastic draws use the model RNG (`model.random`) for reproducibility.
- This agent supports both DSC-style and VM/LEC-style efficacy parameter columns.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import logging

from mesa import Agent
from transitions import Machine

from ..config import get_config
from ..data.distributions import beta_pert, uniform as uniform_sample

logger = logging.getLogger(__name__)
cfg = get_config()


class BaseControlAgent(Agent, ABC):
    states = ["inactive", "normal", "variant", "remediating"]

    def __init__(self, model: Any, unique_id: str, params: Dict[str, Any]):
        try:
            super().__init__(model)          # Mesa 3.x
            self.unique_id = unique_id
        except TypeError:
            super().__init__(unique_id, model)  # Mesa 2.x

        self.params = params or {}

        # Filled by Loader using YAML defaults
        self.capex = float(self.params.get("CapEx"))
        self.opex = float(self.params.get("OpEx"))

        # Parse efficacy + change frequency parameters (filled by loader if missing)
        self.efficacy_dist_params = self._parse_dist_params(prefix="Efficacy")
        self.change_freq_dist_params = self._parse_dist_params(prefix="Change Freq")

        self.intended_efficacy = self._sample_intended_efficacy()
        self.current_efficacy = float(self.intended_efficacy)
        self.variant_efficacy = 0.0

        self.next_change_time: Optional[int] = None
        self.remediation_end_time: Optional[int] = None

        self.machine = Machine(
            model=self,
            states=self.states,
            initial="normal",
            auto_transitions=False,
            send_event=True,
        )
        self._setup_transitions()
        self._schedule_next_change()

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _rng(self, subsystem: str = "default"):
        """Get RNG for this agent.

        When stream isolation is enabled (for marginal value analysis),
        returns a per-agent stream for the given subsystem (e.g.,
        "efficacy", "variance"). This ensures removing one control
        doesn't shift another control's random draws.
        """
        streams = getattr(self.model, "streams", None)
        if streams is not None:
            return streams.agent_rng(subsystem, str(self.unique_id))
        r = getattr(self.model, "random", None)
        if r is None:
            raise ValueError("Model must provide model.random RNG")
        return r

    def _require_cfg(self, key: str):
        v = cfg.get(key, None)
        if v is None:
            raise ValueError(f"Missing required config key: {key}")
        return v

    def _get_control_type_category(self) -> str:
        """Return 'LEC', 'VMC', or 'DSC' based on unique_id prefix or control_type."""
        uid = str(self.unique_id).upper()
        if uid.startswith("LEC"):
            return "LEC"
        if uid.startswith("VM"):
            return "VMC"
        if uid.startswith("DSC"):
            return "DSC"
        # Fallback to control_type attribute
        ct = str(getattr(self, "control_type", "")).upper()
        if "LEC" in ct:
            return "LEC"
        if "VM" in ct:
            return "VMC"
        return "OTHER"

    # ------------------------------------------------------------------
    # Parameter parsing
    # ------------------------------------------------------------------

    def _parse_dist_params(self, prefix: str) -> Dict[str, Any]:
        """Parse distribution parameters from params.

        Expected normalized columns (via Loader):
          - '{prefix} Dist Type', '{prefix} Param 1..4'

        Back-compat for VM/LEC efficacy sheets:
          - 'Dist Type', 'Param 1..4' (only for prefix == 'Efficacy')
        """
        dist_type = self.params.get(f"{prefix} Dist Type", None)
        if dist_type is None and prefix == "Efficacy":
            dist_type = self.params.get("Dist Type", None)
        if dist_type is None:
            raise ValueError(f"Missing required distribution type for {prefix}: '{prefix} Dist Type'")

        def get_param(n: int):
            v = self.params.get(f"{prefix} Param {n}", None)
            if v is None and prefix == "Efficacy":
                v = self.params.get(f"Param {n}", None)
            if v is None:
                raise ValueError(f"Missing required {prefix} Param {n}")
            return float(v)

        return {
            "dist_type": str(dist_type).strip(),
            "param1": float(get_param(1)),
            "param2": float(get_param(2)),
            "param3": float(get_param(3)),
            "param4": float(get_param(4)),
        }

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _setup_transitions(self):
        self.machine.add_transition(
            trigger="become_variant",
            source="normal",
            dest="variant",
            before="_on_enter_variant",
        )
        self.machine.add_transition(
            trigger="begin_remediation",
            source="variant",
            dest="remediating",
            before="_on_enter_remediating",
        )
        self.machine.add_transition(
            trigger="complete_remediation",
            source="remediating",
            dest="normal",
            before="_on_return_to_normal",
        )
        self.machine.add_transition(
            trigger="deactivate",
            source=["normal", "variant", "remediating"],
            dest="inactive",
        )
        self.machine.add_transition(
            trigger="activate",
            source="inactive",
            dest="normal",
            before="_on_return_to_normal",
        )

    def _on_enter_variant(self, event):
        """Transition into Variant condition.

        Variance can be intrinsic (control drift, personnel errors) or
        extrinsic (threat landscape changes, zero-days) per KB §09.
        Regardless of cause, the control's *current* efficacy is set to
        a degraded value and remains at that degraded level until it is
        remediated (i.e., until it returns to normal).

        We draw a single degraded efficacy value at variant entry and
        store it in ``current_efficacy`` for all downstream evaluations.
        """
        self.variant_efficacy = self._calculate_variant_efficacy()
        self.current_efficacy = float(self.variant_efficacy)

        # metrics: variance count (total and by control type)
        ms = getattr(self.model, "metrics_state", None)
        if ms is not None and hasattr(ms, "total_variance_events"):
            try:
                ms.total_variance_events += 1
                # Track by control type
                control_type = self._get_control_type_category()
                if control_type == "LEC" and hasattr(ms, "total_lec_variance_events"):
                    ms.total_lec_variance_events += 1
                elif control_type == "VMC" and hasattr(ms, "total_vmc_variance_events"):
                    ms.total_vmc_variance_events += 1
            except Exception:
                pass

        logger.debug(
            "Control %s became variant. efficacy: %.3f -> %.3f",
            self.unique_id,
            float(self.intended_efficacy),
            float(self.variant_efficacy),
        )

        # narrative — pass through change_type + variance source classification
        nar = getattr(self.model, "narrative", None)
        if nar is not None and hasattr(nar, "record_variance_event"):
            change_type = getattr(self, "_pending_change_type", "unknown") or "unknown"
            self._pending_change_type = None  # consume

            if change_type == "threat_landscape":
                variance_source = "extrinsic"
                cause = "threat_landscape_change"
            elif change_type == "personnel_monthly":
                variance_source = "intrinsic"
                cause = "personnel_error"
            elif change_type == "periodic_internal":
                variance_source = "intrinsic"
                cause = "control_drift"
            else:
                variance_source = "unknown"
                cause = change_type

            try:
                nar.record_variance_event(
                    control_id=str(self.unique_id),
                    tick=int(getattr(self.model.schedule, "steps", 0)),
                    change_type=change_type,
                    intended_efficacy=float(self.intended_efficacy),
                    variant_efficacy=float(self.variant_efficacy),
                    cause=cause,
                    variance_source=variance_source,
                )
            except Exception:
                pass

        # Remediation enqueue is handled by VMC detection sweeps.
        # Controls remain variant until a VMC monitoring sweep detects them and
        # adds them to the remediation queue via vmc_detection._enqueue_if_detected().

    def _on_enter_remediating(self, event):
        duration = int(self._calculate_remediation_duration())
        self.remediation_end_time = int(getattr(self.model.schedule, "steps", 0)) + duration
        logger.debug("Control %s entering remediation. duration=%s hours", self.unique_id, duration)

    def _on_return_to_normal(self, event):
        self.intended_efficacy = self._sample_intended_efficacy()
        self.current_efficacy = float(self.intended_efficacy)
        self.remediation_end_time = None
        self._schedule_next_change()
        logger.debug("Control %s returned to normal. efficacy=%.3f", self.unique_id, float(self.current_efficacy))

        # Record recovery event in narrative (for efficacy timeline chart)
        nar = getattr(self.model, "narrative", None)
        if nar is not None and hasattr(nar, "record_recovery_event"):
            try:
                nar.record_recovery_event(
                    control_id=str(self.unique_id),
                    tick=int(getattr(self.model.schedule, "steps", 0)),
                    restored_efficacy=float(self.intended_efficacy),
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Efficacy + scheduling
    # ------------------------------------------------------------------

    def _calculate_variant_efficacy(self) -> float:
        """Calculate efficacy when the control enters variant state.

        Per FAIR-CAM:
        - **Binary controls** (Binary_Variance_Efficacy=True): VarEff = 0.0
          The control is either working (IntEff) or completely non-functional.
        - **Non-binary controls**: VarEff ~ Uniform(0, IntEff)
          The control degrades to a random level between 0 and its intended efficacy.
        """
        if self.params.get("Binary_Variance_Efficacy", False):
            return 0.0
        return float(uniform_sample(0.0, float(self.intended_efficacy), rng=self._rng("efficacy")))

    def trigger_variance(self, reason: str = ""):
        if getattr(self, "state", None) == "normal":
            logger.info("%s variance triggered: %s", self.unique_id, reason)
            self.become_variant()

    def _sample_intended_efficacy(self) -> float:
        p = self.efficacy_dist_params
        dist = str(p["dist_type"]).strip().lower()
        if dist == "uniform":
            return float(uniform_sample(p["param1"], p["param2"], rng=self._rng("efficacy")))
        # Default/expected: Beta PERT
        return float(beta_pert(p["param1"], p["param2"], p["param3"], p["param4"], rng=self._rng("efficacy")))

    def _schedule_next_change(self):
        """Schedule the next intrinsic variance event (control drift).

        Intrinsic variance — regular, internally-driven (KB §09):
        each control naturally drifts from its intended state over time
        (e.g., patches go stale, configurations drift).

        Interpretation:
        - Uniform: sample uniform(param1, param2) hours
        - Beta PERT: sample beta_pert(param1, param2, param3, param4) hours

        If VM "reduce var freq" VMCs are linked and enabled,
        extend the interval by the best VMC efficacy (high efficacy = longer interval).
        """
        p = self.change_freq_dist_params
        dist = str(p["dist_type"]).strip().lower()

        if dist == "uniform":
            base_hours = float(uniform_sample(p["param1"], p["param2"], rng=self._rng("variance")))
        else:
            base_hours = float(beta_pert(p["param1"], p["param2"], p["param3"], p["param4"], rng=self._rng("variance")))

        effective_hours = base_hours

        # VM "reduce var freq" extends interval
        if cfg.get("variance_prevention.enable_vm_reduce_freq", True):
            net = getattr(self.model, "network", None)
            if net is not None and hasattr(net, "get_vmc_reduce_freq_controls"):
                vmcs = net.get_vmc_reduce_freq_controls(str(self.unique_id))
                max_eff = 0.0
                for vmc in vmcs:
                    if str(getattr(vmc, "state", "normal")).lower() == "variant":
                        continue  # Skip variant VMCs
                    eff = float(getattr(vmc, "get_effective_efficacy", lambda: 0.0)()
                                if callable(getattr(vmc, "get_effective_efficacy", None))
                                else getattr(vmc, "current_efficacy", 0.0))
                    max_eff = max(max_eff, eff)
                if max_eff > 0.0:
                    effective_hours = base_hours + max_eff * base_hours

        self.next_change_time = int(getattr(self.model.schedule, "steps", 0)) + int(effective_hours)

    def get_effective_efficacy(self) -> float:
        """Single source of truth for the efficacy that applies right now."""
        st = str(getattr(self, "state", "normal")).lower()
        if st == "inactive":
            return 0.0
        if st in ("variant", "remediating"):
            return float(getattr(self, "current_efficacy", 0.0) or 0.0)
        return float(getattr(self, "current_efficacy", getattr(self, "intended_efficacy", 0.0)) or 0.0)

    def is_software_based(self) -> bool:
        """Return True if this control is software-based (not human-actor).

        Used by extrinsic variance: only software-based controls
        auto-transition to variant when the threat landscape changes
        (e.g., new zero-day exploits). Human-actor controls are unaffected.
        LECs have explicit actor_type from JSON; VMCs and DSCs are assumed
        software-based since only LECs carry the human/software distinction.
        """
        actor = str(getattr(self, "actor_type", "technology")).strip().lower()
        return actor != "human"

    # ------------------------------------------------------------------
    # Abstract methods
    # ------------------------------------------------------------------

    @abstractmethod
    def _calculate_remediation_duration(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def on_change_event(self, change_type: str) -> bool:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Variance prevention
    # ------------------------------------------------------------------

    def _attempt_variance(self):
        """Gate intrinsic variance behind DSC check + VM "reduce var prob" check.

        For intrinsic variance (control drift and personnel-driven), the
        control passes through two prevention gates before becoming variant:
          change event -> DSC check -> VM "reduce var prob" -> only then variant.

        Note: extrinsic variance (threat landscape changes) bypasses these
        gates entirely — see model._process_threat_landscape_change().

        If either check prevents variance, reschedule next change and return.
        """
        # 1) DSC check: find personnel managing this control
        if cfg.get("variance_prevention.enable_dsc_check", True):
            dsc_model = getattr(self.model, "dsc_decision_model", None)
            integration = getattr(self.model, "personnel_integration", None)
            if dsc_model is not None and integration is not None and getattr(integration, "enabled", False):
                owners = integration.get_control_owners(str(self.unique_id))
                if owners:
                    # Check ALL managing personnel (OR logic — KB §01, §06):
                    # if ANY aligned person is found, variance is blocked.
                    for oid in owners:
                        pb = integration.behaviors.get(oid)
                        if pb is not None:
                            try:
                                aligned = dsc_model.query_decision_alignment(pb.agent)
                                if aligned:
                                    # Personnel caught the mistake — variance prevented
                                    self._schedule_next_change()
                                    return
                            except Exception:
                                pass

        # 2) VM "reduce var prob" check
        if cfg.get("variance_prevention.enable_vm_reduce_prob", True):
            net = getattr(self.model, "network", None)
            if net is not None and hasattr(net, "get_vmc_reduce_prob_controls"):
                vmcs = net.get_vmc_reduce_prob_controls(str(self.unique_id))
                for vmc in vmcs:
                    if str(getattr(vmc, "state", "normal")).lower() == "variant":
                        continue  # Skip variant VMCs
                    eff = float(getattr(vmc, "get_effective_efficacy", lambda: 0.0)()
                                if callable(getattr(vmc, "get_effective_efficacy", None))
                                else getattr(vmc, "current_efficacy", 0.0))
                    if eff > 0.0 and float(self._rng("variance").random()) < eff:
                        # VM prevented variance
                        self._schedule_next_change()
                        return

        # 3) Neither prevented — become variant
        self.on_change_event("periodic_internal")

    def _any_linked_personnel_has_admin(self) -> bool:
        """Check if any personnel linked to this control have admin_privileges.

        This check is ONLY used for monthly personnel-driven variance,
        NOT for periodic internal changes (spec: 'not factoring in admin permissions').

        Returns True when personnel integration is disabled (backward compat).
        """
        integration = getattr(self.model, "personnel_integration", None)
        if integration is None or not getattr(integration, "enabled", False):
            return True  # When personnel disabled, skip admin check

        owners = integration.get_control_owners(str(self.unique_id))
        if not owners:
            return False  # No linked personnel → no admin-driven variance

        for oid in owners:
            pb = integration.behaviors.get(oid)
            if pb is not None:
                agent = pb.agent
                if getattr(agent, "admin_privileges", False):
                    return True

        return False

    def attempt_personnel_variance(self, personnel_agent) -> bool:
        """Attempt personnel-driven variance (monthly check, spec slide 38).

        Flow:
          1) Admin check: if personnel has no admin_privileges, return False
          2) DSC check: if DSC decision model says aligned, variance prevented
          3) VM "reduce var prob": VMC Bernoulli gate
          4) If neither prevented, become variant

        This is separate from _attempt_variance() because:
          - Admin check is ONLY applied here
          - The personnel agent is explicit (not inferred from ownership)
          - This is called monthly, not on change-freq schedule

        Returns True if variance occurred, False if prevented.
        """
        if getattr(self, "state", None) != "normal":
            return False

        # 1) Admin check
        if not getattr(personnel_agent, "admin_privileges", False):
            return False

        # 2) DSC check
        if cfg.get("variance_prevention.enable_dsc_check", True):
            dsc_model = getattr(self.model, "dsc_decision_model", None)
            if dsc_model is not None:
                try:
                    aligned = dsc_model.query_decision_alignment(personnel_agent)
                    if aligned:
                        return False  # Personnel caught the mistake
                except Exception:
                    pass

        # 2) Culture variance tolerance gate
        # Personnel in high-tolerance cultures (adhocracy) shrug off misalignment;
        # low-tolerance cultures (hierarchy) escalate immediately.
        integration = getattr(self.model, "personnel_integration", None)
        if integration is not None and getattr(integration, "enabled", False):
            behavior = integration.behaviors.get(str(getattr(personnel_agent, "unique_id", "")))
            if behavior is not None:
                tolerance = behavior.culture_profile.get_behavior_tendency("variance_tolerance")
                if float(self._rng("variance").random()) < tolerance:
                    return False  # Misalignment tolerated — personnel lets it slide

        # 3) VM "reduce var prob" check
        if cfg.get("variance_prevention.enable_vm_reduce_prob", True):
            net = getattr(self.model, "network", None)
            if net is not None and hasattr(net, "get_vmc_reduce_prob_controls"):
                vmcs = net.get_vmc_reduce_prob_controls(str(self.unique_id))
                for vmc in vmcs:
                    if str(getattr(vmc, "state", "normal")).lower() == "variant":
                        continue
                    eff = float(getattr(vmc, "get_effective_efficacy", lambda: 0.0)()
                                if callable(getattr(vmc, "get_effective_efficacy", None))
                                else getattr(vmc, "current_efficacy", 0.0))
                    if eff > 0.0 and float(self._rng("variance").random()) < eff:
                        return False  # VM prevented variance

        # 4) Neither prevented — become variant
        self.on_change_event("personnel_monthly")
        return True

    # ------------------------------------------------------------------
    # Mesa step
    # ------------------------------------------------------------------

    def step(self):
        current_tick = int(getattr(self.model.schedule, "steps", 0))

        # Self-driven change events — now gated through _attempt_variance()
        if self.next_change_time is not None and current_tick >= int(self.next_change_time):
            if getattr(self, "state", None) == "normal":
                self._attempt_variance()

        # Remediation completion is handled by RemediationQueue (budget-gated).
        # The queue calls complete_remediation() when hours are spent.
