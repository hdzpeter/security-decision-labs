"""src/agents/tech_asset.py

Technology asset agent.

- Technology assets participate in lateral movement edges.
- Network layer is used for targeting and lateral movement heuristics.

Validation is YAML-configurable:
- If assets.tech_asset.allow_unlisted_network_layer is true, any string value is accepted.
- Otherwise, network_layer must be in assets.tech_asset.allowed_network_layers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from mesa import Agent

from ..config import get_config


cfg = get_config()


def _require(path: str):
    v = cfg.get(path, None)
    if v is None:
        raise ValueError(f"Missing required config key: {path}")
    return v


def _norm(s: Optional[str]) -> str:
    return str(s or "").strip().lower()


class TechAsset(Agent):
    """Technology asset."""

    _agent_type = "TechAsset"

    def __init__(self, model: Any, unique_id: str, params: Dict[str, Any]):
        # Mesa 3.x: Agent(model), Mesa 2.x: Agent(unique_id, model)
        try:
            super().__init__(model)
            self.unique_id = unique_id
        except TypeError:
            super().__init__(unique_id, model)

        self.model = model
        self.params = params or {}

        # -------------------------
        # Network layer
        # -------------------------
        # JSON may provide "Network Layer"; Loader normalizes to Network_Layer.
        layer = self.params.get("Network_Layer", self.params.get("Network Layer", None))
        if layer is None:
            layer = _require("assets.tech_asset.defaults.network_layer")

        layer = _norm(layer)
        allow_unlisted = bool(_require("assets.tech_asset.allow_unlisted_network_layer"))
        allowed = [_norm(x) for x in (_require("assets.tech_asset.allowed_network_layers") or [])]
        if (not allow_unlisted) and allowed and layer not in allowed:
            raise ValueError(f"TechAsset {unique_id}: invalid network_layer='{layer}'. Allowed: {allowed}")
        self.network_layer = layer

        # -------------------------
        # Visibility (derived from network_layer)
        # -------------------------
        # External == visible, internal == not visible.
        # External TAs can be targeted by external threats initially.
        # Internal TAs are only reachable via lateral movement after external breach.
        # Note: The "Visible" column in Excel is ignored; visibility is derived from network_layer.
        self.visible = (self.network_layer == "external")

        self.compromised = False

    def become_compromised(self, threat_id: str):
        self.compromised = True

    def step(self):
        return
