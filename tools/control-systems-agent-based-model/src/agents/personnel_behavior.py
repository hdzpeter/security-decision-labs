"""src/agents/personnel_behavior.py

No-op personnel integration stub.

The dynamic personnel-behavior model (satisficing, social contagion,
event shocks) is not included in this release. This stub preserves
the interface that src/model.py imports.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional


class PersonnelIntegration:
    """No-op personnel integration. ``enabled`` is False; every hook is inert."""

    enabled: bool = False

    def __init__(self, model: Any, **kwargs: Any) -> None:
        self.model = model
        self.behaviors: dict = {}
        self.personnel_agents: list = []

    def step(self, organizational_events: Optional[Iterable[Any]] = None) -> None:
        return None

    def get_control_owners(self, control_id: str) -> List[str]:
        return []
