# src/processing/loss_event.py
"""
Loss event processing.

- Loss time = detection + termination + monitoring backtrack
- Loss magnitude:
    * Information assets: empirical breach sampler (IRIS 2025 distributions)
    * Process assets: driven by outage duration, then loss table lookup (outage)
- Apply loss reduction controls to net loss
- Record causation using breach_tick (not loss_tick)

Design notes:
- This module should not do API/UI transformations.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..config import get_config
from ..data.loss_tables import LossMagnitudeTables, EmpiricalBreachSampler, EmpiricalOutageSampler

logger = logging.getLogger(__name__)
cfg = get_config()

# ---------------------------------------------------------------------------
# Stage-gated detection model
# ---------------------------------------------------------------------------
# When enabled, attacks progress through multiple stages with independent
# detection opportunities at each.  Earlier detection produces lower losses.
# Disabled by default — the classic single-review Bernoulli trial is used.

ATTACK_STAGES = [
    {"name": "initial_access", "weight": 0.15},   # Loss multiplier if detected here
    {"name": "foothold", "weight": 0.35},
    {"name": "lateral_movement", "weight": 0.65},
    {"name": "exfiltration", "weight": 1.0},       # Full impact
]

OUTCOME_CLASSES = {
    "early": {"stages": [0, 1], "loss_multiplier": 0.25},    # Detected at initial_access or foothold
    "mid": {"stages": [2], "loss_multiplier": 0.65},          # Detected at lateral_movement
    "late": {"stages": [3], "loss_multiplier": 1.0},          # Detected at exfiltration
    "full_impact": {"stages": [], "loss_multiplier": 1.0},    # Never detected
}


def _require(key_path: str) -> Any:
    val = cfg.get(key_path, None)
    if val is None:
        raise KeyError(
            f"Missing required config key '{key_path}'. "
            f"Add it to inputs/model_config.yaml."
        )
    return val


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else float(x)


def _norm_type(x: Any) -> str:
    return str(x or "").strip().lower().replace(" ", "_")


@dataclass
class PendingLoss:
    due_tick: int
    breach_tick: int
    threat_id: str
    tech_asset_id: str
    business_asset_id: str
    asset_type: str  # "information" | "process"
    loss_time_hours: float
    outage_hours: Optional[float] = None
    failed_controls: Optional[List[str]] = None
    variant_controls: Optional[List[str]] = None
    # Threat-specific loss parameters from JSON
    threat_velocity_hours: Optional[float] = None
    threat_loss_rate_exp: Optional[float] = None
    # Whether the breach was detected (no detection → no response)
    detected: bool = True
    # Stage-gated detection: name of the stage where detection occurred (None = classic mode)
    detection_stage: Optional[str] = None


class LossEventProcessor:
    """
    Schedules and realizes losses after breaches.

    Public contract expected by ContactProcessor:
      - schedule_loss_events_for_breach(...)
      - step() called each tick (to realize due losses)
    """

    def __init__(self, model):
        self.model = model
        self.pending: List[PendingLoss] = []

        # Per-entity stream isolation for marginal value analysis (see STREAM_ISOLATION.md)
        self._streams = getattr(model, "streams", None)

        # Deterministic numpy RNG seeded from mesa RNG (or isolated loss stream).
        # Kept for complex distribution sampling (gross loss). Bernoulli trials
        # now use per-entity Python RNG via _entity_rng() for stream isolation.
        seed = int(self._draw_seed())
        self._np_rng = np.random.RandomState(seed)

        # Required loss config
        self._use_tables = bool(_require("loss.use_tables"))
        self._primary_ratio = float(_require("loss.primary_ratio"))
        self._primary_ratio = _clamp(self._primary_ratio, 0.0, 1.0)

        # Secondary Loss Event Frequency (SLEF) - fraction of primary loss events
        # that also incur secondary losses. In FAIR, SLEF is a fraction of LEF.
        self._slef = float(_require("loss.secondary_loss_event_frequency"))
        self._slef = _clamp(self._slef, 0.0, 1.0)

        # Timing config (default profile)
        self._timing = {
            "monitoring_backtrack_hours": float(_require("loss_events.default.monitoring_backtrack_hours")),
            "detection_time_dist": dict(_require("loss_events.default.detection_time_dist")),
            "termination_time_dist": dict(_require("loss_events.default.termination_time_dist")),
        }

        # Default Beta-PERT confidence used when a time distribution omits it
        # (no hard-coded defaults; this must be provided in YAML).
        self._beta_pert_default_confidence = float(_require("loss_events.default.beta_pert_confidence"))

        # Recovery config (non-timing profiles live at loss_events.*)
        self._process_recovery = dict(_require("loss_events.process_recovery"))

        # Efficacy->time modifiers + loss reduction
        self._eff_to_time = dict(_require("loss_events.efficacy_to_time"))
        self._loss_reduction = dict(_require("loss_events.loss_reduction"))

        # -----------------------------------------------------------------
        # Detection AND gate
        # -----------------------------------------------------------------
        # FAIR-CAM mandates that detection requires ALL THREE
        # subfunctions to succeed: Visibility AND Monitoring AND Recognition.
        #
        # - Visibility LECs: probability-based [0-1] — "can you see evidence?"
        # - Monitoring LECs: time-based (hours) — "how often do you look?"
        # - Recognition LECs: probability-based [0-1] — "can you tell it's bad?"
        #
        # If any subfunction has no operational (normal-state) control,
        # detection fails entirely and the breach goes undetected for a
        # much longer period (undetected_time_hours).
        #
        # When all three subfunctions are present, detection probability is
        # P(detect) = best_vis_eff × best_recog_eff (AND of probability
        # subfunctions), with monitoring providing the time component.
        dag_cfg = cfg.get("loss_events.detection_and_gate", {}) or {}
        self._detection_and_enabled = bool(dag_cfg.get("enabled", True))
        self._undetected_time_hours = float(dag_cfg.get("undetected_time_hours", 720.0))
        self._use_probability_gate = bool(dag_cfg.get("use_probability_gate", True))
        self._min_detection_prob = float(dag_cfg.get("min_detection_probability", 0.05))

        # Response concurrency factor:
        # T_response = T_containment + T_recovery - alpha * min(T_containment, T_recovery)
        # alpha=0 (default) = sequential, alpha=1 = fully parallel.
        self._response_concurrency_alpha = float(
            cfg.get("loss_events.response_concurrency_alpha", 0.0)
        )
        self._response_concurrency_alpha = _clamp(self._response_concurrency_alpha, 0.0, 1.0)

        # Strict AND gate: when true, missing subfunctions FAIL detection.
        # When false (legacy), missing subfunctions are treated as "ungated" (pass automatically).
        self._require_all_subfunctions = bool(dag_cfg.get("require_all_subfunctions", True))

        # Stage-gated detection model
        stage_cfg = dag_cfg.get("stage_gated", {}) or {}
        self._stage_gated_enabled = bool(stage_cfg.get("enabled", False))
        self._reviews_per_stage = int(stage_cfg.get("reviews_per_stage", 1))

        # Threat intel multiplier: VMC_THREAT_INTEL relationships reduce detection time

        # Load loss tables if enabled
        self.tables: Optional[LossMagnitudeTables] = None
        self._empirical_breach: Optional[EmpiricalBreachSampler] = None
        self._empirical_outage: Optional[EmpiricalOutageSampler] = None
        if self._use_tables:
            # Information assets: empirical breach sampler (required)
            empirical_json = cfg.get("loss.tables.empirical_breach_json", None)
            if not empirical_json:
                raise ValueError(
                    "loss.tables.empirical_breach_json is required when loss.use_tables=true. "
                    "Set loss.tables.empirical_breach_json to the IRIS 2025 calibration file."
                )
            self._empirical_breach = EmpiricalBreachSampler(str(empirical_json))
            logger.info("LossEventProcessor: using empirical breach sampler")

            # Process assets: empirical outage sampler
            outage_json = cfg.get("loss.tables.empirical_outage_json", None)
            if outage_json:
                self._empirical_outage = EmpiricalOutageSampler(str(outage_json))
                logger.info("LossEventProcessor: using empirical outage sampler")

            out_csv = cfg.get("loss.tables.outage_csv", None)
            if out_csv and not self._empirical_outage:
                self.tables = LossMagnitudeTables(outage_table_path=str(out_csv))
                logger.info("LossEventProcessor: outage table=%s (legacy CSV)", out_csv)

        # Scenario metadata for empirical breach lookup
        self._scenario_type = cfg.get("loss.tables.scenario_metadata.scenario_type", None)
        self._sector = cfg.get("loss.tables.scenario_metadata.sector", None)
        self._revenue_bucket = cfg.get("loss.tables.scenario_metadata.revenue_bucket", None)

    def _entity_rng(self, *keys: str):
        """Isolated RNG keyed to the given entity identifiers for marginal value analysis."""
        if self._streams is not None:
            return self._streams.get(":".join(str(k) for k in keys))
        return self.model.random

    # ---------------------------------------------------------------------
    # Scheduling API (called by ContactProcessor on breach)
    # ---------------------------------------------------------------------

    def schedule_loss_events_for_breach(
        self,
        threat_id: str,
        tech_asset_id: str,
        breach_tick: int,
        failed_controls: Optional[List[str]] = None,
        variant_controls: Optional[List[str]] = None,
        threat_agent: Any = None,
    ) -> None:
        """
        For each business asset hosted by tech_asset_id, schedule a pending loss.

        If no business assets exist (orphan breach), this processor does nothing;
        orphan breach handling is tracked in MetricsState elsewhere.

        Args:
            threat_agent: Optional ThreatAgent for velocity/exponent params from JSON.
        """
        bas = []
        try:
            bas = self.model.network.get_business_assets(tech_asset_id) if hasattr(self.model, "network") else []
        except Exception:
            bas = []

        if not bas:
            return

        # Extract threat-specific loss parameters if provided
        threat_velocity = None
        threat_exp = None
        if threat_agent is not None:
            threat_velocity = getattr(threat_agent, "mean_velocity_hours", None)
            threat_exp = getattr(threat_agent, "exp_loss_rate", None)

        for ba in bas:
            ba_id = str(getattr(ba, "unique_id", "")).strip()
            if not ba_id:
                continue

            asset_type = _norm_type(getattr(ba, "asset_type", None) or ba.params.get("Type") if hasattr(ba, "params") else None)
            if asset_type not in ("information", "process"):
                # Force the taxonomy via config/data upstream; don't silently guess.
                raise ValueError(
                    f"BusinessAsset {ba_id} has unsupported asset_type='{asset_type}'. "
                    f"Expected 'information' or 'process' from scenario inputs."
                )

            loss_result = self._compute_loss_time_hours(
                tech_asset_id=tech_asset_id,
                business_asset_id=ba_id,
            )
            loss_time, detected = loss_result[0], loss_result[1]
            detection_stage = loss_result[2] if len(loss_result) > 2 else None
            # 1 tick = 1 hour; round up so non-integer hours don't realize early.
            due_tick = int(math.ceil(float(breach_tick) + max(0.0, float(loss_time))))

            outage_hours = None
            if asset_type == "process":
                outage_hours = self._compute_outage_hours(
                    loss_time_hours=loss_time,
                    lecs=self._linked_lecs(tech_asset_id, ba_id),
                )

            self.pending.append(
                PendingLoss(
                    due_tick=due_tick,
                    breach_tick=int(breach_tick),
                    threat_id=str(threat_id),
                    tech_asset_id=str(tech_asset_id),
                    business_asset_id=ba_id,
                    asset_type=asset_type,
                    loss_time_hours=float(loss_time),
                    outage_hours=outage_hours,
                    failed_controls=list(failed_controls) if failed_controls else None,
                    variant_controls=list(variant_controls) if variant_controls else None,
                    threat_velocity_hours=threat_velocity,
                    threat_loss_rate_exp=threat_exp,
                    detected=detected,
                    detection_stage=detection_stage,
                )
            )

    # ---------------------------------------------------------------------
    # Tick API
    # ---------------------------------------------------------------------

    def step(self) -> None:
        """Realize any pending losses due on the current tick."""
        now = int(getattr(self.model.schedule, "steps", 0))

        if not self.pending:
            return

        due, future = [], []
        for p in self.pending:
            (due if p.due_tick <= now else future).append(p)
        self.pending = future

        for ev in due:
            try:
                self._realize_loss(ev, tick=now)
            except Exception:
                logger.exception("Failed to realize loss event: %s", ev)

    # ---------------------------------------------------------------------
    # Realization
    # ---------------------------------------------------------------------

    def _realize_loss(self, ev: PendingLoss, tick: int) -> None:
        gross = self._sample_gross_loss(ev)

        # Stage-gated detection: apply loss multiplier based on detection stage.
        # Earlier detection means the attacker achieved less of their objective,
        # so gross loss is scaled down by the stage weight.
        if ev.detection_stage:
            stage_weight = 1.0
            for stage in ATTACK_STAGES:
                if stage["name"] == ev.detection_stage:
                    stage_weight = float(stage["weight"])
                    break
            gross = gross * stage_weight
            logger.debug(
                "Stage-gated loss multiplier: stage=%s, weight=%.2f, adjusted_gross=%.2f",
                ev.detection_stage, stage_weight, gross,
            )

        # "No detection → no response." If the breach was not detected,
        # the organisation cannot activate response/loss-reduction controls.
        # The attacker achieves full, unmitigated impact.
        if ev.detected:
            net = self._apply_loss_reduction_controls(gross, tech_asset_id=ev.tech_asset_id, business_asset_id=ev.business_asset_id)
        else:
            net = gross

        primary = gross * self._primary_ratio

        # Apply SLEF (Secondary Loss Event Frequency) - determines whether this
        # primary loss event also results in secondary losses.
        # SLEF=1.0 means all primary losses incur secondary; SLEF=0.5 means 50% do.
        if self._slef >= 1.0:
            # Always incur secondary losses
            secondary = gross - primary
        elif self._slef <= 0.0:
            # Never incur secondary losses
            secondary = 0.0
        else:
            # Probabilistic: draw whether secondary loss occurs
            # Keyed to business asset so removing a control doesn't
            # shift this draw for unrelated assets (see STREAM_ISOLATION.md)
            slef_rng = self._entity_rng("loss_slef", ev.business_asset_id)
            if float(slef_rng.random()) < self._slef:
                secondary = gross - primary
            else:
                secondary = 0.0

        ms = getattr(self.model, "metrics_state", None)
        if ms is not None:
            ms.total_loss_events += 1
            ms.total_gross_losses += float(gross)
            ms.total_net_losses += float(net)
            ms.total_primary_losses += float(primary)
            ms.total_secondary_losses += float(secondary)

            # Keep existing loss_event_log compatible: store gross components (primary/secondary)
            try:
                ms.loss_event_log.append(
                    {
                        "tick": int(tick),
                        "breach_tick": int(ev.breach_tick),
                        "business_asset_id": ev.business_asset_id,
                        "tech_asset_id": ev.tech_asset_id,
                        "threat_id": ev.threat_id,
                        "asset_type": ev.asset_type,
                        "loss_time_hours": float(ev.loss_time_hours),
                        "outage_hours": float(ev.outage_hours) if ev.outage_hours is not None else None,
                        "gross_loss": float(gross),
                        "net_loss": float(net),
                        "primary_loss": float(primary),
                        "secondary_loss": float(secondary),
                        "detected": ev.detected,
                        "detection_stage": ev.detection_stage,
                        "variant_controls": ev.variant_controls,
                        "failed_controls": ev.failed_controls,
                    }
                )
            except Exception:
                pass

        nar = getattr(self.model, "narrative", None)
        if nar is not None and hasattr(nar, "record_loss_event"):
            nar.record_loss_event(
                business_asset_id=ev.business_asset_id,
                tech_asset_id=ev.tech_asset_id,
                threat_id=ev.threat_id,
                tick=int(tick),
                breach_tick=int(ev.breach_tick),
                primary_loss=float(primary),
                secondary_loss=float(secondary),
                failed_controls=ev.failed_controls,
                variant_controls=ev.variant_controls,
                # Enhanced details for narrative
                asset_type=ev.asset_type,
                loss_time_hours=float(ev.loss_time_hours),
                outage_hours=ev.outage_hours,
            )

        # emit security_breach org event so personnel behavior reacts.
        breach_event_name = cfg.get("personnel_behavior.breach_event_name", "security_breach")
        if breach_event_name and hasattr(self.model, "record_org_event"):
            try:
                self.model.record_org_event(str(breach_event_name))
            except Exception:
                logger.exception("Failed to emit breach org event for TA=%s", ev.tech_asset_id)

        # return assets to normal and remove threat after loss termination.
        # Only clean up if no other pending losses reference the same tech asset / threat.
        other_pending_for_ta = any(
            p.tech_asset_id == ev.tech_asset_id for p in self.pending
        )
        if not other_pending_for_ta:
            cleanup = getattr(self.model, "cleanup_after_loss", None)
            if callable(cleanup):
                try:
                    cleanup(ev.tech_asset_id, ev.threat_id)
                except Exception:
                    logger.exception("Failed to clean up after loss for TA=%s", ev.tech_asset_id)

    # ---------------------------------------------------------------------
    # Gross loss sampling
    # ---------------------------------------------------------------------

    def _sample_gross_loss(self, ev: PendingLoss) -> float:
        if not self._use_tables:
            raise RuntimeError("loss.use_tables is true, but loss tables are not initialized.")

        if ev.asset_type == "information":
            if self._empirical_breach is None:
                raise RuntimeError(
                    "No empirical breach sampler configured for information asset loss. "
                    "Set loss.tables.empirical_breach_json in model_config.yaml."
                )
            return float(self._empirical_breach.sample(
                rng=self._np_rng,
                scenario_type=str(self._scenario_type) if self._scenario_type else None,
                sector=str(self._sector) if self._sector else None,
                revenue_bucket=str(self._revenue_bucket) if self._revenue_bucket else None,
            ))

        if ev.asset_type == "process":
            if ev.outage_hours is None:
                raise ValueError("Process loss event missing outage_hours.")

            if self._empirical_outage is not None:
                return float(self._empirical_outage.sample(
                    rng=self._np_rng,
                    duration_hours=float(ev.outage_hours),
                    revenue_bucket=str(self._revenue_bucket) if self._revenue_bucket else None,
                ))

            if self.tables is not None and self.tables.has_outage():
                return float(self.tables.sample_outage_total(
                    duration_hours=float(ev.outage_hours), rng=self._np_rng,
                ))

            raise RuntimeError(
                "No outage loss sampler configured. "
                "Set loss.tables.empirical_outage_json or loss.tables.outage_csv in model_config.yaml."
            )

        raise ValueError(f"Unsupported asset_type={ev.asset_type}")

    # ---------------------------------------------------------------------
    # Timing
    # ---------------------------------------------------------------------

    def _compute_loss_time_hours(self, tech_asset_id: str, business_asset_id: str) -> tuple:
        """
        loss_time = detection + termination + monitoring_backtrack

        Detection/termination times can come from:
        1. Per-LEC time distributions (monitoring/event_termination LECs with time-based Efficacy Method)
        2. YAML default distributions (fallback)
        3. Optionally modified by LEC efficacy (config-driven mapping)

        Detection AND gate:
        Before computing detection time, the AND gate checks that all three
        detection subfunctions (Visibility, Monitoring, Recognition) have at
        least one operational control. If any subfunction fails, the breach
        goes undetected for a much longer period.

        Returns:
            Tuple of (loss_time_hours: float, detected: bool, detection_stage: Optional[str]).
            When detected=False, the caller should bypass loss reduction (KB §04:
            "No detection → no response" — the organisation cannot mitigate what
            it doesn't know about).
            detection_stage is the name of the attack stage where detection occurred
            (only set when stage-gated detection is enabled).
        """
        lecs = self._linked_lecs(tech_asset_id, business_asset_id)

        # ---- Detection AND gate ----
        # Evaluate whether detection succeeds per FAIR-CAM AND dependency.
        # Returns detection_time_hours (float).  Stage-gated mode also provides
        # detection_stage via _evaluate_stage_gated_detection.
        # Set transient context so Bernoulli draws inside detection can
        # be keyed to the asset pair (see STREAM_ISOLATION.md)
        self._stream_context = (tech_asset_id, business_asset_id)
        detection_stage: Optional[str] = None
        detection = self._evaluate_detection_time(lecs)

        # When stage-gated is enabled, _evaluate_detection_time delegates to
        # _evaluate_stage_gated_detection which stores the stage on a transient attr.
        if self._stage_gated_enabled:
            detection_stage = getattr(self, "_last_detection_stage", None)

        detected = detection < self._undetected_time_hours

        # Try per-LEC termination time (event_termination/response/monitoring LECs with termination_time method).
        # Note: monitoring LECs can carry "timing interval for loss termination" efficacy method
        # (e.g., anti-malware that detects and terminates), so we include monitoring here.
        termination = self._get_lec_time(
            lecs,
            lec_types=("event_termination", "termination", "response", "monitoring"),
            method_type="termination_time",
            fallback_dist=self._timing["termination_time_dist"],
        )

        backtrack = float(self._timing["monitoring_backtrack_hours"])

        # Optional efficacy->time compression (only if not already using per-LEC times)
        if bool(self._eff_to_time.get("enabled", False)):
            # Only apply efficacy-based compression if detection succeeded;
            # when undetected, the long dwell time should not be reduced.
            if detection < self._undetected_time_hours:
                detection = detection * self._time_multiplier_from_controls(
                    tech_asset_id=tech_asset_id,
                    business_asset_id=business_asset_id,
                    lec_type_match=self._eff_to_time.get("detection_lec_types", []),
                )
            termination = termination * self._time_multiplier_from_controls(
                tech_asset_id=tech_asset_id,
                business_asset_id=business_asset_id,
                lec_type_match=self._eff_to_time.get("termination_lec_types", []),
            )

        # Apply response concurrency factor:
        # T_response = T_containment + T_recovery - alpha * min(T_containment, T_recovery)
        # Here, detection is the "find it" phase and termination is the "contain it" phase.
        # Alpha models overlap between these activities (some orgs detect and contain in parallel).
        alpha = self._response_concurrency_alpha
        if alpha > 0.0 and detected:
            overlap = alpha * min(detection, termination)
        else:
            overlap = 0.0

        return (float(max(0.0, detection + termination + backtrack - overlap)), detected, detection_stage)

    def _evaluate_detection_time(self, lecs: List[Any]) -> float:
        """
        Evaluate the detection AND gate and return detection time in hours.

        Per FAIR-CAM: Detection requires ALL THREE subfunctions to succeed:

            Detection = Visibility AND Monitoring AND Recognition

        - **Visibility** (probability [0-1]): Evidence of attack activity is
          available (e.g., logging, EDR telemetry). If no visibility control
          is operational, there is nothing to monitor.

        - **Monitoring** (time in hours): Detection sweep cadence — how often
          someone (or something) reviews the evidence. Provides the time
          component of detection.

        - **Recognition** (probability [0-1]): Ability to distinguish normal
          from abnormal activity (e.g., signatures, behavioral baselines).
          If recognition fails, even visible anomalies go unrecognized.

        The simplified AND formula (single-review approximation of KB §04):

            P(Detect) = V_eff × R_eff

        Where V_eff = best visibility efficacy, R_eff = best recognition
        efficacy (both sampled from normal-state LECs). Monitoring provides
        the time-to-detect.

        If the AND gate fails (any subfunction has no operational control),
        or the Bernoulli trial fails, the breach goes undetected for
        ``undetected_time_hours`` (default 720h = 30 days).

        Returns:
            Detection time in hours.
        """
        ms = getattr(self.model, "metrics_state", None)

        # Stage-gated detection: delegate to multi-stage model when enabled
        if self._stage_gated_enabled:
            return self._evaluate_stage_gated_detection(lecs)

        if not self._detection_and_enabled:
            # Feature disabled — fall back to original monitoring-only logic
            return self._get_lec_time(
                lecs,
                lec_types=("monitoring",),
                method_type="detection_time",
                fallback_dist=self._timing["detection_time_dist"],
            )

        # ---- Partition detection LECs by subfunction type ----
        vis_lecs: List[Any] = []       # visibility (probability-based)
        mon_lecs: List[Any] = []       # monitoring (time-based)
        recog_lecs: List[Any] = []     # recognition (probability-based)

        for lec in lecs:
            lec_type = _norm_type(getattr(lec, "lec_type", ""))
            if lec_type == "visibility":
                vis_lecs.append(lec)
            elif lec_type == "monitoring":
                mon_lecs.append(lec)
            elif lec_type == "recognition":
                recog_lecs.append(lec)

        # ---- Check each subfunction for at least one operational control ----
        def _best_normal_probability(subfunction_lecs: List[Any]) -> Optional[float]:
            """Return the best efficacy among normal-state probability LECs, or None."""
            best = None
            for lec in subfunction_lecs:
                lec_state = str(getattr(lec, "state", "normal")).lower()
                if lec_state in ("variant", "remediating"):
                    continue
                # Sample probability from the LEC's distribution
                if hasattr(lec, "sample_success_probability"):
                    p = lec.sample_success_probability()
                    if p is not None:
                        p = _clamp(float(p), 0.0, 1.0)
                        if best is None or p > best:
                            best = p
                        continue
                # Fallback: use stored efficacy
                eff = self._lec_effective_efficacy(lec)
                if best is None or eff > best:
                    best = eff
            return best

        def _has_normal_monitoring(monitoring_lecs: List[Any]) -> bool:
            """Check if at least one monitoring LEC is in normal state."""
            for lec in monitoring_lecs:
                lec_state = str(getattr(lec, "state", "normal")).lower()
                if lec_state not in ("variant", "remediating"):
                    return True
            return False

        # Evaluate subfunctions
        vis_eff = _best_normal_probability(vis_lecs)
        has_monitoring = _has_normal_monitoring(mon_lecs)
        recog_eff = _best_normal_probability(recog_lecs)

        # ---- AND gate: all three must be operational ----
        # If any subfunction has NO normal-state controls, detection fails.
        #
        # require_all_subfunctions (default true, KB §01):
        #   true  = missing subfunctions FAIL detection (strict — KB-compliant)
        #   false = missing subfunctions are "ungated" (legacy backward compat)

        strict = self._require_all_subfunctions

        vis_gate_active = len(vis_lecs) > 0 or strict
        recog_gate_active = len(recog_lecs) > 0 or strict

        and_gate_failed = False
        failure_reason = ""

        if vis_gate_active and vis_eff is None:
            and_gate_failed = True
            failure_reason = "visibility (no operational controls)"
        elif not has_monitoring and (len(mon_lecs) > 0 or strict):
            and_gate_failed = True
            failure_reason = "monitoring (no operational controls)"
        elif recog_gate_active and recog_eff is None:
            and_gate_failed = True
            failure_reason = "recognition (no operational controls)"

        if and_gate_failed:
            logger.debug(
                "Detection AND gate FAILED: %s subfunction has no "
                "operational controls — breach undetected for %.0f hours",
                failure_reason, self._undetected_time_hours,
            )
            if ms is not None:
                ms.detection_and_gate_failures = getattr(ms, "detection_and_gate_failures", 0) + 1
            return self._undetected_time_hours

        # ---- Sample monitoring time (how long until detection) ----
        base_detection_time = self._get_lec_time(
            lecs,
            lec_types=("monitoring",),
            method_type="detection_time",
            fallback_dist=self._timing["detection_time_dist"],
        )

        # ---- VMC_THREAT_INTEL: reduce detection time using intel VMC's own efficacy ----
        # The VMC's current_efficacy (from its JSON parameters) determines the
        # detection time reduction. Higher efficacy = faster detection.
        # Multiplier = 1 - efficacy (e.g., efficacy 0.3 → detection time × 0.7).
        net = getattr(self.model, "network", None)
        if net is not None and hasattr(net, "get_threat_intel_vmcs"):
            try:
                for lec in lecs:
                    lec_id = str(getattr(lec, "unique_id", "")).strip()
                    if not lec_id:
                        continue
                    intel_vmcs = net.get_threat_intel_vmcs(lec_id)
                    if intel_vmcs:
                        # Use the best operational intel VMC's efficacy
                        best_eff = 0.0
                        best_vmc_id = "?"
                        for vmc in intel_vmcs:
                            if str(getattr(vmc, "state", "normal")).lower() == "variant":
                                continue
                            eff = float(getattr(vmc, "current_efficacy", 0.0))
                            if eff > best_eff:
                                best_eff = eff
                                best_vmc_id = str(getattr(vmc, "unique_id", "?"))
                        if best_eff > 0.0:
                            multiplier = max(0.1, 1.0 - best_eff)
                            base_detection_time *= multiplier
                            logger.debug(
                                "VMC_THREAT_INTEL: %s (eff=%.2f) reduced detection "
                                "time by %.0f%%",
                                best_vmc_id, best_eff, (1.0 - multiplier) * 100,
                            )
                            break  # Apply once per detection evaluation
            except Exception:
                pass

        # ---- Probability gate (Bernoulli trial) ----
        # When enabled, the combined detection probability determines whether
        # this particular breach is actually detected. This maps to the KB §04
        # formula: P(Detect) = V_eff × R_eff (simplified single-review case).
        if self._use_probability_gate:
            # Use effective values, defaulting to 1.0 for ungated subfunctions
            v = vis_eff if vis_gate_active and vis_eff is not None else 1.0
            r = recog_eff if recog_gate_active and recog_eff is not None else 1.0

            p_detect = max(self._min_detection_prob, v * r)

            # Keyed to asset pair (see STREAM_ISOLATION.md)
            ctx = getattr(self, "_stream_context", ("?", "?"))
            detect_rng = self._entity_rng("loss_detect", ctx[0], ctx[1])
            if float(detect_rng.random()) >= p_detect:
                # Detection trial failed — breach not detected this time
                logger.debug(
                    "Detection AND gate passed but Bernoulli trial failed "
                    "(P=%.3f, vis=%.3f, recog=%.3f) — undetected for %.0f hours",
                    p_detect, v, r, self._undetected_time_hours,
                )
                if ms is not None:
                    ms.detection_probability_failures = getattr(
                        ms, "detection_probability_failures", 0
                    ) + 1
                return self._undetected_time_hours

            # Detection trial succeeded
            logger.debug(
                "Detection AND gate passed, Bernoulli succeeded "
                "(P=%.3f, vis=%.3f, recog=%.3f) — detection in %.1f hours",
                p_detect, v, r, base_detection_time,
            )

        if ms is not None:
            ms.detection_and_gate_successes = getattr(
                ms, "detection_and_gate_successes", 0
            ) + 1

        return base_detection_time

    def _evaluate_stage_gated_detection(self, lecs: List[Any]) -> float:
        """
        Stage-gated detection model.

        The attack progresses through ATTACK_STAGES sequentially.  At each
        stage an independent detection opportunity is evaluated using the
        existing V_eff x R_eff probability, raised to the configured number
        of reviews per stage:

            P(detect at stage) = 1 - (1 - V_eff * R_eff) ^ reviews_per_stage

        If detected at a given stage, detection time is proportional to
        the stage weight applied to the base monitoring time.

        The stage name is stored on ``self._last_detection_stage`` so the
        caller (``_compute_loss_time_hours``) can relay it to PendingLoss.

        Returns:
            Detection time in hours (same contract as _evaluate_detection_time).
        """
        ms = getattr(self.model, "metrics_state", None)
        self._last_detection_stage = None  # reset

        # ---- Compute V_eff and R_eff using the same partitioning logic ----
        vis_lecs: List[Any] = []
        mon_lecs: List[Any] = []
        recog_lecs: List[Any] = []

        for lec in lecs:
            lec_type = _norm_type(getattr(lec, "lec_type", ""))
            if lec_type == "visibility":
                vis_lecs.append(lec)
            elif lec_type == "monitoring":
                mon_lecs.append(lec)
            elif lec_type == "recognition":
                recog_lecs.append(lec)

        def _best_normal_probability(subfunction_lecs: List[Any]) -> Optional[float]:
            best = None
            for lec in subfunction_lecs:
                lec_state = str(getattr(lec, "state", "normal")).lower()
                if lec_state in ("variant", "remediating"):
                    continue
                if hasattr(lec, "sample_success_probability"):
                    p = lec.sample_success_probability()
                    if p is not None:
                        p = _clamp(float(p), 0.0, 1.0)
                        if best is None or p > best:
                            best = p
                        continue
                eff = self._lec_effective_efficacy(lec)
                if best is None or eff > best:
                    best = eff
            return best

        def _has_normal_monitoring(monitoring_lecs: List[Any]) -> bool:
            for lec in monitoring_lecs:
                lec_state = str(getattr(lec, "state", "normal")).lower()
                if lec_state not in ("variant", "remediating"):
                    return True
            return False

        vis_eff = _best_normal_probability(vis_lecs)
        has_monitoring = _has_normal_monitoring(mon_lecs)
        recog_eff = _best_normal_probability(recog_lecs)

        # ---- AND gate check (same logic as single-review path) ----
        strict = self._require_all_subfunctions
        vis_gate_active = len(vis_lecs) > 0 or strict
        recog_gate_active = len(recog_lecs) > 0 or strict

        and_gate_failed = False
        if vis_gate_active and vis_eff is None:
            and_gate_failed = True
        elif not has_monitoring and (len(mon_lecs) > 0 or strict):
            and_gate_failed = True
        elif recog_gate_active and recog_eff is None:
            and_gate_failed = True

        if and_gate_failed:
            logger.debug(
                "Stage-gated detection: AND gate failed — breach undetected for %.0f hours",
                self._undetected_time_hours,
            )
            if ms is not None:
                ms.detection_and_gate_failures = getattr(ms, "detection_and_gate_failures", 0) + 1
            return self._undetected_time_hours

        # ---- Base detection time from monitoring LECs / fallback ----
        base_detection_time = self._get_lec_time(
            lecs,
            lec_types=("monitoring",),
            method_type="detection_time",
            fallback_dist=self._timing["detection_time_dist"],
        )

        # ---- Combined single-review detection probability ----
        v = vis_eff if vis_gate_active and vis_eff is not None else 1.0
        r = recog_eff if recog_gate_active and recog_eff is not None else 1.0
        p_single = max(self._min_detection_prob, v * r)

        reviews = max(1, self._reviews_per_stage)

        # ---- Walk through stages ----
        for stage_idx, stage in enumerate(ATTACK_STAGES):
            # P(detect at this stage) = 1 - (1 - p_single)^reviews
            p_stage = 1.0 - (1.0 - p_single) ** reviews

            # Keyed to asset context + stage for deterministic per-stage draw
            ctx = getattr(self, "_stream_context", ("?", "?"))
            stage_rng = self._entity_rng("loss_stage", ctx[0], ctx[1], str(stage_idx))
            if float(stage_rng.random()) < p_stage:
                # Detected at this stage
                stage_name = stage["name"]
                stage_weight = float(stage["weight"])
                detection_time = base_detection_time * stage_weight

                self._last_detection_stage = stage_name

                logger.debug(
                    "Stage-gated detection: detected at stage %d (%s), "
                    "P_stage=%.3f, detection_time=%.1f hours (base=%.1f * weight=%.2f)",
                    stage_idx, stage_name, p_stage, detection_time,
                    base_detection_time, stage_weight,
                )
                if ms is not None:
                    ms.detection_and_gate_successes = getattr(
                        ms, "detection_and_gate_successes", 0
                    ) + 1
                return detection_time

        # ---- No stage detected — breach goes undetected ----
        logger.debug(
            "Stage-gated detection: all %d stages missed (P_single=%.3f, reviews=%d) "
            "— breach undetected for %.0f hours",
            len(ATTACK_STAGES), p_single, reviews, self._undetected_time_hours,
        )
        if ms is not None:
            ms.detection_probability_failures = getattr(
                ms, "detection_probability_failures", 0
            ) + 1
        return self._undetected_time_hours

    def _get_lec_time(
        self,
        lecs: List[Any],
        lec_types: Tuple[str, ...],
        method_type: str,
        fallback_dist: Optional[Dict[str, Any]],
    ) -> Optional[float]:
        """
        Get time from matching LEC with time-based Efficacy Method, or sample from fallback distribution.

        Args:
            lecs: List of linked LECs
            lec_types: LEC types to match (e.g., ("monitoring",))
            method_type: Expected _efficacy_method_type (e.g., "detection_time")
            fallback_dist: YAML distribution spec to use if no matching LEC found.
                           If None, returns None when no match found.

        Returns:
            Sampled time in hours, or None if no match and no fallback.
        """
        for lec in lecs:
            # skip controls in variant or remediating state — they cannot
            # contribute detection/termination/recovery times while degraded.
            lec_state = str(getattr(lec, "state", "normal")).lower()
            if lec_state in ("variant", "remediating"):
                continue

            lec_type = _norm_type(getattr(lec, "lec_type", ""))
            lec_method = getattr(lec, "_efficacy_method_type", "")

            if lec_type in lec_types and lec_method == method_type:
                # Map method type to sampler method name
                sampler_map = {
                    "detection_time": "sample_detection_time_hours",
                    "termination_time": "sample_termination_time_hours",
                    "recovery_time": "sample_recovery_time_hours",
                }
                sampler_name = sampler_map.get(method_type)

                if sampler_name and hasattr(lec, sampler_name):
                    val = getattr(lec, sampler_name)()
                    if val is not None:
                        return float(val)

        # Fallback to YAML distribution if provided
        if fallback_dist is not None:
            return self._sample_time_dist(fallback_dist)

        return None

    def _sample_time_dist(self, spec: Dict[str, Any]) -> float:
        """
        Sample a time distribution spec from YAML.
        Supported types: uniform, exponential, weibull, lognormal, beta_pert

        YAML shape:
          { type: "weibull", scale: 72, shape: 1.5 }
          { type: "uniform", low: 24, high: 168 }
          { type: "exponential", mean: 72 }
          { type: "lognormal", median: 72, sigma: 1.1 }
          { type: "beta_pert", min: 24, mode: 72, max: 168, confidence: 4 }
        """
        dtype = _norm_type(spec.get("type"))
        if not dtype:
            raise KeyError("Time distribution spec missing 'type'.")

        if dtype == "uniform":
            lo = float(spec["low"])
            hi = float(spec["high"])
            return float(self._np_rng.uniform(lo, hi))

        if dtype == "exponential":
            mean = float(spec["mean"])
            return float(self._np_rng.exponential(mean))

        if dtype == "weibull":
            scale = float(spec["scale"])
            shape = float(spec["shape"])
            return float(scale * self._np_rng.weibull(shape))

        if dtype == "lognormal":
            median = float(spec["median"])
            sigma = float(spec["sigma"])
            return float(self._np_rng.lognormal(mean=np.log(median), sigma=sigma))

        if dtype in ("beta_pert", "betapert", "pert"):
            mn = float(spec["min"])
            md = float(spec["mode"])
            mx = float(spec["max"])
            # Accept both 'confidence' and legacy 'lambda' naming.
            conf = spec.get("confidence", spec.get("lambda", None))
            if conf is None:
                conf = self._beta_pert_default_confidence
            conf = float(conf)
            return float(self._beta_pert(mn, md, mx, conf))

        raise ValueError(f"Unsupported time dist type '{dtype}' in loss_events config.")

    def _beta_pert(self, minimum: float, mode: float, maximum: float, confidence: float) -> float:
        if minimum >= maximum:
            return float(minimum)

        mode = max(minimum, min(maximum, mode))
        mean = (minimum + confidence * mode + maximum) / (confidence + 2.0)

        if abs(mean - mode) < 1e-10:
            alpha = beta = (confidence / 2.0) + 1.0
        else:
            alpha = ((mean - minimum) * (2 * mode - minimum - maximum)) / ((mode - mean) * (maximum - minimum))
            beta = alpha * (maximum - mean) / (mean - minimum)

        alpha = max(0.1, float(alpha))
        beta = max(0.1, float(beta))
        x = float(self._np_rng.beta(alpha, beta))
        return float(minimum + (maximum - minimum) * x)

    def _time_multiplier_from_controls(
        self,
        tech_asset_id: str,
        business_asset_id: str,
        lec_type_match: List[str],
    ) -> float:
        """
        Convert linked LEC efficacy into a time multiplier (lower is faster).

        Fully config-driven:
          loss_events.default.efficacy_to_time:
            min_multiplier: 0.2
            max_multiplier: 1.0
            weight: 0.6
            detection_lec_types: ["monitoring","recognition","visibility"]
            termination_lec_types: ["event_termination","response"]
        """
        min_mult = float(self._eff_to_time["min_multiplier"])
        max_mult = float(self._eff_to_time["max_multiplier"])
        weight = float(self._eff_to_time["weight"])

        if not lec_type_match:
            return 1.0

        lecs = self._linked_lecs(tech_asset_id=tech_asset_id, business_asset_id=business_asset_id)
        if not lecs:
            return 1.0

        match = []
        wanted = {_norm_type(x) for x in lec_type_match}
        for lec in lecs:
            # Skip variant/remediating controls — degraded controls cannot
            # contribute time reduction, consistent with _get_lec_time behavior.
            lec_state = str(getattr(lec, "state", "normal")).lower()
            if lec_state in ("variant", "remediating"):
                continue
            lt = _norm_type(getattr(lec, "lec_type", None))
            if lt in wanted:
                eff = self._lec_effective_efficacy(lec)
                match.append(eff)

        if not match:
            return 1.0

        # Use best available control efficacy (min time).
        best_eff = max(match)
        mult = 1.0 - weight * best_eff
        return float(_clamp(mult, min_mult, max_mult))

    # ---------------------------------------------------------------------
    # Magnitude drivers
    # ---------------------------------------------------------------------

    def _compute_outage_hours(
        self,
        loss_time_hours: float,
        lecs: Optional[List[Any]] = None,
    ) -> float:
        """
        For process assets, treat outage as:
          outage = loss_time_hours + recovery_time

        Recovery time can come from:
        1. Per-LEC time distribution (resilience LECs with recovery_time method)
        2. YAML base_recovery_hours (fallback)

        YAML:
          loss_events.process_recovery:
            base_recovery_hours: 72
        """
        # Try per-LEC recovery time (resilience LECs with recovery_time method)
        if lecs:
            recovery_time = self._get_lec_time(
                lecs,
                lec_types=("resilience", "recovery"),
                method_type="recovery_time",
                fallback_dist=None,  # Will return None if no match
            )
            if recovery_time is not None:
                return float(max(0.0, float(loss_time_hours) + recovery_time))

        # Fallback to YAML default
        base_recovery = float(self._process_recovery["base_recovery_hours"])
        return float(max(0.0, float(loss_time_hours) + base_recovery))

    # ---------------------------------------------------------------------
    # Loss reduction
    # ---------------------------------------------------------------------

    def _apply_loss_reduction_controls(self, gross: float, tech_asset_id: str, business_asset_id: str) -> float:
        """
        Apply loss reduction controls as:
          net = gross * (1 - reduction)

        YAML:
          loss_events.loss_reduction:
            lec_types: ["loss_reduction"]
            weight: 0.5
            max_reduction: 0.9
        """
        lec_types = self._loss_reduction.get("lec_types", [])
        if not lec_types:
            return float(gross)

        lecs = self._linked_lecs(tech_asset_id=tech_asset_id, business_asset_id=business_asset_id)
        if not lecs:
            return float(gross)

        wanted = {_norm_type(x) for x in lec_types}
        effs = []
        for lec in lecs:
            # Skip variant/remediating controls — degraded controls cannot
            # contribute loss reduction, consistent with _get_lec_time behavior.
            lec_state = str(getattr(lec, "state", "normal")).lower()
            if lec_state in ("variant", "remediating"):
                continue
            lt = _norm_type(getattr(lec, "lec_type", None))
            if lt in wanted:
                effs.append(self._lec_effective_efficacy(lec))

        if not effs:
            return float(gross)

        best_eff = max(effs)
        weight = float(self._loss_reduction["weight"])
        max_red = float(self._loss_reduction["max_reduction"])

        reduction = _clamp(weight * best_eff, 0.0, max_red)
        return float(gross * (1.0 - reduction))

    # ---------------------------------------------------------------------
    # Linking helpers
    # ---------------------------------------------------------------------

    def _linked_lecs(self, tech_asset_id: str, business_asset_id: str) -> List[Any]:
        """
        Pull LECs linked to either the tech asset or business asset.
        """
        lecs: List[Any] = []
        net = getattr(self.model, "network", None)
        if net is None:
            return lecs

        try:
            lecs.extend(net.get_protecting_lecs(tech_asset_id) or [])
        except Exception:
            pass
        try:
            lecs.extend(net.get_protecting_lecs(business_asset_id) or [])
        except Exception:
            pass

        # de-dupe by unique_id
        out: List[Any] = []
        seen = set()
        for lec in lecs:
            cid = str(getattr(lec, "unique_id", "")).strip()
            if not cid or cid in seen:
                continue
            seen.add(cid)
            out.append(lec)
        return out

    def _lec_effective_efficacy(self, lec: Any) -> float:
        """
        Use control's own state-dependent efficacy draw if available; else use current/intended fields.
        """
        if hasattr(lec, "draw_current_efficacy"):
            try:
                return _clamp(float(lec.draw_current_efficacy()), 0.0, 1.0)
            except Exception:
                pass
        for attr in ("current_efficacy", "intended_efficacy"):
            if hasattr(lec, attr):
                try:
                    return _clamp(float(getattr(lec, attr)), 0.0, 1.0)
                except Exception:
                    continue
        return 0.0

    def _draw_seed(self) -> int:
        """
        Derive a deterministic numpy seed from isolated loss stream (if available)
        or mesa RNG (random.Random).
        """
        streams = getattr(self.model, "streams", None)
        if streams is not None:
            r = streams.get("loss")
            return int(r.randint(0, 2**31 - 1))
        r = getattr(self.model, "random", None)
        if r is None or not hasattr(r, "randint"):
            raise AttributeError("Model has no RNG (model.random.randint missing).")
        return int(r.randint(0, 2**31 - 1))