"""
Narrative tracing and causation analysis.

Features:
- Loss events carry a breach_tick (from LossEventProcessor).
- Root causes are identified using breach_tick as the cutoff, not loss_tick.
- Root causes consider controls relevant at breach time (variant_controls + failed_controls).
- Robustness: normalize control IDs, fall back to breach record when loss record lacks controls,
  and (optionally) expand upstream via network influence edges when available.
"""

import logging
import math
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

from ..config import get_config

logger = logging.getLogger(__name__)

cfg = get_config()


def _require(key: str):
    v = cfg.get(key, None)
    if v is None:
        raise ValueError(f"Missing required config key: {key}")
    return v


def _norm_id(x: Any) -> str:
    """Normalize IDs for stable matching across sources."""
    s = str(x or "").strip()
    # Keep original casing but normalize common accidental whitespace issues.
    # For fully case-insensitive matching, change to: return s.upper()
    return s


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for it in items:
        itn = _norm_id(it)
        if not itn:
            continue
        if itn in seen:
            continue
        seen.add(itn)
        out.append(itn)
    return out


@dataclass
class VarianceNarrative:
    """Narrative of a control entering variant state."""
    control_id: str
    tick: int
    change_type: str = "unknown"       # periodic_internal | personnel_monthly | threat_landscape
    intended_efficacy: float = 0.0
    variant_efficacy: float = 0.0
    cause: Optional[str] = None        # control_drift | personnel_error | threat_landscape_change
    variance_source: str = "unknown"   # intrinsic | extrinsic | unknown


@dataclass
class RecoveryNarrative:
    """Narrative of a control returning to normal state after remediation."""
    control_id: str
    tick: int
    restored_efficacy: float = 0.0


@dataclass
class RemediationNarrative:
    """Narrative of a remediation lifecycle event."""
    control_id: str
    tick: int
    event_type: str = "started"  # started | completed | blocked | demoted
    hours: int = 0
    # For blocked/demoted events: which VMC(s) caused the block/demotion
    blocking_vmc_ids: List[str] = field(default_factory=list)
    reason: str = ""  # e.g., "all_implementing_vmcs_variant", "treatment_selection_vmc_variant"


@dataclass
class BreachNarrative:
    """Narrative of a successful breach."""
    threat_id: str
    tech_asset_id: str
    tick: int
    failed_controls: List[str] = field(default_factory=list)
    variant_controls_at_breach: List[str] = field(default_factory=list)
    threat_sophistication: float = 0.0
    # Enhanced details
    control_efficacies: Dict[str, float] = field(default_factory=dict)  # control_id -> efficacy at breach
    threat_origin: str = "unknown"  # internal/external
    # Breach mechanics (computed during contact processing)
    breach_mechanics: Dict[str, Any] = field(default_factory=dict)
    per_control_detail: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class LossEventNarrative:
    """Complete narrative of a loss event with causation chain."""
    event_id: str
    business_asset_id: str
    tech_asset_id: str
    threat_id: str
    tick: int                     # loss tick
    breach_tick: int = 0          # breach tick for causation cutoff

    primary_loss: float = 0.0
    secondary_loss: float = 0.0
    total_loss: float = 0.0

    failed_controls: List[str] = field(default_factory=list)
    variant_controls: List[str] = field(default_factory=list)
    root_variance_events: List[str] = field(default_factory=list)  # "CONTROL@tick"

    # Enhanced details for full narrative
    asset_type: str = "unknown"  # information/process
    loss_time_hours: float = 0.0
    outage_hours: Optional[float] = None  # for process assets
    threat_sophistication: float = 0.0
    control_efficacies_at_breach: Dict[str, float] = field(default_factory=dict)  # control_id -> efficacy
    proximate_root_cause: Optional[str] = None  # most recent variance before breach
    breach_category: str = "unknown"  # threat_exceeded | variance_enabled | missing_controls

    # Breach mechanics and per-control detail (from contact processing)
    breach_mechanics: Dict[str, Any] = field(default_factory=dict)
    per_control_detail: List[Dict[str, Any]] = field(default_factory=list)
    # Enriched per-control detail with variance type information
    control_variance_detail: List[Dict[str, Any]] = field(default_factory=list)
    # Human-readable causation story
    causation_narrative: str = ""
    # Risk management failure classification
    loss_driver: str = "design_weakness"


