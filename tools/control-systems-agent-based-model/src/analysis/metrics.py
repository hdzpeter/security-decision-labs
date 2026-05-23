"""
Metrics collection, reporting, and risk appetite assessment.

Implements:
- MetricsState: per-run event tracking
- RiskAppetiteAssessment: exceedance probability computation (KB §05)
- Control reliability and operational efficacy (KB §01, §05)
- Loss distribution percentiles (P50, P90, P95, P99)
- KRI / KPI decomposition aligned with board reporting spec
"""

from mesa.datacollection import DataCollector
from typing import Dict, Any, List, Optional, Tuple
import math
import logging

from ..config import get_config

logger = logging.getLogger(__name__)

cfg = get_config()


# ---------------------------------------------------------------------------
# MetricsState — per-run event accumulator
# ---------------------------------------------------------------------------

class MetricsState:
    def __init__(self):
        self.total_gross_losses: float = 0.0
        self.total_net_losses: float = 0.0
        self.total_primary_losses: float = 0.0
        self.total_secondary_losses: float = 0.0

        # Contact attempts are scheduled by ThreatAgent. Avoidance may prevent
        # a *successful* contact. We track both.
        self.total_contact_attempts: int = 0
        self.total_contact_events: int = 0
        self.total_breach_events: int = 0
        self.total_loss_events: int = 0
        self.total_variance_events: int = 0
        self.total_lec_variance_events: int = 0
        self.total_vmc_variance_events: int = 0

        # Prevention-stage outcomes
        self.total_avoided_contacts: int = 0
        self.total_deterred_events: int = 0
        self.total_resisted_events: int = 0

        self.cumulative_opex: float = 0.0
        self.cumulative_capex: float = 0.0

        self.contact_event_log: List[Dict[str, Any]] = []
        self.breach_event_log: List[Dict[str, Any]] = []
        self.loss_event_log: List[Dict[str, Any]] = []

        self.breaches_by_ta: Dict[str, int] = {}
        self.orphan_breaches_by_ta: Dict[str, int] = {}
        self.orphan_breach_events: int = 0
        self.orphan_breach_severity_sum: float = 0.0

        self.compromised_ta_hours: int = 0
        self.compromised_ta_hours_by_ta: Dict[str, int] = {}

        # Detection AND gate metrics
        # Tracks how the detection AND dependency affects loss events.
        self.detection_and_gate_successes: int = 0
        self.detection_and_gate_failures: int = 0
        self.detection_probability_failures: int = 0

    def record_contact_event(self, result):
        self.contact_event_log.append({
            "tick": getattr(result, "tick", 0),
            "threat_id": getattr(result, "threat_id", ""),
            "tech_asset_id": getattr(result, "tech_asset_id", ""),
            "success": getattr(result, "success", False),
            "sophistication": getattr(result, "sophistication", 0.0),
            "failed_controls": list(getattr(result, "failed_controls", []) or []),
            "blocking_control": getattr(result, "blocking_control", None),
        })

    def record_breach_event(self, result):
        self.breach_event_log.append({
            "tick": getattr(result, "tick", 0),
            "threat_id": getattr(result, "threat_id", ""),
            "tech_asset_id": getattr(result, "tech_asset_id", ""),
            "failed_controls": list(getattr(result, "failed_controls", []) or []),
        })

    def record_loss_event(self, business_asset_id: str, primary_loss: float, secondary_loss: float, tick: int):
        self.total_primary_losses += float(primary_loss)
        self.total_secondary_losses += float(secondary_loss)
        gross = float(primary_loss) + float(secondary_loss)
        self.total_gross_losses += gross
        self.total_net_losses += gross

        self.loss_event_log.append({
            "tick": tick,
            "business_asset_id": business_asset_id,
            "primary_loss": float(primary_loss),
            "secondary_loss": float(secondary_loss),
            "gross_loss": gross,
        })

    def to_summary_dict(self) -> Dict[str, Any]:
        avg_orphan_severity = (
            self.orphan_breach_severity_sum / self.orphan_breach_events
            if self.orphan_breach_events else 0.0
        )
        return {
            "total_gross_losses": self.total_gross_losses,
            "total_net_losses": self.total_net_losses,
            "total_primary_losses": self.total_primary_losses,
            "total_secondary_losses": self.total_secondary_losses,

            "total_contact_attempts": self.total_contact_attempts,
            "total_contact_events": self.total_contact_events,
            "total_avoided_contacts": self.total_avoided_contacts,
            "total_deterred_events": self.total_deterred_events,
            "total_resisted_events": self.total_resisted_events,

            "total_breach_events": self.total_breach_events,
            "total_loss_events": self.total_loss_events,
            "total_variance_events": self.total_variance_events,
            "total_lec_variance_events": self.total_lec_variance_events,
            "total_vmc_variance_events": self.total_vmc_variance_events,

            "cumulative_opex": self.cumulative_opex,
            "cumulative_capex": self.cumulative_capex,

            "breach_rate": (self.total_breach_events / self.total_contact_events) if self.total_contact_events else 0.0,
            "loss_per_breach": (self.total_gross_losses / self.total_breach_events) if self.total_breach_events else 0.0,

            "orphan_breach_events": self.orphan_breach_events,
            "avg_orphan_breach_severity": avg_orphan_severity,
            "compromised_ta_hours": self.compromised_ta_hours,

            # Detection AND gate
            "detection_and_gate_successes": self.detection_and_gate_successes,
            "detection_and_gate_failures": self.detection_and_gate_failures,
            "detection_probability_failures": self.detection_probability_failures,
            "detection_success_rate": (
                self.detection_and_gate_successes
                / (self.detection_and_gate_successes + self.detection_and_gate_failures + self.detection_probability_failures)
                if (self.detection_and_gate_successes + self.detection_and_gate_failures + self.detection_probability_failures) > 0
                else 0.0
            ),
        }


