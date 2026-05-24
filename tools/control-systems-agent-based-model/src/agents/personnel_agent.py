"""src/agents/personnel_agent.py

Personnel agent.

Intentionally lightweight:
- Stores identity + organizational attributes
- Exposes canonical DSC attributes (expectation_alignment/awareness/capability/situational/incentive)
- Stores behavior knobs read from YAML

Behavior dynamics live in src/agents/personnel_behavior.py (network + updates).
"""

from __future__ import annotations

from typing import Any, Dict

from mesa import Agent

from ..config import get_config

cfg = get_config()


def _require(path: str):
    v = cfg.get(path, None)
    if v is None:
        raise ValueError(f"Missing required config key: {path}")
    return v


def _boolish(v: Any, *, key: str) -> bool:
    """
    Parse boolean-ish values safely.
    Prevents common bug: bool("false") == True.
    """
    if isinstance(v, bool):
        return v
    if v is None:
        raise ValueError(f"Missing required boolean value: {key}")
    s = str(v).strip().lower()
    if s in ("1", "true", "t", "yes", "y", "on"):
        return True
    if s in ("0", "false", "f", "no", "n", "off"):
        return False
    raise ValueError(f"Config/param value for '{key}' must be boolean-ish, got: {v!r}")


class PersonnelAgent(Agent):
    _agent_type = "Personnel"

    def __init__(self, model: Any, unique_id: str, params: Dict[str, Any]):
        # Mesa compatibility:
        # - Mesa 3.x: Agent(model)
        # - Mesa 2.x: Agent(unique_id, model)
        try:
            super().__init__(model)  # Mesa 3.x
            self.unique_id = unique_id
        except TypeError:
            super().__init__(unique_id, model)  # Mesa 2.x
        self.params = params or {}

        # ------------------------------------------------------------------
        # Organizational properties (required)
        # ------------------------------------------------------------------
        dept = self.params.get("Department", self.params.get("department", None))
        if dept is None:
            raise ValueError("PersonnelAgent missing required param: department")
        self.department = str(dept).strip().lower()

        rl = self.params.get("RoleLevel", self.params.get("role_level", None))
        if rl is None:
            raise ValueError("PersonnelAgent missing required param: role_level")
        self.role_level = int(rl)

        admin = self.params.get("Admin", self.params.get("admin_privileges", None))
        if admin is None:
            raise ValueError("PersonnelAgent missing required param: admin_privileges")
        self.admin_privileges = _boolish(admin, key=f"personnel[{unique_id}].admin_privileges")

        # ------------------------------------------------------------------
        # Canonical DSC attributes (used by DSCAgent when needed)
        # ------------------------------------------------------------------
        defaults = cfg.get_section("personnel").get("default_attributes", None)
        if not defaults or not isinstance(defaults, dict):
            raise ValueError("Missing required config: personnel.default_attributes")

        def _attr(name: str) -> float:
            v = self.params.get(name, defaults.get(name, None))
            if v is None:
                raise ValueError(f"Missing required attribute '{name}' for personnel '{unique_id}' and no default provided")
            return float(v)

        # IMPORTANT: use canonical names:
        # expectation_alignment / awareness / capability / situational / incentive
        self.attributes = {
            "expectation_alignment": _attr("expectation_alignment"),
            "awareness": _attr("awareness"),
            "capability": _attr("capability"),
            "situational": _attr("situational"),
            "incentive": _attr("incentive"),
        }

        # ------------------------------------------------------------------
        # Behavior knobs (read from YAML defaults; allow per-agent overrides)
        # ------------------------------------------------------------------
        self.track_history = _boolish(
            self.params.get("track_history", _require("personnel_behavior.track_history")),
            key=f"personnel[{unique_id}].track_history",
        )

        self.susceptibility = float(self.params.get("susceptibility", _require("personnel_behavior.defaults.susceptibility")))
        self.confidence_bound = float(self.params.get("confidence_bound", _require("personnel_behavior.defaults.confidence_bound")))
        self.confirmation_bias = float(self.params.get("confirmation_bias", _require("personnel_behavior.defaults.confirmation_bias")))
        self.optimistic_bias = float(self.params.get("optimistic_bias", _require("personnel_behavior.defaults.optimistic_bias")))

    def step(self):
        # Personnel behavior is advanced centrally by PersonnelIntegration
        return

    def get_attribute(self, name: str) -> float:
        return float(self.attributes.get(name, 0.0))

    def get_effective_attributes(self) -> Dict[str, float]:
        """
        DSCDecisionModel expects this method.

        For now, personnel behavior (propensity, social influence) affects variance introduction,
        not DSC intrinsic attributes. Therefore, effective_attributes == attributes.

        If/when you decide to let behavior influence DSC attributes, do it via YAML-configured
        scaling in a separate module, not hard-coded here.
        """
        return dict(self.attributes)
