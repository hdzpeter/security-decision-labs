"""
Configuration loader for the TEF estimator.

Loads bundled defaults from config.yaml, then merges user overrides
from ~/.tef-estimator/config.yaml if present.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


_BUNDLED_CONFIG = Path(__file__).parent / "config.yaml"
_USER_CONFIG = Path.home() / ".tef-estimator" / "config.yaml"

_bundled_defaults: dict | None = None


def _get_bundled_defaults() -> dict:
    global _bundled_defaults
    if _bundled_defaults is None:
        with open(_BUNDLED_CONFIG) as f:
            _bundled_defaults = yaml.safe_load(f)
    return _bundled_defaults


@dataclass
class SusceptibilityPrior:
    low: float
    mode: float
    high: float


@dataclass
class DampeningParams:
    factor_k: float
    vector_k: float
    max_composite: float


@dataclass
class CredibilityKParams:
    exploitation: float
    credential: float
    phishing: float
    supply_chain: float


@dataclass
class TEFConfig:
    susceptibility_prior: SusceptibilityPrior = field(
        default_factory=lambda: SusceptibilityPrior(
            **_get_bundled_defaults()["susceptibility_prior"]
        )
    )
    dampening: DampeningParams = field(
        default_factory=lambda: DampeningParams(
            **_get_bundled_defaults()["dampening"]
        )
    )
    credibility_k: CredibilityKParams = field(
        default_factory=lambda: CredibilityKParams(
            **_get_bundled_defaults()["credibility_k"]
        )
    )

    @classmethod
    def from_dict(cls, d: dict) -> TEFConfig:
        defaults = _get_bundled_defaults()
        sp = {**defaults["susceptibility_prior"], **d.get("susceptibility_prior", {})}
        dp = {**defaults["dampening"], **d.get("dampening", {})}
        ck = {**defaults["credibility_k"], **d.get("credibility_k", {})}
        cfg = cls()
        cfg.susceptibility_prior = SusceptibilityPrior(**sp)
        cfg.dampening = DampeningParams(**dp)
        cfg.credibility_k = CredibilityKParams(**ck)
        return cfg

    def to_dict(self) -> dict:
        return {
            "susceptibility_prior": {
                "low": self.susceptibility_prior.low,
                "mode": self.susceptibility_prior.mode,
                "high": self.susceptibility_prior.high,
            },
            "dampening": {
                "factor_k": self.dampening.factor_k,
                "vector_k": self.dampening.vector_k,
                "max_composite": self.dampening.max_composite,
            },
            "credibility_k": {
                "exploitation": self.credibility_k.exploitation,
                "credential": self.credibility_k.credential,
                "phishing": self.credibility_k.phishing,
                "supply_chain": self.credibility_k.supply_chain,
            },
        }


def _deep_merge(base: dict, overrides: dict) -> dict:
    merged = dict(base)
    for k, v in overrides.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def load_config(user_path: Path | None = None) -> TEFConfig:
    """Load config from bundled defaults, merged with user overrides."""
    base = dict(_get_bundled_defaults())

    user_file = user_path or _USER_CONFIG
    if user_file.exists():
        with open(user_file) as f:
            user = yaml.safe_load(f) or {}
        base = _deep_merge(base, user)

    return TEFConfig.from_dict(base)


_cached_config: TEFConfig | None = None


def get_config() -> TEFConfig:
    """Return the cached config, loading on first access."""
    global _cached_config
    if _cached_config is None:
        _cached_config = load_config()
    return _cached_config


def reset_config() -> None:
    """Clear cached config (for testing or after user edits)."""
    global _cached_config
    _cached_config = None
