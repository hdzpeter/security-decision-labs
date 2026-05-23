# src/config/loader.py
"""
Configuration loader.

Loads configuration from YAML files and provides easy access to parameters.

Key behaviors:
- Config location precedence:
    1) FAIR_CAM_CONFIG env var (absolute or relative to repo root)
    2) explicit config_path passed to get_config(...) / ConfigLoader(...)
    3) default: <repo_root>/inputs/model_config.yaml
- repo_root is inferred from this file location (src/config/loader.py -> repo root)
- paths.project_root in YAML defines the "project_root" used to resolve relative paths
- resolve_path(...) resolves relative paths using project_root (default) / repo_root / config dir

Design notes:
- This module provides *path resolution* and *config access* only.
- It does not perform simulation logic or data transformation.
"""

from __future__ import annotations

import copy
import contextlib
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import yaml

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Loads and manages model configuration from YAML files."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration loader.

        Args:
            config_path: Optional explicit path to config YAML file.
        """
        # Infer repo root from file location:
        # .../src/config/loader.py -> parents[0]=config, [1]=src, [2]=repo_root
        self._repo_root: Path = Path(__file__).resolve().parents[2]

        # Precedence:
        # 1) env var FAIR_CAM_CONFIG
        # 2) explicit config_path arg
        # 3) default repo_root/inputs/model_config.yaml
        env_cfg = os.getenv("FAIR_CAM_CONFIG", "").strip()
        if env_cfg:
            p = Path(env_cfg).expanduser()
            config_path = p if p.is_absolute() else (self._repo_root / p)

        if config_path is None:
            config_path = self._repo_root / "inputs" / "model_config.yaml"

        self.config_path: Path = Path(config_path).expanduser().resolve()
        self._config: Dict[str, Any] = {}

        # Load YAML first (does not depend on project_root)
        self._load_config()

        # Now compute project_root from config (safe after _config exists)
        cfg_root = self._config.get("paths", {}).get("project_root")
        if cfg_root is None:
            raise ValueError("Missing required config key: paths.project_root")
        self._project_root: Path = self._resolve_against_repo(str(cfg_root))

        logger.info(
            "ConfigLoader initialized. repo_root=%s project_root=%s config=%s",
            self._repo_root,
            self._project_root,
            self.config_path,
        )

    # -----------------------------
    # Core loading
    # -----------------------------

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Expected default: {self._repo_root / 'inputs' / 'model_config.yaml'}\n"
                f"Or set FAIR_CAM_CONFIG or pass config_path explicitly to get_config(config_path=...)"
            )

        with open(self.config_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}

        if not isinstance(loaded, dict):
            raise ValueError(f"Config YAML must load to a dict, got: {type(loaded)}")

        self._config = loaded
        logger.info("Loaded configuration from %s", self.config_path)

    # -----------------------------
    # Path resolution
    # -----------------------------

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    @property
    def project_root(self) -> Path:
        return self._project_root

    def _resolve_against_repo(self, p: str) -> Path:
        pp = Path(p).expanduser()
        return pp if pp.is_absolute() else (self._repo_root / pp).resolve()

    def resolve_path(self, p: str, base: str = "project") -> str:
        """
        Resolve a path string to an absolute path.

        base:
          - "project" (default): resolve relative paths under project_root (paths.project_root)
          - "repo": resolve relative paths under repo_root
          - "config": resolve relative paths under config file directory
        """
        pp = Path(p).expanduser()
        if pp.is_absolute():
            return str(pp)

        base = (base or "project").strip().lower()
        if base == "repo":
            return str((self.repo_root / pp).resolve())
        if base == "config":
            return str((self.config_path.parent / pp).resolve())

        # default: project
        return str((self.project_root / pp).resolve())

    def get_path(self, key_path: str, default: Any = None, base: str = "project") -> Optional[str]:
        """
        Fetch config value at key_path and resolve it as a path.

        Returns None if key not found and default is None.
        """
        raw = self.get(key_path, default=default)
        if raw is None:
            return None
        return self.resolve_path(str(raw), base=base)

    # -----------------------------
    # Config access
    # -----------------------------

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value using dot notation."""
        keys = key_path.split(".")
        value: Any = self._config

        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def get_section(self, section: str) -> Dict[str, Any]:
        """Get entire configuration section (top-level)."""
        v = self._config.get(section, {})
        return v if isinstance(v, dict) else {}

    def reload(self) -> None:
        """Reload configuration from file and recompute project_root."""
        self._load_config()
        cfg_root = self._config.get("paths", {}).get("project_root")
        if cfg_root is None:
            raise ValueError("Missing required config key: paths.project_root")
        self._project_root = self._resolve_against_repo(str(cfg_root))

    @property
    def all(self) -> Dict[str, Any]:
        """Get entire configuration dictionary (copy)."""
        return dict(self._config)

    # -----------------------------
    # Per-run config overrides
    # -----------------------------

    _override_lock = threading.Lock()

    @contextlib.contextmanager
    def override(self, overrides: Dict[str, Any]) -> Iterator[None]:
        """Temporarily deep-merge *overrides* into the config for one run.

        Usage::

            with get_config().override({"threat_landscape": {"change_frequency_per_year": 0}}):
                model = FAIRCAMModel(data, seed=42)
                ...

        The original config is restored when the block exits, even on error.
        A lock prevents concurrent runs from stomping on each other.
        """
        if not overrides:
            yield
            return

        with self._override_lock:
            original = copy.deepcopy(self._config)
            try:
                _deep_merge(self._config, overrides)
                yield
            finally:
                self._config = original

    # -----------------------------
    # Config update (write-back)
    # -----------------------------

    # Sections exposed to the Settings UI.
    _EDITABLE_SECTIONS = [
        "model", "batch", "time", "paths",
        "network", "threat_landscape", "threats",
        "controls", "remediation", "loss", "loss_events",
        "variance_prevention", "personnel_behavior",
        "dsc_decision", "vmc_detection", "personnel",
    ]

    # Sections that must NOT be modified via the Settings API.
    _PROTECTED_SECTIONS = {
        "api", "change_events", "dsc_calibration",
        "excel_loader", "assets", "narrative",
    }

    def get_editable_sections(self) -> Dict[str, Any]:
        """Return config sections that are editable via the Settings UI.

        Excludes: api (security), change_events (deprecated),
        dsc_calibration, excel_loader, assets, narrative,
        and controls.efficacy_methods (behavioral mappings).
        """
        result: Dict[str, Any] = {}
        for key in self._EDITABLE_SECTIONS:
            if key in self._config:
                section = copy.deepcopy(self._config[key])
                # Strip non-editable sub-sections
                if key == "controls" and isinstance(section, dict):
                    section.pop("efficacy_methods", None)
                result[key] = section
        return result

    def update(self, updates: Dict[str, Any]) -> None:
        """Deep-merge *updates* into the YAML config and write back.

        Uses ``ruamel.yaml`` for comment-preserving round-trip serialisation.
        Only keys present in *updates* are changed; everything else (including
        comments, ordering, and formatting) is preserved.

        After writing, the in-memory config is reloaded so subsequent
        ``get()`` calls return the updated values.
        """
        from ruamel.yaml import YAML

        yaml_rt = YAML()
        yaml_rt.preserve_quotes = True

        # Load the file with ruamel for round-trip (preserves comments)
        with open(self.config_path, "r", encoding="utf-8") as f:
            doc = yaml_rt.load(f)

        # Deep merge updates into the ruamel CommentedMap document
        _deep_merge(doc, updates)

        # Write back
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml_rt.dump(doc, f)

        # Reload the internal _config dict (uses PyYAML safe_load for runtime)
        self.reload()
        logger.info("Config updated and reloaded from %s", self.config_path)


def _deep_merge(base: dict, updates: dict) -> None:
    """Recursively merge *updates* into *base* dict (in-place).

    Works with both plain dicts and ``ruamel.yaml``'s ``CommentedMap``.
    """
    for key, value in updates.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


# Global configuration instance (singleton pattern)
_global_config: Optional[ConfigLoader] = None


def get_config(config_path: Optional[Path] = None) -> ConfigLoader:
    """
    Get global configuration instance.

    Precedence for initial load is handled by ConfigLoader:
      FAIR_CAM_CONFIG env var > config_path arg > default path

    If a config is already loaded and config_path is provided with a different
    resolved path, we reset and reload using the provided path. This avoids
    surprising behavior in tests or multi-entrypoint usage.
    """
    global _global_config
    if _global_config is None:
        _global_config = ConfigLoader(config_path)
        return _global_config

    if config_path is not None:
        requested = Path(config_path).expanduser().resolve()
        loaded = Path(_global_config.config_path).expanduser().resolve()
        if requested != loaded:
            _global_config = ConfigLoader(requested)

    return _global_config


def reset_config() -> None:
    """Reset global configuration (useful for testing)."""
    global _global_config
    _global_config = None
