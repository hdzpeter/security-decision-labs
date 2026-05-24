"""src/agents/business_asset.py

Business asset agent.

- Business assets drive loss type. Canonical FAIR-CAM loss modes are:
    * information: record-driven losses
    * process    : downtime/recovery driven losses

We'll allow additional asset types (custom taxonomy) if:
- They are listed in YAML under assets.business_asset.allowed_types, and
- YAML maps them to a canonical loss mode under assets.business_asset.type_semantics.

Validation is also YAML-configurable:
- If assets.business_asset.allow_unlisted_type is true, any string value is accepted.
- Otherwise, asset_type must be in assets.business_asset.allowed_types.
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


class BusinessAsset(Agent):
    """Business asset (information or process)."""

    _agent_type = "BusinessAsset"

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
        # Asset type
        # -------------------------
        # Prefer normalized fields (set by Loader)
        asset_type = self.params.get("Asset_Type", self.params.get("Type", None))
        if asset_type is None:
            asset_type = _require("assets.business_asset.defaults.asset_type")

        asset_type = _norm(asset_type)
        allow_unlisted = bool(_require("assets.business_asset.allow_unlisted_type"))
        allowed = [_norm(x) for x in (_require("assets.business_asset.allowed_types") or [])]
        if (not allow_unlisted) and allowed and asset_type not in allowed:
            raise ValueError(f"BusinessAsset {unique_id}: invalid asset_type='{asset_type}'. Allowed: {allowed}")
        self.asset_type = asset_type

        # -------------------------
        # Record count (used by loss logic; applies to all assets)
        # -------------------------
        # JSON may provide "Record Size"; Loader normalizes to Record_Count.
        record_count = self.params.get("Record_Count", self.params.get("Record Size", None))
        if record_count is None:
            record_count = _require("assets.business_asset.defaults.record_count")
        self.record_count = int(record_count) if record_count is not None else 0

        self.compromised = False

    def step(self):
        return