class NarrativeCollector:
    """
    Collects narratives throughout simulation and performs causation analysis.
    """

    def __init__(self, model):
        self.model = model

        self.variance_events: List[VarianceNarrative] = []
        self.recovery_events: List[RecoveryNarrative] = []
        self.remediation_events: List[RemediationNarrative] = []
        self.breach_events: List[BreachNarrative] = []
        self.loss_events: List[LossEventNarrative] = []

        self.variance_by_control: Dict[str, List[VarianceNarrative]] = defaultdict(list)
        self.recovery_by_control: Dict[str, List[RecoveryNarrative]] = defaultdict(list)
        self.remediation_by_control: Dict[str, List[RemediationNarrative]] = defaultdict(list)
        self.breach_by_tech_asset: Dict[str, List[BreachNarrative]] = defaultdict(list)

        # Optional fast lookup: (tech_asset_id, threat_id, breach_tick) -> BreachNarrative
        self._breach_index: Dict[Tuple[str, str, int], BreachNarrative] = {}

        self.loss_event_counter = 0

    # ---------------- Recording ----------------

    def record_variance_event(
        self,
        control_id: str,
        tick: int,
        change_type: str = "unknown",
        intended_efficacy: float = 0.0,
        variant_efficacy: float = 0.0,
        cause: Optional[str] = None,
        variance_source: str = "unknown",
        **kwargs
    ):
        cid = _norm_id(control_id)
        narrative = VarianceNarrative(
            control_id=cid,
            tick=int(tick),
            change_type=change_type,
            intended_efficacy=float(intended_efficacy or 0.0),
            variant_efficacy=float(variant_efficacy or 0.0),
            cause=cause,
            variance_source=variance_source,
        )

        self.variance_events.append(narrative)
        self.variance_by_control[cid].append(narrative)

        logger.debug(
            "Variance: %s at tick %s, efficacy %.2f -> %.2f",
            cid, tick, narrative.intended_efficacy, narrative.variant_efficacy
        )

    def record_recovery_event(
        self,
        control_id: str,
        tick: int,
        restored_efficacy: float = 0.0,
    ):
        cid = _norm_id(control_id)
        narrative = RecoveryNarrative(
            control_id=cid,
            tick=int(tick),
            restored_efficacy=float(restored_efficacy or 0.0),
        )
        self.recovery_events.append(narrative)
        self.recovery_by_control[cid].append(narrative)

    def record_remediation_started(
        self,
        control_id: str,
        tick: int,
        hours: int = 0,
    ):
        cid = _norm_id(control_id)
        narrative = RemediationNarrative(
            control_id=cid, tick=int(tick), event_type="started", hours=int(hours),
        )
        self.remediation_events.append(narrative)
        self.remediation_by_control[cid].append(narrative)

    def record_remediation_completed(
        self,
        control_id: str,
        tick: int,
        hours: int = 0,
    ):
        cid = _norm_id(control_id)
        narrative = RemediationNarrative(
            control_id=cid, tick=int(tick), event_type="completed", hours=int(hours),
        )
        self.remediation_events.append(narrative)
        self.remediation_by_control[cid].append(narrative)

    def record_remediation_blocked(
        self,
        control_id: str,
        tick: int,
        blocking_vmc_ids: Optional[List[str]] = None,
        reason: str = "",
    ):
        cid = _norm_id(control_id)
        narrative = RemediationNarrative(
            control_id=cid, tick=int(tick), event_type="blocked",
            blocking_vmc_ids=list(blocking_vmc_ids or []),
            reason=reason,
        )
        self.remediation_events.append(narrative)
        self.remediation_by_control[cid].append(narrative)

    def record_remediation_demoted(
        self,
        control_id: str,
        tick: int,
        blocking_vmc_ids: Optional[List[str]] = None,
        reason: str = "",
    ):
        cid = _norm_id(control_id)
        narrative = RemediationNarrative(
            control_id=cid, tick=int(tick), event_type="demoted",
            blocking_vmc_ids=list(blocking_vmc_ids or []),
            reason=reason,
        )
        self.remediation_events.append(narrative)
        self.remediation_by_control[cid].append(narrative)

    def record_breach(
        self,
        threat_id: str,
        tech_asset_id: str,
        tick: int,
        failed_controls: Optional[List[str]] = None,
        variant_controls: Optional[List[str]] = None,
        threat_sophistication: float = 0.0,
        control_efficacies: Optional[Dict[str, float]] = None,
        threat_origin: str = "unknown",
        breach_mechanics: Optional[Dict[str, Any]] = None,
        per_control_detail: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ):
        th = _norm_id(threat_id)
        ta = _norm_id(tech_asset_id)
        btick = int(tick)

        failed = _dedupe_keep_order([_norm_id(x) for x in (failed_controls or [])])
        variant = _dedupe_keep_order([_norm_id(x) for x in (variant_controls or [])])

        narrative = BreachNarrative(
            threat_id=th,
            tech_asset_id=ta,
            tick=btick,
            failed_controls=failed,
            variant_controls_at_breach=variant,
            threat_sophistication=float(threat_sophistication or 0.0),
            control_efficacies=dict(control_efficacies) if control_efficacies else {},
            threat_origin=str(threat_origin or "unknown"),
            breach_mechanics=dict(breach_mechanics) if breach_mechanics else {},
            per_control_detail=list(per_control_detail) if per_control_detail else [],
        )

        self.breach_events.append(narrative)
        self.breach_by_tech_asset[ta].append(narrative)
        self._breach_index[(ta, th, btick)] = narrative

        logger.info(
            "Breach: %s -> %s at tick %s, failed=%s variant=%s soph=%.3f",
            th, ta, btick, len(failed), len(variant), float(threat_sophistication or 0.0)
        )

    def record_loss_event(
        self,
        business_asset_id: str,
        tech_asset_id: str,
        threat_id: str,
        tick: int,                 # loss tick
        primary_loss: float,
        secondary_loss: float,
        breach_tick: Optional[int] = None,
        failed_controls: Optional[List[str]] = None,
        variant_controls: Optional[List[str]] = None,
        # Enhanced details
        asset_type: str = "unknown",
        loss_time_hours: float = 0.0,
        outage_hours: Optional[float] = None,
        **kwargs
    ):
        self.loss_event_counter += 1
        event_id = f"LOSS_{self.loss_event_counter}"

        th = _norm_id(threat_id)
        ta = _norm_id(tech_asset_id)
        ba = _norm_id(business_asset_id)

        loss_tick = int(tick)
        breach_tick_val = int(breach_tick) if breach_tick is not None else loss_tick

        failed = _dedupe_keep_order([_norm_id(x) for x in (failed_controls or [])])
        variant = _dedupe_keep_order([_norm_id(x) for x in (variant_controls or [])])

        # Get breach record for additional details
        breach_record = self._breach_index.get((ta, th, breach_tick_val))
        if breach_record is None:
            breach_record = self._find_best_breach(tech_asset_id=ta, threat_id=th, breach_tick=breach_tick_val)

        # Robust fallback: if caller didn't pass controls, pull from breach record.
        if not failed and not variant and breach_record is not None:
            failed = _dedupe_keep_order(list(breach_record.failed_controls))
            variant = _dedupe_keep_order(list(breach_record.variant_controls_at_breach))

        # Get control efficacies and threat sophistication from breach record
        control_efficacies_at_breach: Dict[str, float] = {}
        threat_sophistication = 0.0
        if breach_record is not None:
            control_efficacies_at_breach = dict(breach_record.control_efficacies)
            threat_sophistication = breach_record.threat_sophistication

        # Root causes: variance events BEFORE/AT breach tick for controls relevant at breach time
        root_variance_events, relevant_controls = self._identify_root_variance_events(
            tech_asset_id=ta,
            threat_id=th,
            failed_controls=failed,
            variant_controls=variant,
            breach_tick=breach_tick_val,
        )

        # Find the most proximate root cause (most recent variance before breach among variant controls)
        proximate_root_cause: Optional[str] = None
        if variant and root_variance_events:
            # Find latest variance among controls that were variant at breach
            latest_tick = -1
            for rv in root_variance_events:
                if "@" in rv:
                    ctrl, tick_str = rv.split("@", 1)
                    if ctrl in variant:
                        try:
                            var_tick = int(tick_str)
                            if var_tick > latest_tick and var_tick <= breach_tick_val:
                                latest_tick = var_tick
                                proximate_root_cause = rv
                        except ValueError:
                            pass

        # Propagate breach mechanics from the breach record
        breach_mechanics: Dict[str, Any] = {}
        per_control_detail: List[Dict[str, Any]] = []
        if breach_record is not None:
            breach_mechanics = dict(getattr(breach_record, "breach_mechanics", {}) or {})
            per_control_detail = list(getattr(breach_record, "per_control_detail", []) or [])

        # Classify breach category using counterfactual analysis:
        #   - threat_exceeded: threat would have breached even at intended efficacy
        #   - variance_enabled: breach was causally enabled by control variance
        #     (counterfactual: at intended efficacy, the threat would NOT have breached)
        #   - missing_controls: no LECs in protection path (MISSING_LEC marker)
        #
        # Only resistance-stage controls affect P(breach). Time-based detection/response
        # controls affect loss severity but don't enable the breach itself.
        if "MISSING_LEC" in failed or "MISSING_LEC" in variant:
            breach_category = "missing_controls"
        else:
            resistance_detail = [
                c for c in per_control_detail if c.get("stage") == "resistance"
            ]
            resistance_ids = {c.get("control_id") for c in resistance_detail}
            resistance_variant = [v for v in variant if v in resistance_ids]

            if not resistance_variant:
                breach_category = "threat_exceeded"
            else:
                # Counterfactual: would the breach have occurred if all controls
                # were at intended efficacy?  Recompute combined RS from intended
                # efficacies and compare against threat sophistication.
                intended_effs = [
                    float(c.get("intended_efficacy", 0.0))
                    for c in resistance_detail
                    if c.get("intended_efficacy") is not None
                ]
                if intended_effs:
                    counterfactual_rs = 1.0 - math.prod(1.0 - e for e in intended_effs)
                    if threat_sophistication > counterfactual_rs:
                        # Threat would have breached anyway — variance was coincidental
                        breach_category = "threat_exceeded"
                    else:
                        # Variance was causally necessary for the breach
                        breach_category = "variance_enabled"
                else:
                    # No intended efficacy data — fall back to heuristic
                    breach_category = "variance_enabled"

        # Build enriched per-control detail with variance type information
        control_variance_detail = self._build_control_variance_detail(
            per_control_detail=per_control_detail,
            variant_controls=variant,
            breach_tick=breach_tick_val,
        )

        # Generate human-readable causation text
        causation_narrative = self._generate_causation_text(
            breach_category=breach_category,
            threat_sophistication=threat_sophistication,
            breach_mechanics=breach_mechanics,
            control_variance_detail=control_variance_detail,
            variant_controls=variant,
        )

        # Classify loss driver
        failure_mode = self._classify_loss_driver({
            "detected": breach_category != "missing_controls",
            "variant_controls": variant,
            "failed_controls": failed,
        })

        narrative = LossEventNarrative(
            event_id=event_id,
            business_asset_id=ba,
            tech_asset_id=ta,
            threat_id=th,
            tick=loss_tick,
            breach_tick=breach_tick_val,
            primary_loss=float(primary_loss or 0.0),
            secondary_loss=float(secondary_loss or 0.0),
            total_loss=float(primary_loss or 0.0) + float(secondary_loss or 0.0),
            failed_controls=failed,
            variant_controls=variant,
            root_variance_events=root_variance_events,
            # Enhanced details
            asset_type=str(asset_type or "unknown"),
            loss_time_hours=float(loss_time_hours or 0.0),
            outage_hours=float(outage_hours) if outage_hours is not None else None,
            threat_sophistication=threat_sophistication,
            control_efficacies_at_breach=control_efficacies_at_breach,
            proximate_root_cause=proximate_root_cause,
            breach_category=breach_category,
            # Breach mechanics + enriched control detail
            breach_mechanics=breach_mechanics,
            per_control_detail=per_control_detail,
            control_variance_detail=control_variance_detail,
            causation_narrative=causation_narrative,
            loss_driver=failure_mode,
        )

        self.loss_events.append(narrative)

        logger.info(
            "Loss %s: BA=%s type=%s loss=$%s category=%s root_causes=%s proximate=%s breach_tick=%s",
            event_id,
            ba,
            asset_type,
            f"{narrative.total_loss:,.2f}",
            breach_category,
            len(root_variance_events),
            proximate_root_cause or "none",
            breach_tick_val,
        )

    # ---------------- Root cause logic ----------------

    def _find_best_breach(self, tech_asset_id: str, threat_id: str, breach_tick: int) -> Optional[BreachNarrative]:
        breaches = self.breach_by_tech_asset.get(tech_asset_id, [])
        best: Optional[BreachNarrative] = None
        for b in breaches:
            if b.threat_id != threat_id:
                continue
            if int(b.tick) > int(breach_tick):
                continue
            if best is None or int(b.tick) > int(best.tick):
                best = b
        return best

    def _expand_upstream_controls(self, control_ids: List[str]) -> List[str]:
        """
        Optional: expand upstream (indirect) controls via network relationships, if available.
        """
        # Config-driven (0 disables expansion). No hard-coded defaults.
        depth = int(_require("narrative.root_cause_upstream_depth"))

        if depth <= 0:
            return control_ids

        net = getattr(self.model, "network", None)
        if net is None or not hasattr(net, "get_upstream_controls_ids"):
            return control_ids

        expanded: List[str] = list(control_ids)
        seen: Set[str] = set(control_ids)

        for cid in list(control_ids):
            try:
                ups = net.get_upstream_controls_ids(cid, max_depth=depth)  # type: ignore[attr-defined]
                for u in ups or []:
                    un = _norm_id(u)
                    if un and un not in seen:
                        seen.add(un)
                        expanded.append(un)
            except Exception:
                continue

        return expanded

    def _identify_root_variance_events(
        self,
        tech_asset_id: str,
        threat_id: str,
        failed_controls: List[str],
        variant_controls: List[str],
        breach_tick: int,
    ) -> Tuple[List[str], List[str]]:
        """Identify variance events that causally contributed to this breach.

        Returns:
          (root_causes, relevant_controls)

        root_causes entries are "CONTROL@tick" markers for *actual* variance
        events that preceded the breach.  A control that was beaten at full
        intended efficacy is NOT a root cause — the threat simply exceeded
        defenses.  Only controls that were actually *variant* (degraded)
        at breach time, or that had prior variance events contributing to
        a weakened posture, are considered root causes.

        Special markers:
          - ``MISSING_LEC@tick`` — no LEC existed in the protection path.
        """
        _ = tech_asset_id  # currently unused, kept for future expansions / debugging
        _ = threat_id      # currently unused, kept for future expansions / debugging

        root_causes: List[str] = []

        # missing LEC is causal
        if "MISSING_LEC" in (failed_controls or []) or "MISSING_LEC" in (variant_controls or []):
            root_causes.append(f"MISSING_LEC@{int(breach_tick)}")

        # Controls relevant at breach time: start with variant controls (most
        # directly causal), then add failed controls for upstream expansion.
        relevant_controls: List[str] = []
        seen: Set[str] = set()

        for c in (variant_controls or []):
            if c and c not in seen and c != "MISSING_LEC":
                seen.add(c)
                relevant_controls.append(c)
        for c in (failed_controls or []):
            if c and c not in seen and c != "MISSING_LEC":
                seen.add(c)
                relevant_controls.append(c)

        # optional upstream expansion
        relevant_controls = self._expand_upstream_controls(relevant_controls)

        # Root causes: actual variance events that preceded the breach.
        # ONLY include variance events for controls that were *variant*
        # (degraded) at breach time.  A control that was beaten at full
        # intended efficacy is NOT a root cause — the threat simply
        # exceeded defenses.  Prior variance events for a control that
        # has since been remediated and is now at full strength are not
        # causal for this particular breach.
        variant_set = set(variant_controls or [])

        for control_id in relevant_controls:
            # Skip controls that were at full intended efficacy at breach
            if control_id not in variant_set:
                continue

            variances = self.variance_by_control.get(control_id, [])

            for v in variances:
                if int(v.tick) <= int(breach_tick):
                    root_causes.append(f"{control_id}@{v.tick}")

        return root_causes, relevant_controls

    # ---------------- Breach causation detail helpers ----------------

    def _build_control_variance_detail(
        self,
        per_control_detail: List[Dict[str, Any]],
        variant_controls: List[str],
        breach_tick: int,
    ) -> List[Dict[str, Any]]:
        """Enrich per-control detail with variance type for each control.

        For each control in the protection path, look up the most recent
        variance event (at or before breach time) and attach the variance
        source (intrinsic/extrinsic), cause, and degradation amount.
        Controls at full intended efficacy get ``variance_source: "none"``.
        """
        if not per_control_detail:
            return []

        variant_set = set(variant_controls or [])
        result: List[Dict[str, Any]] = []

        seen_ids: set = set()
        for ctrl in per_control_detail:
            ctrl_id = ctrl.get("control_id", "")
            seen_ids.add(ctrl_id)
            entry = dict(ctrl)  # shallow copy

            if ctrl_id in variant_set:
                # Find most recent variance event for this control at/before breach
                variances = self.variance_by_control.get(ctrl_id, [])
                latest_var: Optional[VarianceNarrative] = None
                for v in variances:
                    if v.tick <= breach_tick:
                        if latest_var is None or v.tick > latest_var.tick:
                            latest_var = v

                if latest_var is not None:
                    entry["variance_type"] = latest_var.change_type
                    entry["variance_source"] = latest_var.variance_source
                    entry["variance_cause"] = latest_var.cause
                    entry["variance_tick"] = latest_var.tick
                    entry["pre_variance_efficacy"] = latest_var.intended_efficacy
                    entry["variant_efficacy"] = latest_var.variant_efficacy
                    entry["efficacy_degradation"] = round(
                        latest_var.intended_efficacy - latest_var.variant_efficacy, 4
                    )
                else:
                    entry["variance_source"] = "unknown"
            else:
                entry["variance_source"] = "none"

            result.append(entry)

        # Include variant controls not in per_control_detail (e.g., time-based
        # detection/recovery LECs excluded from resistance but still degraded)
        for vc in (variant_controls or []):
            if vc in seen_ids:
                continue
            variances = self.variance_by_control.get(vc, [])
            latest_var = None
            for v in variances:
                if v.tick <= breach_tick:
                    if latest_var is None or v.tick > latest_var.tick:
                        latest_var = v
            if latest_var is not None:
                is_time_based = (
                    latest_var.intended_efficacy > 1
                    or latest_var.variant_efficacy > 1
                )
                entry = {
                    "control_id": vc,
                    "stage": "detection" if is_time_based else "resistance",
                    "state": "variant",
                    "sampled_efficacy": latest_var.variant_efficacy,
                    "intended_efficacy": latest_var.intended_efficacy,
                    "behavior": "sample_time_interval" if is_time_based else "unknown",
                    "variance_type": latest_var.change_type,
                    "variance_source": latest_var.variance_source,
                    "variance_cause": latest_var.cause,
                    "variance_tick": latest_var.tick,
                    "pre_variance_efficacy": latest_var.intended_efficacy,
                    "variant_efficacy": latest_var.variant_efficacy,
                    "efficacy_degradation": round(
                        latest_var.intended_efficacy - latest_var.variant_efficacy, 4
                    ),
                }
                result.append(entry)

        return result

    def _generate_causation_text(
        self,
        breach_category: str,
        threat_sophistication: float,
        breach_mechanics: Dict[str, Any],
        control_variance_detail: List[Dict[str, Any]],
        variant_controls: List[str],
    ) -> str:
        """Generate causation narrative with numbers.

        Returns a concise explanation of *why* the breach happened, including
        the defense-in-depth math (combined RS, susceptibility formula, draw).
        """
        if breach_category == "missing_controls":
            return "No loss-event-prevention controls in the protection path."

        combined_rs = breach_mechanics.get("combined_rs")
        susceptibility = breach_mechanics.get("susceptibility")
        draw = breach_mechanics.get("draw_value")
        soph = breach_mechanics.get("threat_sophistication", threat_sophistication)

        # Build the defense math string
        math_parts: List[str] = []
        if combined_rs is not None:
            math_parts.append(f"RS={combined_rs:.3f}")
        if susceptibility is not None:
            math_parts.append(f"P(breach)={susceptibility:.3f}")
        if draw is not None and susceptibility is not None:
            math_parts.append(f"draw={draw:.3f} < {susceptibility:.3f}")
        math_str = ", ".join(math_parts) if math_parts else "no resistance math available"

        if breach_category == "threat_exceeded":
            # All controls at baseline efficacy; threat sophistication exceeded combined RS
            resistance_ctrls = [
                c for c in control_variance_detail if c.get("stage") == "resistance"
            ]
            eff_list = ", ".join(
                f"{c.get('control_id', '?')}={c.get('sampled_efficacy', 0):.2f}"
                for c in resistance_ctrls
            )
            dsc_parts = self._format_dsc_details(control_variance_detail)
            return (
                f"Threat (S={soph:.3f}) beat all controls at baseline efficacy"
                f"{(' [' + eff_list + ']') if eff_list else ''}. "
                f"Defense math: {math_str}."
                f"{dsc_parts}"
            )

        if breach_category == "variance_enabled":
            # Identify variance sources
            variant_detail = [
                c for c in control_variance_detail
                if c.get("control_id") in set(variant_controls or [])
            ]
            sources = set(c.get("variance_source", "unknown") for c in variant_detail)

            if "extrinsic" in sources and "intrinsic" in sources:
                source_text = "both intrinsic drift and extrinsic threat landscape changes"
            elif "extrinsic" in sources:
                source_text = "extrinsic threat landscape change (zero-day/CVE)"
            elif "intrinsic" in sources:
                # Distinguish sub-types
                causes = set(c.get("variance_cause", "") for c in variant_detail)
                if "personnel_error" in causes and "control_drift" in causes:
                    source_text = "intrinsic variance (control drift + personnel error)"
                elif "personnel_error" in causes:
                    source_text = "intrinsic variance (personnel error)"
                else:
                    source_text = "intrinsic variance (control drift)"
            else:
                source_text = "variance"

            # Show which controls degraded and by how much
            degradation_parts = []
            seen_ids: set = set()
            for c in variant_detail:
                cid = c.get("control_id", "?")
                seen_ids.add(cid)
                pre = c.get("pre_variance_efficacy")
                post = c.get("sampled_efficacy", c.get("variant_efficacy"))
                if pre is not None and post is not None:
                    degradation_parts.append(f"{cid}: {pre:.2f}->{post:.2f}")
                else:
                    degradation_parts.append(cid)
            # Include variant controls not in resistance detail (e.g., time-based
            # detection/recovery LECs that affect loss severity, not P(breach))
            for vc in (variant_controls or []):
                if vc in seen_ids:
                    continue
                variances = self.variance_by_control.get(vc, [])
                latest_var = None
                for v in variances:
                    if latest_var is None or v.tick > latest_var.tick:
                        latest_var = v
                if latest_var is not None:
                    pre_val = latest_var.intended_efficacy
                    post_val = latest_var.variant_efficacy
                    # Time-based controls have values > 1 (hours)
                    if pre_val > 1 or post_val > 1:
                        degradation_parts.append(
                            f"{vc}: {pre_val:.0f}h->{post_val:.0f}h (detection/response)"
                        )
                    else:
                        degradation_parts.append(
                            f"{vc}: {pre_val:.2f}->{post_val:.2f}"
                        )
                else:
                    degradation_parts.append(vc)
            degradation_str = ", ".join(degradation_parts)

            # Include DSC decision details for human-actor controls
            dsc_parts = self._format_dsc_details(control_variance_detail)

            return (
                f"Breach enabled by {source_text}. "
                f"{len(variant_controls)} control(s) degraded [{degradation_str}]. "
                f"Defense math: {math_str}."
                f"{dsc_parts}"
            )

        return f"Breach category: {breach_category}."

    def _format_dsc_details(
        self, control_variance_detail: List[Dict[str, Any]]
    ) -> str:
        """Format DSC decision chain details for controls with dsc_detail."""
        parts: List[str] = []
        for c in control_variance_detail:
            dsc = c.get("dsc_detail")
            if not dsc:
                continue
            cid = c.get("control_id", "?")
            aligned = dsc.get("aligned", None)
            p_mis = dsc.get("p_misaligned", None)
            dims = dsc.get("dimensions", {})
            dim_strs = []
            for dim_name, dim_result in dims.items():
                final = dim_result.get("final_success")
                dim_strs.append(f"{dim_name}={'pass' if final else 'fail'}")
            outcome = "aligned" if aligned else "misaligned"
            p_str = f"p_misaligned={p_mis:.3f}" if p_mis is not None else ""
            dim_str = ", ".join(dim_strs) if dim_strs else "no dimensions"
            residual = c.get("dsc_residual")
            residual_str = f", residual={residual:.0%}" if residual is not None else ""
            parts.append(f" DSC({cid}): {outcome} ({p_str}, {dim_str}{residual_str})")
        if not parts:
            return ""
        return " |" + " |".join(parts)

    def _classify_loss_driver(self, loss_event_data: dict) -> str:
        """Classify the loss driver for this loss event."""
        detected = loss_event_data.get("detected", True)
        if not detected:
            return "detection_failure"

        variant_controls = loss_event_data.get("variant_controls") or []
        failed_controls = loss_event_data.get("failed_controls") or []

        # Check if any failed controls were in the remediation queue
        queue = getattr(self.model, "remediation", None)
        if queue and hasattr(queue, "queue"):
            queued_ids = {item.control_id for item in queue.queue}
            in_progress_ids = set(queue.in_progress.keys()) if hasattr(queue, "in_progress") else set()
            if any(c in queued_ids or c in in_progress_ids for c in variant_controls):
                return "resource_constrained"

        if variant_controls:
            return "control_degradation"

        if not failed_controls:
            return "design_weakness"

        return "design_weakness"

    # ---------------- Analysis helpers ----------------

    def get_linchpin_controls(self, min_impact_count: int = 2) -> Dict[str, int]:
        """
        Identify linchpin controls - controls whose variance contributed to multiple loss events.

        This includes:
        1. LECs that failed during breach (directly in the attack path)
        2. VMCs that were variant and contributed via any cascade path:
           - Detection: monitoring VMC variant when LEC became variant
           - Prevention: variance-prevention VMC variant when LEC drifted
           - Threat intel: intel VMC variant at breach time (slower detection)
           - Correction: implementing/treatment-selection VMC blocked or
             delayed remediation during the LEC's variant window

        A true linchpin is a control whose failure
        creates cascading effects across multiple loss events.

        Note: For cross-run linchpin analysis (comparing outcomes across 100 iterations),
        use the batch analysis tools which aggregate narratives across runs.
        """
        control_impact_count = defaultdict(int)

        for loss in self.loss_events:
            contributing_controls = set()

            # 1. Controls from root_variance_events (LECs that were variant)
            for root_cause in loss.root_variance_events:
                if "@" in root_cause:
                    control_id = root_cause.split("@")[0]
                    contributing_controls.add(control_id)

            # 2. Find VMCs that were variant when LECs became variant
            #    These are the "hidden linchpins" - their failure allowed LEC variance to persist
            vmc_linchpins = self._find_variant_vmcs_at_lec_variance(loss)
            contributing_controls.update(vmc_linchpins)

            for control_id in contributing_controls:
                control_impact_count[control_id] += 1

        return {
            control_id: count
            for control_id, count in control_impact_count.items()
            if count >= min_impact_count
        }

    def _find_variant_vmcs_at_lec_variance(self, loss: LossEventNarrative) -> Set[str]:
        """Find VMC IDs that were variant when LECs in this loss event became variant."""
        return set(d["vmc_id"] for d in self._find_variant_vmcs_detail(loss))

    def _find_variant_vmcs_detail(self, loss: LossEventNarrative) -> List[Dict[str, Any]]:
        """
        Find VMCs that were variant when LECs in this loss event became variant,
        with full variance detail (cause, efficacy degradation, tick, cascade path).

        Traces four cascade paths:
        1. Detection: VMC_MONITORS — VMC couldn't detect LEC variance
        2. Prevention: VMC_REDUCES_VAR_PROB / VMC_REDUCES_CHANGE_FREQ — VMC
           couldn't prevent LEC from entering variant state
        3. Threat intel: VMC_THREAT_INTEL — VMC couldn't reduce detection time
           at breach (checked at breach_tick, not lec_variance_tick)
        4. Correction: VMC_IMPLEMENTS_REMEDIATION / VMC_SELECTS_TREATMENT —
           VMC blocked or delayed remediation (from recorded remediation events)

        Each result is tagged with a ``cascade_path`` field identifying the
        failure mode.  The temporal overlap logic (was the VMC variant at the
        relevant moment, and had it not recovered?) is shared across all paths.
        """
        result: List[Dict[str, Any]] = []
        seen_vmcs: Set[str] = set()

        net = getattr(self.model, "network", None)
        if net is None:
            return result

        # --- Helper: check temporal overlap for a VMC at a reference tick ---
        def _check_vmc_variant_at(vmc, reference_tick: int, cascade_path: str) -> None:
            vmc_id = str(getattr(vmc, "unique_id", ""))
            if not vmc_id or vmc_id in seen_vmcs:
                return

            vmc_variances = self.variance_by_control.get(vmc_id, [])
            vmc_recoveries = self.recovery_by_control.get(vmc_id, [])
            for vmc_var in vmc_variances:
                if vmc_var.tick > reference_tick:
                    continue
                recovered_before = any(
                    r.tick > vmc_var.tick and r.tick <= reference_tick
                    for r in vmc_recoveries
                )
                if not recovered_before:
                    seen_vmcs.add(vmc_id)
                    result.append({
                        "vmc_id": vmc_id,
                        "cascade_path": cascade_path,
                        "variance_tick": vmc_var.tick,
                        "variance_source": vmc_var.variance_source,
                        "cause": vmc_var.cause,
                        "change_type": vmc_var.change_type,
                        "intended_efficacy": vmc_var.intended_efficacy,
                        "variant_efficacy": vmc_var.variant_efficacy,
                    })
                    break

        def _safe_get(method_name: str, control_id: str) -> list:
            try:
                fn = getattr(net, method_name, None)
                return fn(control_id) or [] if fn else []
            except Exception:
                return []

        # --- Per-LEC cascade paths (detection + prevention) ---
        for lec_root in loss.root_variance_events:
            if "@" not in lec_root:
                continue
            lec_id, tick_str = lec_root.split("@", 1)
            if not lec_id.upper().startswith("LEC"):
                continue
            try:
                lec_variance_tick = int(tick_str)
            except ValueError:
                continue

            # 1. Detection: was the monitoring VMC variant when the LEC became variant?
            for vmc in _safe_get("get_monitoring_vmcs", lec_id):
                _check_vmc_variant_at(vmc, lec_variance_tick, "detection")

            # 2. Prevention: was the prevention VMC variant when the LEC's drift fired?
            for vmc in _safe_get("get_vmc_reduce_prob_controls", lec_id):
                _check_vmc_variant_at(vmc, lec_variance_tick, "prevention")
            for vmc in _safe_get("get_vmc_reduce_freq_controls", lec_id):
                _check_vmc_variant_at(vmc, lec_variance_tick, "prevention")

        # --- Breach-time cascade path (threat intel) ---
        # Threat-intel VMCs affect detection time at breach, not at LEC variance.
        # Check all LECs involved in this loss event for linked threat-intel VMCs.
        breach_tick = int(loss.breach_tick)
        checked_lecs: Set[str] = set()
        for lec_root in loss.root_variance_events:
            if "@" not in lec_root:
                continue
            lec_id = lec_root.split("@", 1)[0]
            if lec_id in checked_lecs or not lec_id.upper().startswith("LEC"):
                continue
            checked_lecs.add(lec_id)
            for vmc in _safe_get("get_threat_intel_vmcs", lec_id):
                _check_vmc_variant_at(vmc, breach_tick, "threat_intel")

        # --- Correction cascade path (implementing + treatment selection) ---
        # Use recorded remediation events: if a variant LEC had its remediation
        # blocked or demoted between lec_variance_tick and breach_tick, the
        # blocking VMC contributed to the loss by extending the variant window.
        for lec_root in loss.root_variance_events:
            if "@" not in lec_root:
                continue
            lec_id, tick_str = lec_root.split("@", 1)
            if not lec_id.upper().startswith("LEC"):
                continue
            try:
                lec_variance_tick = int(tick_str)
            except ValueError:
                continue

            for rem_event in self.remediation_by_control.get(lec_id, []):
                if rem_event.event_type not in ("blocked", "demoted"):
                    continue
                # Only count events during the LEC's variant window before breach
                if rem_event.tick < lec_variance_tick or rem_event.tick > breach_tick:
                    continue
                for blocking_vmc_id in rem_event.blocking_vmc_ids:
                    if not blocking_vmc_id or blocking_vmc_id in seen_vmcs:
                        continue
                    # Look up the VMC's variance detail at the blocking tick
                    vmc_variances = self.variance_by_control.get(blocking_vmc_id, [])
                    for vmc_var in vmc_variances:
                        if vmc_var.tick > rem_event.tick:
                            continue
                        vmc_recoveries = self.recovery_by_control.get(blocking_vmc_id, [])
                        recovered_before = any(
                            r.tick > vmc_var.tick and r.tick <= rem_event.tick
                            for r in vmc_recoveries
                        )
                        if not recovered_before:
                            seen_vmcs.add(blocking_vmc_id)
                            result.append({
                                "vmc_id": blocking_vmc_id,
                                "cascade_path": "correction",
                                "variance_tick": vmc_var.tick,
                                "variance_source": vmc_var.variance_source,
                                "cause": vmc_var.cause,
                                "change_type": vmc_var.change_type,
                                "intended_efficacy": vmc_var.intended_efficacy,
                                "variant_efficacy": vmc_var.variant_efficacy,
                            })
                            break

        return result

    def get_cascade_chains(self) -> List[Dict[str, Any]]:
        cascades: List[Dict[str, Any]] = []

        for loss in self.loss_events:
            breaches = self.breach_by_tech_asset.get(loss.tech_asset_id, [])

            # Find most recent breach before loss (same threat)
            relevant_breach = None
            for breach in breaches:
                if breach.tick <= loss.tick and breach.threat_id == loss.threat_id:
                    if relevant_breach is None or breach.tick > relevant_breach.tick:
                        relevant_breach = breach

            variance_narratives = []
            for root_cause in loss.root_variance_events:
                if "@" in root_cause:
                    control_id, tick_str = root_cause.split("@")
                    tick = int(tick_str)

                    for variance in self.variance_by_control.get(control_id, []):
                        if variance.tick == tick:
                            variance_narratives.append(variance)
                            break

            cascade = {
                "loss_event": loss,
                "breach_event": relevant_breach,
                "variance_events": variance_narratives,
                "total_loss": loss.total_loss,
                "cascade_duration": loss.tick - min(v.tick for v in variance_narratives) if variance_narratives else 0,
            }
            cascades.append(cascade)

        return cascades

    # ---------------- Export ----------------

    def export_narratives(self) -> Dict[str, Any]:
        linchpins = self.get_linchpin_controls()
        cascades = self.get_cascade_chains()

        result = {
            "variance_events": [
                {
                    "control_id": v.control_id,
                    "tick": v.tick,
                    "change_type": v.change_type,
                    "variance_source": v.variance_source,
                    "intended_efficacy": v.intended_efficacy,
                    "variant_efficacy": v.variant_efficacy,
                    "cause": v.cause,
                }
                for v in self.variance_events
            ],
            "recovery_events": [
                {
                    "control_id": r.control_id,
                    "tick": r.tick,
                    "restored_efficacy": r.restored_efficacy,
                }
                for r in self.recovery_events
            ],
            "remediation_events": [
                {
                    "control_id": rem.control_id,
                    "tick": rem.tick,
                    "event_type": rem.event_type,
                    "hours": rem.hours,
                    "blocking_vmc_ids": list(rem.blocking_vmc_ids),
                    "reason": rem.reason,
                }
                for rem in self.remediation_events
                if rem.event_type in ("blocked", "demoted")
            ],
            "breach_events": [
                {
                    "threat_id": b.threat_id,
                    "tech_asset_id": b.tech_asset_id,
                    "tick": b.tick,
                    "threat_sophistication": b.threat_sophistication,
                    "threat_origin": getattr(b, "threat_origin", "unknown"),
                    "failed_controls_count": len(b.failed_controls),
                    "variant_controls_count": len(b.variant_controls_at_breach),
                    "failed_controls": list(b.failed_controls),
                    "variant_controls_at_breach": list(b.variant_controls_at_breach),
                    "control_efficacies": dict(getattr(b, "control_efficacies", {})),
                    "breach_mechanics": dict(getattr(b, "breach_mechanics", {})),
                    "per_control_detail": list(getattr(b, "per_control_detail", [])),
                }
                for b in self.breach_events
            ],
            "loss_events": [
                {
                    "event_id": l.event_id,
                    "business_asset_id": l.business_asset_id,
                    "tech_asset_id": l.tech_asset_id,
                    "threat_id": l.threat_id,
                    "tick": l.tick,
                    "breach_tick": l.breach_tick,
                    "loss_time_hours": l.tick - l.breach_tick,  # computed from ticks
                    "total_loss": l.total_loss,
                    "primary_loss": l.primary_loss,
                    "secondary_loss": l.secondary_loss,
                    "asset_type": getattr(l, "asset_type", "unknown"),
                    "outage_hours": getattr(l, "outage_hours", None),
                    "threat_sophistication": getattr(l, "threat_sophistication", 0.0),
                    "root_causes_count": len(l.root_variance_events),
                    "failed_controls": list(l.failed_controls),
                    "variant_controls": list(l.variant_controls),
                    "control_efficacies_at_breach": dict(getattr(l, "control_efficacies_at_breach", {})),
                    "root_variance_events": list(l.root_variance_events),
                    "proximate_root_cause": getattr(l, "proximate_root_cause", None),
                    "breach_category": getattr(l, "breach_category", "unknown"),
                    # Enriched causation detail
                    "breach_mechanics": dict(getattr(l, "breach_mechanics", {})),
                    "control_variance_detail": list(getattr(l, "control_variance_detail", [])),
                    "causation_narrative": getattr(l, "causation_narrative", ""),
                    "variant_vmcs": list(self._find_variant_vmcs_at_lec_variance(l)),
                    "variant_vmcs_detail": self._find_variant_vmcs_detail(l),
                    "loss_driver": getattr(l, "loss_driver", "design_weakness"),
                }
                for l in self.loss_events
            ],
            "linchpin_controls": linchpins,
            "linchpin_analysis": {
                "description": "Controls whose variance contributed to multiple loss events. "
                               "Includes LECs that failed during breach AND VMCs that were variant "
                               "across four cascade paths: detection (monitoring VMC blind to LEC "
                               "variance), prevention (variance-prevention VMC degraded at drift), "
                               "threat intel (intel VMC degraded at breach, slowing detection), "
                               "and correction (implementing/treatment VMC blocked remediation).",
                "scope": "within_run",
                "note": "For cross-run analysis (identifying controls with high outcome variance "
                        "across 100 iterations), use batch analysis tools.",
                "controls": linchpins,
            },
            "total_cascades": len(cascades),
            "summary": {
                "total_variance_events": len(self.variance_events),
                "total_breaches": len(self.breach_events),
                "total_losses": len(self.loss_events),
                "total_loss_amount": sum(l.total_loss for l in self.loss_events),
                "linchpin_count": len(linchpins),
                # Breach category distribution — how many breaches were caused by
                # variance vs. threat capability vs. missing controls
                "breach_categories": {
                    "threat_exceeded": sum(
                        1 for l in self.loss_events
                        if getattr(l, "breach_category", "") == "threat_exceeded"
                    ),
                    "variance_enabled": sum(
                        1 for l in self.loss_events
                        if getattr(l, "breach_category", "") == "variance_enabled"
                    ),
                    "missing_controls": sum(
                        1 for l in self.loss_events
                        if getattr(l, "breach_category", "") == "missing_controls"
                    ),
                },
                # Cost tracking from model metrics
                "cumulative_capex": getattr(getattr(self.model, "metrics_state", None), "cumulative_capex", 0.0),
                "cumulative_opex": getattr(getattr(self.model, "metrics_state", None), "cumulative_opex", 0.0),
                # Risk management failure distribution
                "loss_drivers": {
                    "detection_failure": sum(
                        1 for l in self.loss_events
                        if getattr(l, "loss_driver", "") == "detection_failure"
                    ),
                    "resource_constrained": sum(
                        1 for l in self.loss_events
                        if getattr(l, "loss_driver", "") == "resource_constrained"
                    ),
                    "control_degradation": sum(
                        1 for l in self.loss_events
                        if getattr(l, "loss_driver", "") == "control_degradation"
                    ),
                    "design_weakness": sum(
                        1 for l in self.loss_events
                        if getattr(l, "loss_driver", "") == "design_weakness"
                    ),
                },
            },
            "cost_benefit_analysis": self._compute_cost_benefit_analysis(),
        }

        # ---- Personnel behavior feature status ----
        result["personnel_behavior"] = {
            "satisficing_active": bool(cfg.get("personnel_behavior.satisficing.strength", 0) > 0),
            "psychometric_perception_active": bool(
                cfg.get("personnel_behavior.feature_flags.enable_psychometric_perception", False)
            ),
        }

        # ---- Risk appetite assessment + KRI/KPI ----
        # Appended to the narrative export so the UI / downstream consumers
        # have a single payload with full causation + risk posture.
        try:
            result["risk_appetite_assessment"] = self._compute_risk_appetite()
            result["kris"] = self._compute_kris()
            result["kpis"] = self._compute_kpis()
        except Exception as exc:
            logger.warning("Could not compute risk appetite / KRI / KPI metrics: %s", exc)

        return result

    def _compute_cost_benefit_analysis(self) -> Dict[str, Any]:
        """
        Compute cost-benefit metrics for the simulation run.

        Metrics:
        - Total control costs (CapEx + cumulative OpEx)
        - Total realized losses
        - Breaches prevented (contacts - breaches that led to loss)
        - Estimated loss avoidance (breaches prevented × average loss per breach)
        - ROI indicators
        """
        metrics = getattr(self.model, "metrics_state", None)
        if metrics is None:
            return {"error": "No metrics available"}

        # Costs
        capex = getattr(metrics, "cumulative_capex", 0.0)
        opex = getattr(metrics, "cumulative_opex", 0.0)
        total_control_cost = capex + opex

        # Losses
        total_loss = sum(l.total_loss for l in self.loss_events)
        loss_event_count = len(self.loss_events)

        # Breach statistics
        total_breaches = len(self.breach_events)
        total_contacts = getattr(metrics, "total_contact_events", 0)

        # Calculate average loss per loss event (for estimation)
        avg_loss_per_event = total_loss / loss_event_count if loss_event_count > 0 else 0.0

        # Breaches that didn't result in loss events (orphan breaches or contained)
        # A breach only becomes a loss event if the tech asset hosts a business asset
        orphan_breaches = getattr(metrics, "orphan_breach_events", 0)

        # Contacts that were blocked (didn't become breaches)
        blocked_contacts = total_contacts - total_breaches if total_contacts > total_breaches else 0

        baseline_loss_per_breach = 1_500_000.0
        estimated_loss_if_uncontrolled = total_contacts * baseline_loss_per_breach * 0.1  # ~10% of contacts would breach without controls

        # More conservative estimate based on actual data
        if loss_event_count > 0 and total_breaches > 0:
            # Use actual loss rate from this run
            loss_rate = loss_event_count / total_breaches
            avg_loss = total_loss / loss_event_count
            estimated_avoided_loss = blocked_contacts * loss_rate * avg_loss
        else:
            # No losses occurred - estimate based on blocked contacts
            estimated_avoided_loss = blocked_contacts * baseline_loss_per_breach * 0.05

        # Cost per breach prevented
        cost_per_blocked = total_control_cost / blocked_contacts if blocked_contacts > 0 else None

        # Net position (negative = costs exceed losses, positive = losses exceed costs)
        net_position = total_loss - total_control_cost

        # ROI calculation (avoided loss - control cost) / control cost
        # This is speculative since we don't know counterfactual
        roi_estimate = (estimated_avoided_loss - total_control_cost) / total_control_cost if total_control_cost > 0 else None

        # Breaches that hit assets WITH business assets (could cause loss)
        breaches_with_ba = total_breaches - orphan_breaches

        # Average BAs per breached TA — explains why loss_events > breaches.
        # Each breach on a TA hosting N business assets produces N loss events.
        ba_per_breach: Dict[tuple, set] = {}
        for le in self.loss_events:
            key = (le.tech_asset_id, le.breach_tick)
            if key not in ba_per_breach:
                ba_per_breach[key] = set()
            ba_per_breach[key].add(le.business_asset_id)
        avg_bas_per_breached_ta = (
            sum(len(bas) for bas in ba_per_breach.values()) / len(ba_per_breach)
            if ba_per_breach else 0.0
        )

        loss_events_per_breach = loss_event_count / breaches_with_ba if breaches_with_ba > 0 else 0.0

        return {
            "costs": {
                "capex": capex,
                "cumulative_opex": opex,
                "total_control_cost": total_control_cost,
            },
            "losses": {
                "total_realized_loss": total_loss,
                "loss_event_count": loss_event_count,
                "avg_loss_per_event": avg_loss_per_event,
            },
            "effectiveness": {
                "total_contacts": total_contacts,
                "total_breaches": total_breaches,
                "breaches_with_business_assets": breaches_with_ba,
                "orphan_breaches": orphan_breaches,
                "blocked_contacts": blocked_contacts,
                "block_rate": blocked_contacts / total_contacts if total_contacts > 0 else 0.0,
                "breach_to_loss_rate": loss_events_per_breach,
                "loss_events_per_breach": loss_events_per_breach,
                "avg_business_assets_per_breached_ta": avg_bas_per_breached_ta,
            },
            "estimates": {
                "estimated_avoided_loss": estimated_avoided_loss,
                "cost_per_contact_blocked": cost_per_blocked,
                "net_position": net_position,
                "roi_estimate": roi_estimate,
                "note": (
                    f"Est. avoided loss = blocked contacts ({blocked_contacts:,}) "
                    f"\u00d7 loss events per breach ({loss_events_per_breach:.2f}) "
                    f"\u00d7 avg loss per event (${avg_loss_per_event:,.0f}). "
                    f"Each breach can create multiple loss events because a single tech "
                    f"asset may host multiple business assets "
                    f"(avg {avg_bas_per_breached_ta:.1f} BAs per breached TA). "
                    f"Orphan breaches hit tech assets with no business assets and cause no loss."
                ),
            },
        }

    # ---- Risk appetite + KRI/KPI helpers ----

    def _get_total_ticks(self) -> int:
        """Return the current simulation tick count."""
        sched = getattr(self.model, "schedule", None)
        return int(getattr(sched, "steps", 0)) if sched else 0

    def _compute_risk_appetite(self) -> Dict[str, Any]:
        """Compute risk appetite assessment for this run.

        Delegates to :class:`~src.analysis.metrics.RiskAppetiteAssessment`.
        """
        from .metrics import RiskAppetiteAssessment

        ms = getattr(self.model, "metrics_state", None)
        if ms is None:
            return {"error": "No metrics state available"}

        total_ticks = self._get_total_ticks()
        assessment = RiskAppetiteAssessment()
        return assessment.assess_single_run(ms, total_ticks)

    def _compute_kris(self) -> Dict[str, Any]:
        """Compute Key Risk Indicators."""
        from .metrics import compute_kris

        ms = getattr(self.model, "metrics_state", None)
        if ms is None:
            return {"error": "No metrics state available"}

        return compute_kris(ms, self._get_total_ticks())

    def _compute_kpis(self) -> Dict[str, Any]:
        """Compute Key Performance Indicators."""
        from .metrics import compute_kpis

        return compute_kpis(self.model, self._get_total_ticks())