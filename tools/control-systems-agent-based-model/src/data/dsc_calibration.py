"""
DSC logistic regression calibration module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import logging
import numpy as np
from scipy.special import expit

from ..config import get_config

logger = logging.getLogger(__name__)

cfg = get_config()


def _require(key: str):
    v = cfg.get(key, None)
    if v is None:
        raise ValueError(f"Missing required config key: {key}")
    return v


@dataclass
class DSCFactors:
    """Input factors for logistic DSC decision model."""
    expectation_alignment: float
    awareness: float
    capability: float
    situational: float
    incentive: float
    risk_magnitude: float
    time_pressure: float


def validate_coefficients(coefficients: Dict[str, float]) -> Dict[str, float]:
    if not coefficients or not isinstance(coefficients, dict):
        raise ValueError("DSC logistic coefficients must be a non-empty dict")

    # Minimal set used by calculate_misalignment_probability_logistic
    required = {
        "intercept",
        "expectation_alignment",
        "awareness",
        "capability",
        "situational",
        "incentive",
        "risk_magnitude",
        "time_pressure",
        "awareness_x_capability",
    }
    missing = required - set(coefficients.keys())
    if missing:
        raise ValueError(f"Missing DSC logistic coefficients: {sorted(missing)}")

    # Cast to float
    return {k: float(v) for k, v in coefficients.items()}


def calculate_misalignment_probability_logistic(
    factors: DSCFactors,
    coefficients: Dict[str, float],
) -> Tuple[float, Dict[str, float]]:
    """Calculate P(misaligned) using logistic regression."""
    coefficients = validate_coefficients(coefficients)

    features = {
        "intercept": 1.0,
        "expectation_alignment": float(factors.expectation_alignment),
        "awareness": float(factors.awareness),
        "capability": float(factors.capability),
        "situational": float(factors.situational),
        "incentive": float(factors.incentive),
        "risk_magnitude": float(factors.risk_magnitude),
        "time_pressure": float(factors.time_pressure),
        "awareness_x_capability": float(factors.awareness) * float(factors.capability),
    }

    contributions: Dict[str, float] = {}
    logit = 0.0

    for feature_name, feature_value in features.items():
        coef = float(coefficients[feature_name])
        contribution = coef * feature_value
        contributions[feature_name] = contribution
        logit += contribution

    p_misaligned = float(expit(logit))
    return p_misaligned, contributions


def calibrate_from_observations(
    observations: List[Dict],
    prior_coefficients: Optional[Dict[str, float]] = None,
    regularization: Optional[float] = None,
) -> Dict[str, float]:
    """
    Calibrate logistic regression coefficients from observed decisions.

    If sklearn is unavailable or observations are insufficient, returns prior_coefficients.
    If prior_coefficients is missing, raises (to avoid hidden defaults).
    """
    try:
        from sklearn.linear_model import LogisticRegression
    except ImportError:
        if prior_coefficients is None:
            raise ValueError("sklearn not available and no prior_coefficients provided")
        return validate_coefficients(prior_coefficients)

    if len(observations) < 10:
        if prior_coefficients is None:
            raise ValueError("Insufficient observations and no prior_coefficients provided")
        return validate_coefficients(prior_coefficients)

    if regularization is None:
        regularization = float(_require("dsc_calibration.defaults.regularization"))

    X = []
    y = []

    # Defaults for observation records come from YAML (single place to tune).
    dflt = cfg.get_section("dsc_calibration").get("observation_defaults", {})
    def _d(key: str) -> float:
        if key not in dflt:
            raise ValueError(f"Missing required config: dsc_calibration.observation_defaults.{key}")
        return float(dflt[key])

    if "aligned" not in dflt:
        raise ValueError("Missing required config: dsc_calibration.observation_defaults.aligned")
    aligned_default = bool(dflt.get("aligned"))

    for obs in observations:
        features = [
            1.0,
            float(obs.get("awareness", _d("awareness"))),
            float(obs.get("capability", _d("capability"))),
            float(obs.get("situational", _d("situational"))),
            float(obs.get("incentive", _d("incentive"))),
            float(obs.get("risk_magnitude", _d("risk_magnitude"))),
            float(obs.get("time_pressure", _d("time_pressure"))),
            float(obs.get("awareness", _d("awareness"))) * float(obs.get("capability", _d("capability"))),
        ]
        X.append(features)
        y.append(0 if bool(obs.get("aligned", aligned_default)) else 1)

    X = np.array(X, dtype=float)
    y = np.array(y, dtype=int)

    model = LogisticRegression(
        fit_intercept=False,
        C=1.0 / float(regularization),
        max_iter=1000,
        solver="lbfgs",
    )
    model.fit(X, y)

    feature_names = [
        "intercept",
        "awareness",
        "capability",
        "situational",
        "incentive",
        "risk_magnitude",
        "time_pressure",
        "awareness_x_capability",
    ]

    out = dict(zip(feature_names, model.coef_[0]))
    return validate_coefficients(out)