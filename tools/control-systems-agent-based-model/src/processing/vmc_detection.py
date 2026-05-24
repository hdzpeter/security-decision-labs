"""src/processing/vmc_detection.py

Variance Management Controls (VMC) monitoring + detection.

Two triggering mechanisms:
1) Periodic monitoring sweeps (per-VMC intervals from JSON, or global YAML default)
2) On-change-event detection attempts (when change events occur)

Per-VMC detection behavior based on Efficacy Method (from JSON):
- "time interval for variance detection sweep": params are hours (Beta-PERT)
  - VMC schedules sweeps at sampled intervals
- "variance probability adjustment factor": params are probability [0-1] (Beta-PERT)
  - VMC uses sampled probability as detection success factor
- "time interval for variance correction": params are hours (Beta-PERT)
  - VMC provides remediation duration (not detection)

Detection probability:
- For time-based VMCs (detection_time): 100% detection when sweep occurs
  - JSON specifies WHEN to sweep (interval in hours), not IF detection succeeds
  - When the sweep runs, all variant controls are detected
- For probability-based VMCs: sample factor from Beta-PERT, use as detection probability
  - JSON specifies HOW LIKELY detection is (probability factor [0-1])
- For other VMCs (remediation_time, etc.): use base_detection_probability * efficacy
  - These don't primarily do detection, so use conservative fallback

Personnel behavior integration:
- When a monitoring sweep detects at least one variant control, emit an organizational event
  (configurable; default lives in YAML) via model.record_org_event(...).
- Optionally, when a sweep runs and detects no variants, emit a "passed" event.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..config import get_config

logger = logging.getLogger(__name__)
cfg = get_config()


def _require(key: str):
    v = cfg.get(key, None)
    if v is None:
        raise ValueError(f"Missing required config key: {key}")
    return v


@dataclass
class DetectionResult:
    vmc_id: str
    detected: bool
    control_id: str
    tick: int
    reason: str


class VMCDetectionProcessor:
    """Pure logic for detection decisions."""

    def __init__(self, model: Any):
        self.model = model
        # Per-entity stream isolation for marginal value analysis (see STREAM_ISOLATION.md)
        self._streams = getattr(model, "streams", None)

    def _entity_rng(self, vmc_id: str, control_id: str):
        """Isolated RNG keyed to the VMC+control pair for marginal value analysis."""
        if self._streams is not None:
            return self._streams.get(f"vmc_detect:{vmc_id}:{control_id}")
        r = getattr(self.model, "random", None)
        if r is None:
            raise ValueError("Model must provide model.random RNG")
        return r

    def _bernoulli(self, p: float, vmc_id: str = "", control_id: str = "") -> bool:
        pp = float(p)
        if pp <= 0.0:
            return False
        if pp >= 1.0:
            return True
        return float(self._entity_rng(vmc_id, control_id).random()) < pp

    def _get_detection_probability(self, vmc_agent: Any) -> float:
        """
        Get detection probability for a VMC based on its Efficacy Method.

        For time-based VMCs (time interval for variance detection sweep):
        - JSON provides WHEN to sweep (interval in hours)
        - Detection is guaranteed (100%) when sweep occurs
        - The value of the VMC is in the scheduling, not detection probability

        For probability-based VMCs (variance probability adjustment factor):
        - JSON provides HOW LIKELY detection is (probability factor [0-1])
        - Sample the probability factor from Beta-PERT distribution
        - Use this factor as detection probability

        For other VMCs (e.g., remediation_time):
        - Use base_detection_probability from YAML scaled by VMC efficacy
        - These VMCs don't primarily do detection, so use conservative approach
        """
        # Check VMC's efficacy method semantics
        behavior = getattr(vmc_agent, "_efficacy_behavior", None)
        semantic_type = getattr(vmc_agent, "_efficacy_semantic_type", None)
        time_type = getattr(vmc_agent, "_efficacy_time_type", None)

        # Time-based detection VMCs: 100% detection when sweep occurs
        # The JSON specifies WHEN to sweep (interval), not IF detection succeeds
        if semantic_type == "time_hours" and time_type == "detection_time":
            return 1.0

        # Probability-based VMCs: sample detection probability from Beta-PERT
        if behavior == "bernoulli_trial" and semantic_type == "probability":
            if hasattr(vmc_agent, "sample_variance_probability_factor"):
                factor = vmc_agent.sample_variance_probability_factor()
                if factor is not None:
                    return min(1.0, max(0.0, factor))

        # For other VMCs (remediation_time, etc.), use base probability * efficacy
        # These don't primarily do detection, so use conservative fallback
        eff = float(getattr(vmc_agent, "get_effective_efficacy", lambda: getattr(vmc_agent, "current_efficacy", 0.0))())
        base = float(_require("vmc_detection.monitoring_sweep.base_detection_probability"))
        return min(1.0, max(0.0, base * eff))

    def detect_changes(
        self,
        vmc_agent: Any,
        monitored_controls: List[Any],
        change_severity: float,
        reason: str,
    ) -> List[DetectionResult]:
        """Attempt to detect variance for controls during a change event (only VARIANT controls eligible)."""
        results: List[DetectionResult] = []

        # Get detection probability based on VMC's efficacy method
        base_p = self._get_detection_probability(vmc_agent)
        scale = float(_require("vmc_detection.change_event.severity_scale"))
        p_detect = min(1.0, max(0.0, base_p * (float(change_severity) * scale)))

        tick = int(getattr(self.model.schedule, "steps", 0))
        vmc_id = str(getattr(vmc_agent, "unique_id", "VMC"))

        for ctrl in monitored_controls:
            cid = str(getattr(ctrl, "unique_id", "CONTROL"))
            if str(getattr(ctrl, "state", "normal")).lower() != "variant":
                continue
            detected = self._bernoulli(p_detect, vmc_id=vmc_id, control_id=cid)
            results.append(DetectionResult(vmc_id=vmc_id, detected=detected, control_id=cid, tick=tick, reason=reason))
        return results

    def monitoring_sweep(self, vmc_agent: Any) -> List[DetectionResult]:
        """Routine sweep across controls monitored by this VMC (only VARIANT controls eligible)."""
        net = getattr(self.model, "network", None)
        if net is None:
            return []

        monitored = net.get_monitored_controls(str(getattr(vmc_agent, "unique_id", ""))) or []
        tick = int(getattr(self.model.schedule, "steps", 0))
        vmc_id = str(getattr(vmc_agent, "unique_id", "VMC"))

        # Get detection probability based on VMC's efficacy method
        p_detect = self._get_detection_probability(vmc_agent)

        out: List[DetectionResult] = []
        for ctrl in monitored:
            cid = str(getattr(ctrl, "unique_id", "CONTROL"))
            if str(getattr(ctrl, "state", "normal")).lower() != "variant":
                continue
            detected = self._bernoulli(p_detect, vmc_id=vmc_id, control_id=cid)
            out.append(DetectionResult(vmc_id=vmc_id, detected=detected, control_id=cid, tick=tick, reason="monitoring_sweep"))
        return out


class VMCDetector:
    """Model-facing orchestrator wrapper."""

    def __init__(self, model: Any):
        self.model = model
        self.processor = VMCDetectionProcessor(model)
        # Track next sweep tick for each VMC with per-VMC intervals
        self._vmc_next_sweep: Dict[str, int] = {}

    def _vmc_agents(self) -> List[Any]:
        vmcs = []
        for a in getattr(self.model.schedule, "agents", []):
            uid = str(getattr(a, "unique_id", "")).upper()
            if uid.startswith("VM") or uid.startswith("VMC"):
                vmcs.append(a)
        return vmcs

    def _enqueue_if_detected(self, results: List[DetectionResult]) -> None:
        if not results:
            return
        remediation = getattr(self.model, "remediation", None)
        net = getattr(self.model, "network", None)
        if remediation is None or net is None or not hasattr(remediation, "add"):
            return

        for r in results:
            if not r.detected:
                continue
            ctrl = net.get_agent(r.control_id)
            if ctrl is None:
                continue
            try:
                remediation.add(r.control_id, ctrl)
            except Exception:
                logger.exception("Failed to enqueue detected variant control %s", r.control_id)

    def _emit_audit_events(self, *, any_detected: bool, sweep_ran: bool) -> None:
        if not sweep_ran:
            return

        names = _require("vmc_detection.monitoring_sweep.audit_event_names")
        finding = str(names.get("finding", "")).strip()
        passed = str(names.get("passed", "")).strip()

        emit_passed = bool(_require("vmc_detection.monitoring_sweep.emit_audit_passed_event"))
        if any_detected:
            if finding and hasattr(self.model, "record_org_event"):
                self.model.record_org_event(finding)
        else:
            if emit_passed and passed and hasattr(self.model, "record_org_event"):
                self.model.record_org_event(passed)

    def _get_vmc_interval(self, vmc: Any) -> int:
        """
        Get detection interval for a VMC.

        For VMCs with time_hours semantic type and detection_time time_type,
        sample from their time distribution. When the VMC is variant, add a
        sample from its change frequency distribution to degrade the interval
        (sweeps become less frequent — a degraded monitor scans less often).

        Otherwise use global YAML default.
        """
        semantic_type = getattr(vmc, "_efficacy_semantic_type", "efficacy")
        time_type = getattr(vmc, "_efficacy_time_type", None)

        # Use VMC's sampled interval if it's a detection-time VMC
        if semantic_type == "time_hours" and time_type == "detection_time":
            if hasattr(vmc, "sample_detection_interval_hours"):
                base = max(1, int(vmc.sample_detection_interval_hours()))
                # Variant: add change freq sample to degrade sweep interval
                if str(getattr(vmc, "state", "normal")).lower() == "variant":
                    if hasattr(vmc, "sample_change_freq_hours"):
                        base += max(0, int(vmc.sample_change_freq_hours()))
                return base

        return int(_require("time.vmc_monitoring_interval_hours"))

    def _should_sweep(self, vmc: Any, vmc_id: str, tick: int) -> bool:
        """
        Determine if VMC should run detection sweep at this tick.

        Per-VMC detection intervals: VMCs with time_hours semantic type and
        detection_time time_type use their own sampled interval.
        Other VMCs use the global interval.
        """
        semantic_type = getattr(vmc, "_efficacy_semantic_type", "efficacy")
        time_type = getattr(vmc, "_efficacy_time_type", None)

        # VMCs with detection time intervals schedule their own sweeps
        if semantic_type == "time_hours" and time_type == "detection_time":
            # Per-VMC interval scheduling
            if vmc_id not in self._vmc_next_sweep:
                # Initialize: schedule first sweep
                interval = self._get_vmc_interval(vmc)
                run_at_tick0 = bool(_require("vmc_detection.monitoring_sweep.run_at_tick0"))
                if run_at_tick0:
                    self._vmc_next_sweep[vmc_id] = tick + interval
                    return True
                else:
                    self._vmc_next_sweep[vmc_id] = interval
                    return False

            if tick >= self._vmc_next_sweep[vmc_id]:
                # Schedule next sweep with freshly sampled interval
                interval = self._get_vmc_interval(vmc)
                self._vmc_next_sweep[vmc_id] = tick + interval
                return True

            return False

        # Probability-based VMCs (variance probability adjustment) also do sweeps
        # but at the global interval
        elif semantic_type == "probability":
            interval = int(_require("time.vmc_monitoring_interval_hours"))
            if interval <= 0:
                return False
            run_at_tick0 = bool(_require("vmc_detection.monitoring_sweep.run_at_tick0"))
            return (tick % interval == 0) and (run_at_tick0 or tick > 0)

        else:
            # Other VMCs (remediation_time, etc.) don't do detection sweeps themselves
            # They participate in remediation, not detection
            # But for backward compatibility, allow global interval sweeps
            interval = int(_require("time.vmc_monitoring_interval_hours"))
            if interval <= 0:
                return False
            run_at_tick0 = bool(_require("vmc_detection.monitoring_sweep.run_at_tick0"))
            return (tick % interval == 0) and (run_at_tick0 or tick > 0)

    def step(self) -> List[DetectionResult]:
        """Periodic sweep entrypoint. Called once per model tick from model.step()."""
        net = getattr(self.model, "network", None)
        if net is None:
            return []

        tick = int(getattr(self.model.schedule, "steps", 0))

        results: List[DetectionResult] = []
        sweep_ran = False

        for vmc in self._vmc_agents():
            vmc_id = str(getattr(vmc, "unique_id", ""))

            if self._should_sweep(vmc, vmc_id, tick):
                sweep_ran = True
                try:
                    results.extend(self.processor.monitoring_sweep(vmc))
                except Exception:
                    logger.exception("VMC monitoring_sweep failed for %s", vmc_id)

        any_detected = any(r.detected for r in results)
        self._enqueue_if_detected(results)
        self._emit_audit_events(any_detected=any_detected, sweep_ran=sweep_ran)
        return results

    def detect_changes(self, controls: List[Any], change_severity: float, reason: str = "change_event") -> List[DetectionResult]:
        """On-demand detection during change events. Enqueues detected variants and emits finding event."""
        net = getattr(self.model, "network", None)
        if net is None or not controls:
            return []

        results: List[DetectionResult] = []
        for ctrl in controls:
            cid = str(getattr(ctrl, "unique_id", ""))
            if not cid:
                continue

            vmcs = net.get_monitoring_vmcs(cid) or []
            for vmc in vmcs:
                try:
                    results.extend(self.processor.detect_changes(vmc, [ctrl], change_severity=float(change_severity), reason=reason))
                except Exception:
                    logger.exception("VMC detect_changes failed for vmc=%s control=%s", getattr(vmc, "unique_id", "VMC"), cid)

        any_detected = any(r.detected for r in results)
        self._enqueue_if_detected(results)

        if any_detected:
            names = _require("vmc_detection.monitoring_sweep.audit_event_names")
            finding = str(names.get("finding", "")).strip()
            if finding and hasattr(self.model, "record_org_event"):
                self.model.record_org_event(finding)

        return results
