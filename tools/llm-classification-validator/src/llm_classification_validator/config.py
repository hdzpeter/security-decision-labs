"""Configuration loading and threshold management.

All default values are loaded from eval_defaults.json (the single source
of truth). Users can override via YAML or Python dataclasses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).parent
_DEFAULTS = json.loads((_HERE / "eval_defaults.json").read_text())

_BOOT = _DEFAULTS["bootstrap"]
_COH = _DEFAULTS["coherence"]
_CON = _DEFAULTS["consistency"]
_CONV = _DEFAULTS["convergent"]
_ADV = _DEFAULTS["adversarial"]
_STAB = _DEFAULTS["stability"]
_SAMP = _DEFAULTS["sampling"]
_RUN = _DEFAULTS["runner"]


@dataclass
class ThresholdConfig:
    """A single metric threshold with target and minimum levels.

    - At or above `target`: PASS
    - Between `minimum` and `target`: MARGINAL
    - Below `minimum`: FAIL
    """

    metric: str
    target: float
    minimum: float


@dataclass
class BootstrapConfig:
    """Bootstrap CI settings."""

    iterations: int = _BOOT["iterations"]
    confidence: float = _BOOT["confidence"]
    seed: int = _BOOT["seed"]


@dataclass
class CoherenceConfig:
    """Configuration for Dimension 1: coherence analysis."""

    thresholds: list[ThresholdConfig] = field(default_factory=lambda: [
        ThresholdConfig(**t) for t in _COH["thresholds"]
    ])
    bootstrap: BootstrapConfig = field(default_factory=BootstrapConfig)


@dataclass
class ConsistencyConfig:
    """Configuration for Dimension 2: rule-based consistency."""

    fail_on_error: bool = _CON["fail_on_error"]
    fail_on_warning: bool = _CON["fail_on_warning"]
    pass_rate_target: float = _CON["pass_rate_target"]
    pass_rate_minimum: float = _CON["pass_rate_minimum"]


@dataclass
class ConvergentConfig:
    """Configuration for Dimension 3: convergent validity."""

    thresholds: list[ThresholdConfig] = field(default_factory=lambda: [
        ThresholdConfig(**t) for t in _CONV["thresholds"]
    ])
    bootstrap: BootstrapConfig = field(default_factory=BootstrapConfig)


@dataclass
class AdversarialConfig:
    """Configuration for Dimension 4: adversarial edge cases."""

    discrimination_target: float = _ADV["discrimination_target"]
    discrimination_minimum: float = _ADV["discrimination_minimum"]
    ambiguity_target: float = _ADV["ambiguity_target"]
    ambiguity_minimum: float = _ADV["ambiguity_minimum"]
    combined_target: float = _ADV["combined_target"]
    combined_minimum: float = _ADV["combined_minimum"]
    discrimination_weight: float = _ADV["discrimination_weight"]
    ambiguity_weight: float = _ADV["ambiguity_weight"]


@dataclass
class StabilityConfig:
    """Configuration for Dimension 5: stability and sensitivity."""

    thresholds: list[ThresholdConfig] = field(default_factory=lambda: [
        ThresholdConfig(**t) for t in _STAB["thresholds"]
    ])
    false_change_max: float = _STAB["false_change_max"]
    bootstrap: BootstrapConfig = field(default_factory=BootstrapConfig)


@dataclass
class SamplingConfig:
    """Configuration for stratified expert review sampling."""

    min_per_stratum: int = _SAMP["min_per_stratum"]
    min_total: int = _SAMP["min_total"]
    confidence: float = _SAMP["confidence"]
    seed: int = _SAMP["seed"]


@dataclass
class RunnerConfig:
    """Configuration for the evaluation runner."""

    max_workers: int = _RUN["max_workers"]
    parallel_advanced: bool = _RUN["parallel_advanced"]


@dataclass
class EvalConfig:
    """Top-level evaluation configuration."""

    coherence: CoherenceConfig = field(default_factory=CoherenceConfig)
    consistency: ConsistencyConfig = field(default_factory=ConsistencyConfig)
    convergent: ConvergentConfig = field(default_factory=ConvergentConfig)
    adversarial: AdversarialConfig = field(default_factory=AdversarialConfig)
    stability: StabilityConfig = field(default_factory=StabilityConfig)
    sampling: SamplingConfig = field(default_factory=SamplingConfig)
    runner: RunnerConfig = field(default_factory=RunnerConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalConfig:
        """Build config from a nested dictionary (e.g. parsed YAML)."""
        config = cls()
        section_map = {
            "coherence": config.coherence,
            "consistency": config.consistency,
            "convergent": config.convergent,
            "adversarial": config.adversarial,
            "stability": config.stability,
            "sampling": config.sampling,
            "runner": config.runner,
        }
        for section_name, section_obj in section_map.items():
            if section_name in data:
                _update_dataclass(section_obj, data[section_name])
        return config

    @classmethod
    def from_yaml(cls, path: str | Path) -> EvalConfig:
        """Load configuration from a YAML file.

        Falls back to defaults if the file is absent or PyYAML is not
        installed.
        """
        p = Path(path)
        if not p.is_file():
            return cls()
        try:
            import yaml
        except ImportError:
            return cls()
        with open(p) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return cls()
        return cls.from_dict(data)


def _update_dataclass(obj: Any, values: dict[str, Any]) -> None:
    """Update dataclass fields from a dict, handling nested structures."""
    for key, val in values.items():
        if not hasattr(obj, key):
            continue
        current = getattr(obj, key)
        if isinstance(current, BootstrapConfig) and isinstance(val, dict):
            _update_dataclass(current, val)
        elif key == "thresholds" and isinstance(val, list):
            setattr(obj, key, [
                ThresholdConfig(**item) if isinstance(item, dict) else item
                for item in val
            ])
        else:
            setattr(obj, key, val)
