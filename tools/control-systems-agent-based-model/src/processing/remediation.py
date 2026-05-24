"""src/processing/remediation.py

Remediation queue - budget-driven remediation per FAIR-CAM.

Key behaviors:
- Variant controls are queued for remediation.
- Remediation capacity is configurable via YAML:
    budget_mode: continuous | monthly | quarterly
    budget_hours_per_month: total hours available per month (default 40)
  In continuous mode, hours accrue every tick at the hourly rate.
  In monthly/quarterly mode, hours reset at each period boundary.
- Remediation work is scheduled in whole hours (1 tick = 1 hour).
- Priority ordering is type-based (LEC types first), then by scheduling strategy,
  then FIFO within equal priority/cost.
- Scheduling strategy is configurable (YAML: remediation.scheduling_strategy):
    "budget_efficiency" (default) — cheapest (CapEx+OpEx) first, maximises throughput
    "perceived_risk"              — most expensive first; cost as proxy for importance
    "worst_case_impact"           — highest-value linked assets first (crown jewels)

Optional personnel behavior integration:
- If personnel_behavior.enable_vd_linkage is true, remediation effort hours can be multiplied by a
  configurable modifier computed from the decision makers responsible for remediation decisions.
- Decision makers are resolved from YAML:
    ownership.remediation_decision_makers keyed by control node id (e.g., LEC5)

"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
import logging

from ..config import get_config

logger = logging.getLogger(__name__)
config = get_config()


def _require(key: str):
    v = config.get(key, None)
    if v is None:
        raise ValueError(f"Missing required config key: {key}")
    return v


class RemediationPriority(str, Enum):
    RESISTIVE_LEC = "resistive_lec"
    DETECTIVE_LEC = "detective_lec"
    RESPONSE_LEC = "response_lec"
    RESILIENCE_LEC = "resilience_lec"
    OTHER = "other"


@dataclass
class RemediationItem:
    control_id: str
    priority: RemediationPriority
    estimated_hours: int
    queued_tick: int
    remediation_cost: float = 0.0  # CapEx + OpEx for cost-aware scheduling
    risk_score: float = 0.0


# ---------------------------------------------------------------------------
# Scheduling strategies — each returns a sort-key tuple for RemediationItem.
# The queue is always sorted by this key (ascending), so lower = higher priority.
# All strategies share the first tier (LEC type priority); they differ on the
# second key (cost direction) and use FIFO as a tiebreaker.
# ---------------------------------------------------------------------------

_PRIORITY_ORDER = {
    RemediationPriority.RESISTIVE_LEC: 0,
    RemediationPriority.DETECTIVE_LEC: 1,
    RemediationPriority.RESPONSE_LEC: 2,
    RemediationPriority.RESILIENCE_LEC: 3,
    RemediationPriority.OTHER: 4,
}


def _strategy_budget_efficiency(item: RemediationItem) -> tuple:
    """Cheapest first within tier — maximises controls fixed per budget hour."""
    return (_PRIORITY_ORDER.get(item.priority, 99), item.remediation_cost, item.queued_tick)


def _strategy_perceived_risk(item: RemediationItem) -> tuple:
    """Most expensive first within tier — cost as proxy for perceived importance.
    """
    return (_PRIORITY_ORDER.get(item.priority, 99), -item.remediation_cost, item.queued_tick)


def _strategy_worst_case_impact(item: RemediationItem) -> tuple:
    """Most valuable asset first within tier — protect crown jewels."""
    return (_PRIORITY_ORDER.get(item.priority, 99), -item.risk_score, item.queued_tick)


SCHEDULING_STRATEGIES = {
    "budget_efficiency": _strategy_budget_efficiency,
    "perceived_risk": _strategy_perceived_risk,
    "worst_case_impact": _strategy_worst_case_impact,
}


class RemediationQueue:
    def __init__(self, model: Any):
        self.model = model
        self.queue: List[RemediationItem] = []
        self.in_progress: Dict[str, int] = {}  # control_id -> completion_tick
        self.reserved_hours: int = 0
        self._reserved_by_control: Dict[str, int] = {}

        self.ticks_per_month = int(_require("time.ticks_per_month"))

        # Budget mode: continuous | monthly | quarterly
        self.budget_mode = str(config.get("remediation.budget_mode", "monthly")).strip().lower()

        # Total remediation hours available per month (default 40)
        self.budget_hours_per_month = float(config.get("remediation.budget_hours_per_month", 40))

        # Legacy support: if budget_hours_per_month is not set but old keys exist,
        # compute from hours_per_month * budget_percentage
        if config.get("remediation.budget_hours_per_month", None) is None:
            legacy_hpm = config.get("remediation.hours_per_month", None)
            legacy_pct = config.get("remediation.budget_percentage", None)
            if legacy_hpm is not None and legacy_pct is not None:
                self.budget_hours_per_month = float(legacy_hpm) * float(legacy_pct)

        # Period tracking: hours spent this period
        self._period_hours_spent: int = 0
        self._last_period_tick: int = 0

        # For continuous mode: fractional hour accumulator
        self._continuous_accrued: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, control_id: str, control: Any):
        """Add a variant control to the queue (idempotent)."""
        cid = str(control_id or "").strip()
        if not cid:
            return
        if cid in self.in_progress:
            return
        if any(item.control_id == cid for item in self.queue):
            return

        est = self._estimate_remediation_hours(control)
        pri = self._infer_priority(control)
        cost = self._get_remediation_cost(control)
        risk_score = self._compute_risk_score(control)

        self.queue.append(
            RemediationItem(
                control_id=cid,
                priority=pri,
                estimated_hours=max(1, int(est)),
                queued_tick=int(getattr(self.model.schedule, "steps", 0)),
                remediation_cost=cost,
                risk_score=risk_score,
            )
        )

    def step(self):
        self._update_budget()
        self._finish_completed()
        self._start_new_items()

    def _update_budget(self):
        """Update budget based on configured mode."""
        if self.budget_mode == "continuous":
            self._accrue_continuous()
        else:
            self._reset_periodic_budget_if_due()

    def _accrue_continuous(self):
        """Continuous mode: accrue hours every tick at the hourly rate."""
        # hours_per_tick = budget_hours_per_month / ticks_per_month
        if self.ticks_per_month <= 0:
            return
        rate = float(self.budget_hours_per_month) / float(self.ticks_per_month)
        self._continuous_accrued += rate

    def _reset_periodic_budget_if_due(self):
        """Reset the spending counter at each period boundary (monthly or quarterly)."""
        tick = int(getattr(self.model.schedule, "steps", 0))

        if self.budget_mode == "quarterly":
            period_ticks = self.ticks_per_month * 3
        else:
            # Default to monthly
            period_ticks = self.ticks_per_month

        if period_ticks > 0 and tick >= self._last_period_tick + period_ticks:
            self._period_hours_spent = 0
            self._last_period_tick = tick

    # ------------------------------------------------------------------
    # Scheduling helpers
    # ------------------------------------------------------------------

    def _finish_completed(self):
        tick = int(getattr(self.model.schedule, "steps", 0))
        completed = [cid for cid, done_tick in self.in_progress.items() if tick >= int(done_tick)]

        for cid in completed:
            ctrl = self.model.network.get_agent(cid) if hasattr(self.model, "network") else None

            if ctrl is not None:
                try:
                    if hasattr(ctrl, "complete_remediation") and getattr(ctrl, "state", None) == "remediating":
                        ctrl.complete_remediation()
                    elif hasattr(ctrl, "become_normal") and getattr(ctrl, "state", None) == "variant":
                        ctrl.become_normal()
                except Exception:
                    logger.exception("Failed to finalize remediation for %s", cid)

            hrs = int(self._reserved_by_control.pop(cid, 0))
            self.reserved_hours -= hrs

            if self.budget_mode == "continuous":
                # In continuous mode, spent hours reduce the accrued pool
                pass  # already deducted from accrued when reserved
            else:
                self._period_hours_spent += hrs

            self.in_progress.pop(cid, None)

            # Narrative
            if hasattr(self.model, "narrative") and self.model.narrative:
                try:
                    self.model.narrative.record_remediation_completed(
                        control_id=cid,
                        tick=tick,
                        hours=hrs,
                    )
                except Exception:
                    pass

    def _available_hours(self) -> int:
        """Hours available for new work based on budget mode."""
        if self.budget_mode == "continuous":
            # Available = accrued - reserved (already in-progress work)
            return max(0, int(self._continuous_accrued) - int(self.reserved_hours))
        else:
            # Periodic (monthly/quarterly)
            if self.budget_mode == "quarterly":
                budget_hours = int(round(float(self.budget_hours_per_month) * 3))
            else:
                budget_hours = int(round(float(self.budget_hours_per_month)))
            return max(0, budget_hours - int(self.reserved_hours) - int(self._period_hours_spent))

    def _start_new_items(self):
        if not self.queue:
            return

        # Resolve scheduling strategy (with backward compat for old cost_priority key)
        strategy_name = config.get("remediation.scheduling_strategy", None)
        if strategy_name is None:
            old_cost = config.get("remediation.cost_priority", "cheapest_first")
            strategy_name = "perceived_risk" if old_cost == "most_expensive_first" else "budget_efficiency"

        # --- VMC_SELECTS_TREATMENT: demote priority if treatment-selection VMC is variant ---
        net = getattr(self.model, "network", None)
        tick = int(getattr(self.model.schedule, "steps", 0))
        if net is not None and hasattr(net, "get_treatment_selection_vmcs"):
            for item in self.queue:
                try:
                    sel_vmcs = net.get_treatment_selection_vmcs(item.control_id)
                    if sel_vmcs:
                        # If any treatment-selection VMC is variant, demote to OTHER
                        for vmc in sel_vmcs:
                            if str(getattr(vmc, "state", "normal")).lower() == "variant":
                                item.priority = RemediationPriority.OTHER
                                # Record demotion in narrative
                                if hasattr(self.model, "narrative") and self.model.narrative:
                                    try:
                                        self.model.narrative.record_remediation_demoted(
                                            control_id=item.control_id,
                                            tick=tick,
                                            blocking_vmc_ids=[str(getattr(vmc, "unique_id", ""))],
                                            reason="treatment_selection_vmc_variant",
                                        )
                                    except Exception:
                                        pass
                                break
                except Exception:
                    pass

        strategy_fn = SCHEDULING_STRATEGIES.get(strategy_name, _strategy_budget_efficiency)
        self.queue.sort(key=strategy_fn)

        remaining: List[RemediationItem] = []
        for item in self.queue:
            if item.control_id in self.in_progress:
                continue

            avail = self._available_hours()
            # Start if the item fits the current budget, OR if there is any
            # remaining budget and no other work is reserved (allow
            # large items to begin even if they span multiple periods).
            can_start = (
                item.estimated_hours <= avail
                or (avail > 0 and self.reserved_hours == 0)
            )

            if can_start:
                ctrl = self.model.network.get_agent(item.control_id) if hasattr(self.model, "network") else None
                if ctrl is None:
                    remaining.append(item)
                    continue

                # --- VMC_IMPLEMENTS_REMEDIATION: gate remediation start ---
                # At least one implementing VMC must be in normal state;
                # if all are variant, skip this item (leave in queue).
                if net is not None and hasattr(net, "get_implementing_vmcs"):
                    try:
                        impl_vmcs = net.get_implementing_vmcs(item.control_id)
                        if impl_vmcs:
                            any_normal = any(
                                str(getattr(v, "state", "normal")).lower() != "variant"
                                for v in impl_vmcs
                            )
                            if not any_normal:
                                # Record blocked event in narrative
                                if hasattr(self.model, "narrative") and self.model.narrative:
                                    try:
                                        self.model.narrative.record_remediation_blocked(
                                            control_id=item.control_id,
                                            tick=tick,
                                            blocking_vmc_ids=[
                                                str(getattr(v, "unique_id", ""))
                                                for v in impl_vmcs
                                            ],
                                            reason="all_implementing_vmcs_variant",
                                        )
                                    except Exception:
                                        pass
                                remaining.append(item)
                                continue
                    except Exception:
                        pass

                # Reserve hours immediately
                self.reserved_hours += int(item.estimated_hours)
                self._reserved_by_control[item.control_id] = int(item.estimated_hours)

                if self.budget_mode == "continuous":
                    # Deduct from accrued pool
                    self._continuous_accrued -= float(item.estimated_hours)

                try:
                    if hasattr(ctrl, "begin_remediation"):
                        ctrl.begin_remediation()
                except Exception:
                    logger.exception("Failed to begin remediation for %s", item.control_id)
                    hrs = self._reserved_by_control.pop(item.control_id, 0)
                    self.reserved_hours -= int(hrs)
                    if self.budget_mode == "continuous":
                        self._continuous_accrued += float(hrs)
                    continue

                done_tick = int(getattr(self.model.schedule, "steps", 0)) + int(item.estimated_hours)
                self.in_progress[item.control_id] = done_tick

                # Narrative
                if hasattr(self.model, "narrative") and self.model.narrative:
                    try:
                        self.model.narrative.record_remediation_started(
                            control_id=item.control_id,
                            tick=int(getattr(self.model.schedule, "steps", 0)),
                            hours=int(item.estimated_hours),
                        )
                    except Exception:
                        pass
            else:
                remaining.append(item)

        self.queue = remaining

    # ------------------------------------------------------------------
    # Estimation + priority + cost
    # ------------------------------------------------------------------

    def _get_remediation_cost(self, control: Any) -> float:
        """Get the CapEx + OpEx cost for a control (used for cost-aware scheduling)."""
        capex = float(getattr(control, "capex", 0.0) or 0.0)
        opex = float(getattr(control, "opex", 0.0) or 0.0)
        return capex + opex

    def _compute_risk_score(self, control) -> float:
        """Compute risk score based on linked asset value."""
        net = getattr(self.model, "network", None)
        if net is None or not hasattr(net, "get_protected_assets"):
            return 0.0
        try:
            assets = net.get_protected_assets(str(getattr(control, "unique_id", "")))
            if not assets:
                return 0.0
            total = 0.0
            for asset in assets:
                rc = float(getattr(asset, "record_count", 0) or getattr(asset, "params", {}).get("Record_Count", 0) or 0)
                total += max(rc, 1000.0)  # Minimum 1000 for process assets
            return total
        except Exception:
            return 0.0

    def _estimate_remediation_hours(self, control: Any) -> int:
        base_hours: Optional[int] = None

        if hasattr(control, "_calculate_remediation_duration"):
            try:
                base_hours = int(control._calculate_remediation_duration())
            except Exception:
                base_hours = None

        if base_hours is None:
            params = getattr(control, "params", {}) or {}
            for k in ("Remediation_Hours", "Remediation Hours", "remediation_hours"):
                if k in params and params[k] is not None:
                    try:
                        base_hours = int(params[k])
                        break
                    except Exception:
                        pass

        if base_hours is None:
            base_hours = config.get_section("remediation").get("effort", {}).get("default_hours", None)
            if base_hours is None:
                raise ValueError("Missing required config: remediation.effort.default_hours")

        base_hours = int(base_hours)

        # OPTIONAL: Culture remediation_speed modifier
        # High remediation_speed (adhocracy/market) → faster fixes; low (hierarchy) → slower.
        # Speed is inverted: high speed value reduces hours.
        integration = getattr(self.model, "personnel_integration", None)
        if integration is not None and getattr(integration, "enabled", False):
            try:
                cid = str(getattr(control, "unique_id", "")).strip()
                decision_makers: List[str] = []
                if hasattr(integration, "get_remediation_decision_makers"):
                    decision_makers = integration.get_remediation_decision_makers(cid)

                # Apply culture-based remediation speed from owners
                if decision_makers:
                    speeds = []
                    for pid in decision_makers:
                        beh = integration.behaviors.get(pid)
                        if beh is not None:
                            speeds.append(beh.culture_profile.get_behavior_tendency("remediation_speed"))
                    if speeds:
                        avg_speed = sum(speeds) / len(speeds)
                        # Speed 0.5 = neutral (1.0x), speed 1.0 = fast (0.5x), speed 0.0 = slow (1.5x)
                        speed_multiplier = 1.5 - avg_speed
                        base_hours = max(1, int(round(base_hours * speed_multiplier)))

                # OPTIONAL: VD linkage modifier (additional)
                if bool(_require("personnel_behavior.enable_vd_linkage")):
                    mod = float(integration.get_remediation_effort_modifier_for_owners(decision_makers))
                    return max(1, int(round(base_hours * mod)))
            except Exception:
                # Fall back to base if anything fails
                return base_hours

        return base_hours

    def _infer_priority(self, control: Any) -> RemediationPriority:
        lec_type = str(getattr(control, "lec_type", "") or "").strip().lower()
        if lec_type in ("avoidance", "deterrence", "resistance"):
            return RemediationPriority.RESISTIVE_LEC
        if lec_type in ("monitoring", "recognition", "detective"):
            return RemediationPriority.DETECTIVE_LEC
        if lec_type in ("response", "event_termination", "termination"):
            return RemediationPriority.RESPONSE_LEC
        if lec_type in ("resilience", "recovery"):
            return RemediationPriority.RESILIENCE_LEC
        return RemediationPriority.OTHER
