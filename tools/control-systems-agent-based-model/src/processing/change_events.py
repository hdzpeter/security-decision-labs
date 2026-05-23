"""
src/processing/change_events.py

Change event generation and processing.

- Change events occur on a schedule and affect a sample of controls.
- For each affected control in NORMAL state, evaluate whether variance is introduced.

Personnel integration:
- Ownership is configured in YAML (ownership.control_owners) keyed by control node id (e.g., LEC5).
- Personnel integration provides the variance factor for owners.

Variance probability:
  P(variance) = base_change_risk * event.severity * personnel_factor

"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import logging

from ..config import get_config

logger = logging.getLogger(__name__)
config = get_config()


def _require(key: str):
    v = config.get(key, None)
    if v is None:
        raise ValueError(f"Missing required config key: {key}")
    return v


class ChangeType(str, Enum):
    SOFTWARE_UPDATE = "software_update"
    POLICY_UPDATE = "policy_update"


@dataclass
class ChangeEvent:
    tick: int
    change_type: ChangeType
    affected_controls: List[str]
    severity: float
    description: str = ""


class ChangeEventGenerator:
    def __init__(self, model):
        self.model = model
        self.scheduled_events: List[ChangeEvent] = []
        self.processed_events: List[ChangeEvent] = []

        self.monthly_change_rate = float(config.get("change_events.monthly_change_rate"))
        self.quarterly_change_rate = float(config.get("change_events.quarterly_change_rate"))

        self._schedule_periodic_events()

    def _schedule_periodic_events(self):
        monthly_periods = int(config.get("change_events.schedule.monthly_periods"))
        quarterly_periods = int(config.get("change_events.schedule.quarterly_periods"))

        hours_per_month = int(config.get("time.hours_per_month"))
        hours_per_quarter = hours_per_month * 3

        software_severity = float(config.get("change_events.severity.software_update"))
        policy_severity = float(config.get("change_events.severity.policy_update"))

        for month in range(1, monthly_periods + 1):
            tick = month * hours_per_month
            self._schedule_change_event(
                tick=tick,
                change_type=ChangeType.SOFTWARE_UPDATE,
                rate=self.monthly_change_rate,
                severity=software_severity,
                description=f"Monthly patch cycle (month {month})",
            )

        for quarter in range(1, quarterly_periods + 1):
            tick = quarter * hours_per_quarter
            self._schedule_change_event(
                tick=tick,
                change_type=ChangeType.POLICY_UPDATE,
                rate=self.quarterly_change_rate,
                severity=policy_severity,
                description=f"Quarterly policy review (Q{quarter})",
            )

    def _schedule_change_event(self, tick: int, change_type: ChangeType, rate: float, severity: float, description: str):
        controls = self.model.all_controls()
        if not controls:
            return

        num_affected = max(1, int(len(controls) * float(rate)))

        ids = [c.unique_id for c in controls]
        # Keyed to tick so removing a control doesn't shift the shuffle
        # for other events (see STREAM_ISOLATION.md)
        streams = getattr(self.model, "streams", None)
        shuffle_rng = streams.get(f"change_shuffle:{tick}") if streams else self.model.random
        shuffle_rng.shuffle(ids)
        affected_controls = ids[: min(num_affected, len(ids))]

        self.scheduled_events.append(
            ChangeEvent(
                tick=int(tick),
                change_type=change_type,
                affected_controls=affected_controls,
                severity=float(severity),
                description=description,
            )
        )

    def step(self):
        current_tick = int(self.model.schedule.steps)
        events_to_process = [e for e in self.scheduled_events if int(e.tick) == current_tick]

        for event in events_to_process:
            self._process_change_event(event)
            self.scheduled_events.remove(event)
            self.processed_events.append(event)

    def _process_change_event(self, event: ChangeEvent):
        logger.info(
            "Processing change event at tick %s: %s affecting %s controls",
            event.tick,
            event.change_type.value,
            len(event.affected_controls),
        )

        affected_agents = []
        for control_id in event.affected_controls:
            agent = self.model.network.get_agent(control_id)
            if agent and hasattr(agent, "state"):
                affected_agents.append(agent)

        for agent in affected_agents:
            self._evaluate_change_risk(agent, event)

        # On-change detection attempts
        if hasattr(self.model, "vmc_detector"):
            try:
                self.model.vmc_detector.detect_changes(affected_agents, change_severity=float(event.severity), reason=event.change_type.value)
            except TypeError:
                # backward compatibility if older signature exists
                self.model.vmc_detector.detect_changes(affected_agents, change_severity=float(event.severity))

    def _evaluate_change_risk(self, control_agent, event: ChangeEvent):
        if getattr(control_agent, "state", None) != "normal":
            return
        if not hasattr(control_agent, "trigger_variance"):
            return

        base_change_risk = float(config.get("change_events.base_change_risk"))

        owner_ids = []
        if hasattr(self.model, "get_control_owners"):
            owner_ids = list(self.model.get_control_owners(getattr(control_agent, "unique_id", "")) or [])

        integration = getattr(self.model, "personnel_integration", None)
        if integration is None or not getattr(integration, "enabled", False):
            personnel_factor = float(config.get("change_events.default_personnel_factor"))
        else:
            personnel_factor = float(integration.get_variance_factor_for_owners(owner_ids))

        variance_probability = base_change_risk * float(event.severity) * float(personnel_factor)

        # Keyed to control so removing another control doesn't shift
        # this draw (see STREAM_ISOLATION.md)
        cid = str(getattr(control_agent, "unique_id", ""))
        streams = getattr(self.model, "streams", None)
        var_rng = streams.get(f"change_var:{cid}") if streams else self.model.random
        if float(var_rng.random()) < float(variance_probability):
            reason = f"Personnel decision during {event.change_type.value}" if owner_ids else f"Change risk during {event.change_type.value}"
            control_agent.trigger_variance(reason=reason)

    def get_upcoming_events(self, lookahead_ticks: Optional[int] = None) -> List[ChangeEvent]:
        if lookahead_ticks is None:
            lookahead_ticks = int(config.get("change_events.schedule.lookahead_ticks"))

        current_tick = int(self.model.schedule.steps)
        return [e for e in self.scheduled_events if current_tick <= e.tick < current_tick + int(lookahead_ticks)]