# ---------------------------------------------------------------------------
# Risk Appetite Assessment
# ---------------------------------------------------------------------------
# Risk appetite = (loss magnitude threshold) + (max probability of exceeding
# it) + (timeframe).  This class computes exceedance probabilities from the
# simulation's realized loss events and control state data.
#
#   P(Exceed Threshold) = number_of_events_exceeding / total_events
#
# For single-run analysis, this is an empirical frequency.  For batch
# (multi-iteration) analysis, each run provides one observation of annual
# loss, yielding a proper exceedance curve.

class RiskAppetiteAssessment:
    """Compute risk appetite alignment metrics from simulation data.

    Can be used in two modes:
    - **Single-run**: Assess loss events within one simulation run
    - **Batch (cross-run)**: Aggregate per-run annual losses for exceedance curve
    """

    def __init__(self, thresholds: Optional[List[Dict[str, Any]]] = None):
        """Initialize with risk appetite thresholds.

        Args:
            thresholds: List of appetite definitions, each with:
                - name: Human-readable label (e.g., "Breach > $5M")
                - loss_threshold: Dollar amount threshold
                - max_probability: Maximum acceptable exceedance probability (e.g., 0.05)
                - timeframe_hours: Observation window in hours (default: 8760 = 1 year)
                - loss_type: "gross" | "primary" | "secondary" | "any_event" (default: "gross")
        """
        if thresholds is None:
            # Load from YAML config, or use sensible defaults
            thresholds = cfg.get("risk_appetite.thresholds", None) or []
        self.thresholds = thresholds

    # ---- Single-run analysis ----

    def assess_single_run(self, metrics_state: "MetricsState", total_ticks: int) -> Dict[str, Any]:
        """Assess risk appetite alignment from a single simulation run.

        Returns per-threshold assessment plus aggregate loss distribution stats.
        """
        loss_log = metrics_state.loss_event_log
        if not loss_log:
            return self._empty_assessment()

        # Extract per-event loss amounts
        gross_losses = [evt["gross_loss"] for evt in loss_log]
        primary_losses = [evt["primary_loss"] for evt in loss_log]
        secondary_losses = [evt["secondary_loss"] for evt in loss_log]

        # Loss distribution statistics (pair Median with Mean, add P90)
        loss_distribution = _compute_distribution_stats(gross_losses)

        # Per-threshold exceedance
        threshold_results = []
        for thresh in self.thresholds:
            result = self._evaluate_threshold(
                threshold=thresh,
                loss_log=loss_log,
                total_ticks=total_ticks,
            )
            threshold_results.append(result)

        # Annualized loss exposure (ALE)
        hours_per_year = float(cfg.get("time.hours_per_year", 8760))
        years_simulated = total_ticks / hours_per_year if total_ticks > 0 else 1.0
        ale = sum(gross_losses) / years_simulated if years_simulated > 0 else 0.0

        return {
            "loss_distribution": loss_distribution,
            "primary_loss_distribution": _compute_distribution_stats(primary_losses),
            "secondary_loss_distribution": _compute_distribution_stats(secondary_losses),
            "annualized_loss_exposure": ale,
            "years_simulated": years_simulated,
            "total_loss_events": len(gross_losses),
            "threshold_assessments": threshold_results,
            "appetite_aligned": all(
                r.get("within_appetite", True) for r in threshold_results
            ),
        }

    def _evaluate_threshold(
        self,
        threshold: Dict[str, Any],
        loss_log: List[Dict[str, Any]],
        total_ticks: int,
    ) -> Dict[str, Any]:
        """Evaluate a single risk appetite threshold against loss data."""
        name = threshold.get("name", "unnamed")
        loss_threshold = float(threshold.get("loss_threshold", 0))
        max_prob = float(threshold.get("max_probability", 0.05))
        timeframe_hours = float(threshold.get("timeframe_hours", 8760))
        loss_type = str(threshold.get("loss_type", "gross")).lower()

        # Select loss values based on type
        if loss_type == "primary":
            losses = [evt["primary_loss"] for evt in loss_log]
        elif loss_type == "secondary":
            losses = [evt["secondary_loss"] for evt in loss_log]
        else:
            losses = [evt["gross_loss"] for evt in loss_log]

        # Count events exceeding the threshold
        exceeding_events = [l for l in losses if l > loss_threshold]
        n_exceeding = len(exceeding_events)
        n_total = len(losses)

        # Empirical exceedance probability (within this run)
        p_exceed_per_event = n_exceeding / n_total if n_total > 0 else 0.0

        # Annualized exceedance: how many events per year exceed the threshold
        hours_per_year = float(cfg.get("time.hours_per_year", 8760))
        years_simulated = total_ticks / hours_per_year if total_ticks > 0 else 1.0
        events_per_year = n_total / years_simulated if years_simulated > 0 else 0.0
        exceeding_per_year = n_exceeding / years_simulated if years_simulated > 0 else 0.0

        # P(at least one event exceeding threshold in timeframe)
        # Using Poisson approximation: P(N>=1) = 1 - e^(-lambda)
        # where lambda = exceeding_per_year * (timeframe_hours / hours_per_year)
        timeframe_years = timeframe_hours / hours_per_year
        lambda_exceed = exceeding_per_year * timeframe_years
        p_exceed_in_timeframe = 1.0 - math.exp(-lambda_exceed) if lambda_exceed > 0 else 0.0

        within_appetite = p_exceed_in_timeframe <= max_prob

        status = "aligned"
        if not within_appetite:
            status = "out_of_appetite"
        elif p_exceed_in_timeframe > max_prob * 0.8:
            status = "near_limit"

        return {
            "name": name,
            "loss_threshold": loss_threshold,
            "max_probability": max_prob,
            "timeframe_hours": timeframe_hours,
            "events_exceeding": n_exceeding,
            "events_total": n_total,
            "p_exceed_per_event": p_exceed_per_event,
            "p_exceed_in_timeframe": p_exceed_in_timeframe,
            "exceeding_events_per_year": exceeding_per_year,
            "within_appetite": within_appetite,
            "status": status,
            "worst_loss_exceeding": max(exceeding_events) if exceeding_events else 0.0,
        }

    # ---- Batch (cross-run) analysis ----

    @staticmethod
    def assess_batch(
        per_run_losses: List[float],
        thresholds: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Compute exceedance curve from per-run total annual losses.

        Args:
            per_run_losses: List of total annual gross losses, one per iteration.
            thresholds: Optional risk appetite thresholds to evaluate.

        Returns:
            Exceedance curve and per-threshold assessment.
        """
        if not per_run_losses:
            return {"error": "No per-run loss data provided"}

        n_runs = len(per_run_losses)
        sorted_losses = sorted(per_run_losses)

        # Loss distribution across runs
        distribution = _compute_distribution_stats(per_run_losses)

        # Exceedance curve: for each loss level L, P(annual_loss > L) = count(losses > L) / N
        # Provide at standard percentile points
        exceedance_curve = []
        test_points = sorted(set(
            [0] + [sorted_losses[int(p * n_runs / 100)] for p in range(0, 100, 5) if int(p * n_runs / 100) < n_runs]
            + [sorted_losses[-1]]
        ))
        for point in test_points:
            n_above = sum(1 for l in sorted_losses if l > point)
            exceedance_curve.append({
                "loss_level": point,
                "p_exceed": n_above / n_runs,
            })

        # Per-threshold assessment
        threshold_results = []
        if thresholds:
            for thresh in thresholds:
                loss_threshold = float(thresh.get("loss_threshold", 0))
                max_prob = float(thresh.get("max_probability", 0.05))
                n_exceeding = sum(1 for l in sorted_losses if l > loss_threshold)
                p_exceed = n_exceeding / n_runs

                status = "aligned"
                if p_exceed > max_prob:
                    status = "out_of_appetite"
                elif p_exceed > max_prob * 0.8:
                    status = "near_limit"

                threshold_results.append({
                    "name": thresh.get("name", "unnamed"),
                    "loss_threshold": loss_threshold,
                    "max_probability": max_prob,
                    "runs_exceeding": n_exceeding,
                    "total_runs": n_runs,
                    "p_exceed": p_exceed,
                    "within_appetite": p_exceed <= max_prob,
                    "status": status,
                })

        return {
            "n_runs": n_runs,
            "distribution": distribution,
            "exceedance_curve": exceedance_curve,
            "threshold_assessments": threshold_results,
            "appetite_aligned": all(
                r.get("within_appetite", True) for r in threshold_results
            ),
        }

    def _empty_assessment(self) -> Dict[str, Any]:
        return {
            "loss_distribution": _compute_distribution_stats([]),
            "primary_loss_distribution": _compute_distribution_stats([]),
            "secondary_loss_distribution": _compute_distribution_stats([]),
            "annualized_loss_exposure": 0.0,
            "years_simulated": 0.0,
            "total_loss_events": 0,
            "threshold_assessments": [],
            "appetite_aligned": True,
        }


# ---------------------------------------------------------------------------
# Control reliability and operational efficacy
# ---------------------------------------------------------------------------

def compute_control_reliability(
    model,
    control_id: str,
    total_ticks: int,
) -> Dict[str, Any]:
    """Compute observed reliability and operational efficacy for a control.

    Reliability: fraction of time the control was in 'normal' state.
    OpEff = Cov × [(Rel × IntEff) + ((1-Rel) × VarEff)]

    In the ABM, coverage is implicit in topology, so we report Cov=1.0
    for connected controls (the network topology encodes coverage).

    Args:
        model: The FAIR-CAM model instance.
        control_id: Unique ID of the control agent.
        total_ticks: Total simulation ticks elapsed.

    Returns:
        Dict with reliability, operational efficacy, and supporting data.
    """
    net = getattr(model, "network", None)
    if net is None:
        return {"error": f"No network available for control {control_id}"}

    agent = net.get_agent(control_id) if hasattr(net, "get_agent") else None
    if agent is None:
        return {"error": f"Control {control_id} not found"}

    # Count variance events from narrative
    nar = getattr(model, "narrative", None)
    variance_events = []
    if nar is not None:
        variance_events = nar.variance_by_control.get(control_id, [])

    # Compute actual time spent in variant state using variance→recovery pairs.
    # Each variance event lasts until the next recovery event for that control,
    # or until the end of the simulation if no recovery follows.
    recovery_events = []
    if nar is not None:
        recovery_events = nar.recovery_by_control.get(control_id, [])
    recovery_ticks = sorted(r.tick for r in recovery_events)

    total_variant_ticks = 0
    intended_eff = float(getattr(agent, "intended_efficacy", 0.5))
    variant_eff_sum = 0.0
    weighted_variant_eff = 0.0
    n_variance = len(variance_events)

    for v in variance_events:
        # Find next recovery after this variance event
        end_tick = total_ticks  # default: still variant at simulation end
        for rt in recovery_ticks:
            if rt > v.tick:
                end_tick = rt
                break
        duration = max(0, end_tick - v.tick)
        total_variant_ticks += duration
        variant_eff_sum += v.variant_efficacy
        weighted_variant_eff += v.variant_efficacy * duration

    # Reliability = fraction of time in normal state
    variant_fraction = min(1.0, total_variant_ticks / total_ticks) if total_ticks > 0 else 0.0
    reliability = 1.0 - variant_fraction

    # Time-weighted average variant efficacy (when in variant state)
    avg_variant_eff = weighted_variant_eff / total_variant_ticks if total_variant_ticks > 0 else 0.0

    # OpEff = Cov × [(Rel × IntEff) + ((1-Rel) × VarEff)]
    # Coverage = 1.0 (implicit in topology)
    coverage = 1.0
    op_eff = coverage * (reliability * intended_eff + (1.0 - reliability) * avg_variant_eff)

    return {
        "control_id": control_id,
        "intended_efficacy": intended_eff,
        "reliability": reliability,
        "avg_variant_efficacy": avg_variant_eff,
        "operational_efficacy": op_eff,
        "coverage": coverage,
        "variance_events": n_variance,
        "total_variant_hours": total_variant_ticks,
        "total_hours": total_ticks,
    }


def compute_all_control_reliability(model, total_ticks: int) -> List[Dict[str, Any]]:
    """Compute reliability for all control agents in the model."""
    net = getattr(model, "network", None)
    if net is None:
        return []

    results = []
    for node_id in net.G.nodes():
        agent = net.get_agent(str(node_id))
        if agent is None:
            continue
        # Only compute for control agents (LEC, VMC, DSC)
        uid = str(node_id).upper()
        if not (uid.startswith("LEC") or uid.startswith("VM") or uid.startswith("DSC")):
            continue
        result = compute_control_reliability(model, str(node_id), total_ticks)
        if "error" not in result:
            results.append(result)

    return results


# ---------------------------------------------------------------------------
# KRI / KPI decomposition
# ---------------------------------------------------------------------------

def compute_kris(metrics_state: "MetricsState", total_ticks: int) -> Dict[str, Any]:
    """Compute Key Risk Indicators from simulation data.

    KRIs measure risk outcomes (probability-focused, backward-looking).
    """
    hours_per_year = float(cfg.get("time.hours_per_year", 8760))
    years = total_ticks / hours_per_year if total_ticks > 0 else 1.0

    gross_losses = [evt["gross_loss"] for evt in metrics_state.loss_event_log]
    loss_dist = _compute_distribution_stats(gross_losses)

    # Susceptibility: breach_events / contact_events
    susceptibility = (
        metrics_state.total_breach_events / metrics_state.total_contact_events
        if metrics_state.total_contact_events > 0 else 0.0
    )

    # Loss Event Frequency (LEF): loss events per year
    lef = metrics_state.total_loss_events / years if years > 0 else 0.0

    # Breach frequency: breaches per year
    breach_freq = metrics_state.total_breach_events / years if years > 0 else 0.0

    return {
        "susceptibility": susceptibility,
        "loss_event_frequency_per_year": lef,
        "breach_frequency_per_year": breach_freq,
        "annualized_loss_exposure": sum(gross_losses) / years if years > 0 else 0.0,
        "loss_distribution": loss_dist,
        "detection_success_rate": (
            metrics_state.detection_and_gate_successes
            / (metrics_state.detection_and_gate_successes
               + metrics_state.detection_and_gate_failures
               + metrics_state.detection_probability_failures)
            if (metrics_state.detection_and_gate_successes
                + metrics_state.detection_and_gate_failures
                + metrics_state.detection_probability_failures) > 0
            else 0.0
        ),
    }


def compute_kpis(model, total_ticks: int) -> Dict[str, Any]:
    """Compute Key Performance Indicators from simulation data.

    KPIs measure control performance (process-focused, forward-looking).
    """
    ms = getattr(model, "metrics_state", None)
    if ms is None:
        return {"error": "No metrics state available"}

    hours_per_year = float(cfg.get("time.hours_per_year", 8760))
    years = total_ticks / hours_per_year if total_ticks > 0 else 1.0

    # Variance frequency (VF): variance events per year
    vf = ms.total_variance_events / years if years > 0 else 0.0
    lec_vf = ms.total_lec_variance_events / years if years > 0 else 0.0
    vmc_vf = ms.total_vmc_variance_events / years if years > 0 else 0.0

    # Control reliability metrics (per-control)
    control_reliability = compute_all_control_reliability(model, total_ticks)

    # Aggregate reliability
    reliabilities = [c["reliability"] for c in control_reliability if "reliability" in c]
    # Exclude time-based controls (intended_efficacy > 1, measured in hours not probability)
    # from operational efficacy aggregation — mixing hours with probabilities is meaningless.
    op_effs = [
        c["operational_efficacy"]
        for c in control_reliability
        if "operational_efficacy" in c and c.get("intended_efficacy", 0) <= 1.0
    ]

    # Block rate: contacts blocked / total contacts
    blocked = (
        ms.total_avoided_contacts + ms.total_deterred_events + ms.total_resisted_events
    )
    block_rate = blocked / ms.total_contact_events if ms.total_contact_events > 0 else 0.0

    return {
        "variance_frequency_per_year": vf,
        "lec_variance_frequency_per_year": lec_vf,
        "vmc_variance_frequency_per_year": vmc_vf,
        "block_rate": block_rate,
        "avoidance_rate": ms.total_avoided_contacts / ms.total_contact_events if ms.total_contact_events > 0 else 0.0,
        "deterrence_rate": ms.total_deterred_events / ms.total_contact_events if ms.total_contact_events > 0 else 0.0,
        "resistance_rate": ms.total_resisted_events / ms.total_contact_events if ms.total_contact_events > 0 else 0.0,
        "control_reliability": {
            "mean": _safe_mean(reliabilities),
            "min": min(reliabilities) if reliabilities else 0.0,
            "p10": _percentile(reliabilities, 10),
            "p50": _percentile(reliabilities, 50),
        },
        "operational_efficacy": {
            "mean": _safe_mean(op_effs),
            "min": min(op_effs) if op_effs else 0.0,
            "p10": _percentile(op_effs, 10),
            "p50": _percentile(op_effs, 50),
        },
        "per_control": control_reliability,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_distribution_stats(values: List[float]) -> Dict[str, Any]:
    """Compute distribution statistics.
    """
    if not values:
        return {
            "count": 0, "sum": 0.0, "mean": 0.0, "median": 0.0,
            "std": 0.0, "min": 0.0, "max": 0.0,
            "p10": 0.0, "p25": 0.0, "p50": 0.0,
            "p75": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0,
        }

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mean = sum(sorted_vals) / n
    variance = sum((v - mean) ** 2 for v in sorted_vals) / n if n > 1 else 0.0
    std = math.sqrt(variance)

    return {
        "count": n,
        "sum": sum(sorted_vals),
        "mean": mean,
        "median": _percentile(sorted_vals, 50),
        "std": std,
        "min": sorted_vals[0],
        "max": sorted_vals[-1],
        "p10": _percentile(sorted_vals, 10),
        "p25": _percentile(sorted_vals, 25),
        "p50": _percentile(sorted_vals, 50),
        "p75": _percentile(sorted_vals, 75),
        "p90": _percentile(sorted_vals, 90),
        "p95": _percentile(sorted_vals, 95),
        "p99": _percentile(sorted_vals, 99),
    }


def _percentile(sorted_values: List[float], p: float) -> float:
    """Compute p-th percentile using linear interpolation (pre-sorted input)."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    # Linear interpolation
    k = (p / 100.0) * (n - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[int(f)] * (c - k) + sorted_values[int(c)] * (k - f)


def _safe_mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


# ---------------------------------------------------------------------------
# DataCollector factory (Mesa integration)
# ---------------------------------------------------------------------------

def create_data_collector(model) -> DataCollector:
    def _compromised_business_assets_count(m) -> int:
        """Count compromised business assets.

        Some versions of the model track `compromised_business_assets` directly.
        Otherwise, derive it from compromised tech assets via the network
        relationship (TechAsset hosts BusinessAsset).
        """

        # Preferred: explicit tracking on the model
        cba = getattr(m, "compromised_business_assets", None)
        if isinstance(cba, (set, list, tuple)):
            try:
                return len(cba)
            except Exception:
                pass

        # Derive from compromised tech assets and topology
        ta_ids = getattr(m, "compromised_tech_assets", None)
        if not isinstance(ta_ids, (set, list, tuple)):
            return 0

        net = getattr(m, "network", None)
        get_bas = None
        if net is not None:
            # Support both names to avoid tight coupling.
            get_bas = getattr(net, "get_business_assets", None) or getattr(net, "get_hosted_business_assets", None)

        bas_ids = set()
        if callable(get_bas):
            for ta_id in ta_ids:
                try:
                    bas = get_bas(str(ta_id))
                except Exception:
                    bas = []

                # bas may be agent objects or plain IDs
                for b in bas or []:
                    if isinstance(b, str):
                        bas_ids.add(b)
                    else:
                        uid = getattr(b, "unique_id", None)
                        if uid is not None:
                            bas_ids.add(str(uid))

        return len(bas_ids)

    model_reporters = {
        "total_gross_losses": lambda m: m.metrics_state.total_gross_losses,
        "total_net_losses": lambda m: m.metrics_state.total_net_losses,
        "total_primary_losses": lambda m: m.metrics_state.total_primary_losses,
        "total_secondary_losses": lambda m: m.metrics_state.total_secondary_losses,

        "total_contact_attempts": lambda m: getattr(m.metrics_state, "total_contact_attempts", 0),
        "total_contact_events": lambda m: m.metrics_state.total_contact_events,
        "total_avoided_contacts": lambda m: getattr(m.metrics_state, "total_avoided_contacts", 0),
        "total_deterred_events": lambda m: getattr(m.metrics_state, "total_deterred_events", 0),
        "total_resisted_events": lambda m: getattr(m.metrics_state, "total_resisted_events", 0),
        "total_breach_events": lambda m: m.metrics_state.total_breach_events,
        "total_loss_events": lambda m: m.metrics_state.total_loss_events,
        "total_variance_events": lambda m: m.metrics_state.total_variance_events,
        "total_lec_variance_events": lambda m: getattr(m.metrics_state, "total_lec_variance_events", 0),
        "total_vmc_variance_events": lambda m: getattr(m.metrics_state, "total_vmc_variance_events", 0),

        "compromised_tech_assets_count": lambda m: len(getattr(m, "compromised_tech_assets", set()) or set()),
        "compromised_business_assets_count": _compromised_business_assets_count,

        "orphan_breach_events": lambda m: m.metrics_state.orphan_breach_events,
        "compromised_ta_hours": lambda m: m.metrics_state.compromised_ta_hours,
        "avg_orphan_breach_severity": lambda m: (
            (m.metrics_state.orphan_breach_severity_sum / m.metrics_state.orphan_breach_events)
            if m.metrics_state.orphan_breach_events else 0.0
        ),

        # Detection AND gate metrics
        "detection_and_gate_successes": lambda m: getattr(m.metrics_state, "detection_and_gate_successes", 0),
        "detection_and_gate_failures": lambda m: getattr(m.metrics_state, "detection_and_gate_failures", 0),
        "detection_probability_failures": lambda m: getattr(m.metrics_state, "detection_probability_failures", 0),
    }

    agent_reporters = {
        "state": lambda a: getattr(a, "state", None),
        "current_efficacy": lambda a: getattr(a, "current_efficacy", None),
        "intended_efficacy": lambda a: getattr(a, "intended_efficacy", None),
        "risk_state": lambda a: getattr(a, "risk_state", None),
    }

    return DataCollector(model_reporters=model_reporters, agent_reporters=agent_reporters)
