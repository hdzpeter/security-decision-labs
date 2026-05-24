"""src/processing/dsc_decision.py

DSC Decision Model implementation.

Supports two modes:
1) table   : 32-cell conditional probability lookup
2) logistic: logistic regression with calibratable coefficients

"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum, auto

import numpy as np

from ..config import get_config

logger = logging.getLogger(__name__)
cfg = get_config()


def _require(key: str):
    v = cfg.get(key, None)
    if v is None:
        raise ValueError(f"Missing required config key: {key}")
    return v


class DSCModelType(Enum):
    TABLE = auto()
    LOGISTIC = auto()


@dataclass
class DSCDimensionResult:
    dimension: str
    intrinsic_success: bool
    dsc_correction_attempted: bool
    dsc_correction_success: bool
    final_success: bool


class DSCDecisionModel:
    """Implements the FAIR-CAM DSC decision flowthrough process."""

    DSC_DIMENSIONS = ["expectation_alignment", "awareness", "capability", "situational", "incentive"]

    def __init__(self, model: "FAIRCAMModel"):
        self.model = model
        self.call_count = 0
        # Per-entity stream isolation for marginal value analysis (see STREAM_ISOLATION.md)
        self._streams = getattr(model, "streams", None)

        mode = str(_require("dsc_decision.mode")).strip().lower()
        if mode not in ("table", "logistic"):
            raise ValueError("dsc_decision.mode must be 'table' or 'logistic'")
        self.model_type = DSCModelType.TABLE if mode == "table" else DSCModelType.LOGISTIC

        # Table config (required in all modes, used for TABLE mode)
        from ..data.conditional_probs import load_conditional_prob_table_from_config
        self.conditional_prob_table = load_conditional_prob_table_from_config()

        # Logistic mode coefficients (required if mode==logistic)
        self.logistic_coefficients: Optional[Dict[str, float]] = None
        if self.model_type == DSCModelType.LOGISTIC:
            coeffs = cfg.get_section("dsc_decision").get("logistic_coefficients", None)
            if not coeffs:
                raise ValueError("dsc_decision.logistic_coefficients is required in logistic mode")
            from ..data.dsc_calibration import validate_coefficients
            self.logistic_coefficients = validate_coefficients(coeffs)

        # Mapping from dimension -> DSC control types (required; no hard-coded)
        mapping = cfg.get_section("dsc_decision").get("dimension_to_control_types", None)
        if not mapping or not isinstance(mapping, dict):
            raise ValueError("dsc_decision.dimension_to_control_types is required (no hard-coded defaults).")
        self.dimension_to_control_types = mapping

        # Logistic factor values (used in logistic mode when converting boolean results into continuous factors)
        self._logistic_factor_values = cfg.get_section("dsc_decision").get("logistic_factor_values", None)
        if self.model_type == DSCModelType.LOGISTIC:
            if not self._logistic_factor_values or not isinstance(self._logistic_factor_values, dict):
                raise ValueError("dsc_decision.logistic_factor_values is required in logistic mode")
            for k in ("success", "failure"):
                if k not in self._logistic_factor_values:
                    raise ValueError(f"dsc_decision.logistic_factor_values missing key: {k}")

        # Defaults for optional query inputs
        defaults = cfg.get_section("dsc_decision").get("defaults", None)
        if not defaults or not isinstance(defaults, dict):
            raise ValueError("Missing required config section: dsc_decision.defaults")
        for k in ("risk_magnitude", "time_pressure"):
            if k not in defaults:
                raise ValueError(f"dsc_decision.defaults missing key: {k}")
        self._defaults = defaults

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query_decision_alignment(
        self,
        personnel,
        effective_attributes=None,
        risk_magnitude: Optional[float] = None,
        time_pressure: Optional[float] = None,
    ) -> bool:
        """Return True if decision is aligned (correct), False if misaligned."""
        self.call_count += 1

        if risk_magnitude is None:
            risk_magnitude = float(self._defaults["risk_magnitude"])
        if time_pressure is None:
            time_pressure = float(self._defaults["time_pressure"])

        if effective_attributes is None:
            if not hasattr(personnel, "get_effective_attributes"):
                raise ValueError("Personnel agent must implement get_effective_attributes()")
            effective_attributes = personnel.get_effective_attributes()

        # Evaluate each dimension
        dimension_results: Dict[str, DSCDimensionResult] = {}
        for dimension in self.DSC_DIMENSIONS:
            dimension_results[dimension] = self._evaluate_dimension(personnel, effective_attributes, dimension)

        # Probability of misalignment
        if self.model_type == DSCModelType.TABLE:
            p_misaligned = self._get_table_probability(dimension_results)
        else:
            p_misaligned = self._get_logistic_probability(dimension_results, float(risk_magnitude), float(time_pressure))

        # Final Bernoulli trial (keyed to personnel so removing a control
        # doesn't shift this draw — see STREAM_ISOLATION.md)
        from ..data.distributions import bernoulli_trial
        pid = str(getattr(personnel, "unique_id", "?"))
        rng = self._streams.get(f"dsc_align:{pid}") if self._streams else self.model.random
        aligned = not bernoulli_trial(float(p_misaligned), rng=rng)

        logger.debug(
            "DSC decision for %s: aligned=%s p_misalign=%.3f mode=%s",
            getattr(personnel, "unique_id", "?"),
            aligned,
            p_misaligned,
            self.model_type.name,
        )

        # Store last decision details for causal chain retrieval
        self._last_decision_detail = {
            "personnel_id": str(getattr(personnel, "unique_id", "?")),
            "aligned": aligned,
            "p_misaligned": round(float(p_misaligned), 4),
            "model_type": self.model_type.name.lower(),
            "dimensions": {
                d: {
                    "intrinsic_success": r.intrinsic_success,
                    "dsc_correction_attempted": r.dsc_correction_attempted,
                    "dsc_correction_success": r.dsc_correction_success,
                    "final_success": r.final_success,
                }
                for d, r in dimension_results.items()
            },
        }

        return aligned

    def get_last_decision_detail(self) -> Optional[Dict]:
        """Return details of the most recent DSC decision for causal chain inclusion."""
        return getattr(self, "_last_decision_detail", None)

    # ------------------------------------------------------------------
    # Table mode
    # ------------------------------------------------------------------

    def _get_table_probability(self, dimension_results: Dict[str, DSCDimensionResult]) -> float:
        from ..data.conditional_probs import get_misalignment_probability

        g = dimension_results["expectation_alignment"].final_success
        a = dimension_results["awareness"].final_success
        c = dimension_results["capability"].final_success
        s = dimension_results["situational"].final_success
        i = dimension_results["incentive"].final_success

        return float(get_misalignment_probability(g, a, c, s, i, table=self.conditional_prob_table))

    # ------------------------------------------------------------------
    # Logistic mode
    # ------------------------------------------------------------------

    def _get_logistic_probability(
        self,
        dimension_results: Dict[str, DSCDimensionResult],
        risk_magnitude: float,
        time_pressure: float,
    ) -> float:
        from ..data.dsc_calibration import DSCFactors, calculate_misalignment_probability_logistic

        coeffs = self.logistic_coefficients
        if not coeffs:
            raise ValueError("Internal error: logistic coefficients missing in logistic mode")

        success_val = float(self._logistic_factor_values["success"])
        failure_val = float(self._logistic_factor_values["failure"])

        factors = DSCFactors(
            expectation_alignment=success_val if dimension_results["expectation_alignment"].final_success else failure_val,
            awareness=success_val if dimension_results["awareness"].final_success else failure_val,
            capability=success_val if dimension_results["capability"].final_success else failure_val,
            situational=success_val if dimension_results["situational"].final_success else failure_val,
            incentive=success_val if dimension_results["incentive"].final_success else failure_val,
            risk_magnitude=float(risk_magnitude),
            time_pressure=float(time_pressure),
        )
        p_misaligned, _ = calculate_misalignment_probability_logistic(factors, coeffs)
        return float(p_misaligned)

    # ------------------------------------------------------------------
    # Dimension evaluation
    # ------------------------------------------------------------------

    def _evaluate_dimension(self, personnel, effective_attributes, dimension: str) -> DSCDimensionResult:
        """
        1) Bernoulli trial on intrinsic attribute
        2) If fails, try DSC correction (formal DSC or informal incentives)
        """
        from ..data.distributions import bernoulli_trial

        # effective_attributes is a dict (from PersonnelAgent.get_effective_attributes())
        attr_value = effective_attributes[dimension] if isinstance(effective_attributes, dict) else getattr(effective_attributes, dimension)
        pid = str(getattr(personnel, "unique_id", "?"))
        rng = self._streams.get(f"dsc_attr:{pid}:{dimension}") if self._streams else self.model.random
        intrinsic_success = bernoulli_trial(float(attr_value), rng=rng)

        dsc_correction_attempted = False
        dsc_correction_success = False

        if not intrinsic_success:
            if dimension == "incentive":
                dsc_correction_attempted = True
                dsc_correction_success = self._check_informal_incentives(personnel)
            else:
                linked_dscs = self._get_dscs_for_dimension(personnel, dimension)
                if linked_dscs:
                    dsc_correction_attempted = True
                    for dsc in linked_dscs:
                        # Variant DSCs still have degraded efficacy (KB §01: OpEff
                        # blends IntEff and VarEff weighted by Reliability). Use
                        # current_efficacy which is already set to the variant
                        # efficacy value when the control enters variant state.
                        dsc_id = str(getattr(dsc, "unique_id", "?"))
                        dsc_rng = self._streams.get(f"dsc_correct:{dsc_id}") if self._streams else self.model.random
                        if bernoulli_trial(float(getattr(dsc, "current_efficacy", 0.0)), rng=dsc_rng):
                            dsc_correction_success = True
                            break

        final_success = bool(intrinsic_success or dsc_correction_success)

        return DSCDimensionResult(
            dimension=dimension,
            intrinsic_success=bool(intrinsic_success),
            dsc_correction_attempted=bool(dsc_correction_attempted),
            dsc_correction_success=bool(dsc_correction_success),
            final_success=final_success,
        )

    def _get_dscs_for_dimension(self, personnel, dimension: str) -> List:
        linked_dscs = self.model.network.get_dscs_for_personnel(getattr(personnel, "unique_id", ""))
        valid_types = self.dimension_to_control_types.get(dimension, []) or []
        return [dsc for dsc in (linked_dscs or []) if getattr(dsc, "control_type", None) in valid_types]

    def _check_informal_incentives(self, personnel) -> bool:
        """
        Informal incentive correction via peers:
        efficacy = average of peer incentive attributes.
        """
        from ..data.distributions import bernoulli_trial

        peers = self.model.network.get_peer_personnel(getattr(personnel, "unique_id", ""))
        if not peers:
            return False

        vals = []
        for p in peers:
            ba = getattr(p, "base_attributes", None)
            if ba is not None and hasattr(ba, "incentive"):
                vals.append(float(ba.incentive))
        if not vals:
            return False

        avg_incentive = float(np.mean(vals))
        pid = str(getattr(personnel, "unique_id", "?"))
        rng = self._streams.get(f"dsc_incentive:{pid}") if self._streams else self.model.random
        return bool(bernoulli_trial(avg_incentive, rng=rng))