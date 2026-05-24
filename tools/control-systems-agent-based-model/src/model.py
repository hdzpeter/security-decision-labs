"""src/model.py

FAIR-CAM Mesa model.

This file wires together:
- Agents loaded from Excel inputs
- Network topology
- Core processors (contact, loss, remediation, change events, VMC detection, DSC decisions)
- Personnel behavior integration (ownership via YAML)

"""

from __future__ import annotations

import inspect
import logging
import math
from typing import Any, Dict, List, Optional

from mesa import Model
from mesa.time import RandomActivation

from .analysis.metrics import MetricsState, create_data_collector
from .analysis.narrative import NarrativeCollector

from .agents.dsc_agent import DSCAgent
from .agents.vmc_agent import VMCAgent
from .agents.lec_agent import LECAgent
from .agents.tech_asset import TechAsset
from .agents.business_asset import BusinessAsset
from .agents.threat_source import ThreatSourceAgent
from .agents.threat_agent import ThreatAgent

from .network.topology import FAIRCAMNetwork
from .network.relationships import RelationshipType

from .config import get_config
from .processing.contact import ContactProcessor
from .processing.loss_event import LossEventProcessor
from .processing.remediation import RemediationQueue
from .processing.vmc_detection import VMCDetector
from .processing.dsc_decision import DSCDecisionModel

from .agents.personnel_agent import PersonnelAgent
from .agents.personnel_behavior import PersonnelIntegration

from .data.streamed_rng import StreamedRNG

cfg = get_config()
logger = logging.getLogger(__name__)


def _agent_id(row: Dict[str, Any]) -> str:
    return str(row.get("ID") or row.get("id") or "").strip()


def _construct_agent(AgentCls: Any, model: Any, agent_id: str, params: Dict[str, Any]) -> Any:
    """Signature-tolerant agent constructor."""
    try:
        sig = inspect.signature(AgentCls)
        p = sig.parameters
        kwargs = {}
        if "model" in p:
            kwargs["model"] = model
        if "unique_id" in p:
            kwargs["unique_id"] = agent_id
        if "agent_id" in p:
            kwargs["agent_id"] = agent_id
        if "params" in p:
            kwargs["params"] = params
        if kwargs:
            return AgentCls(**kwargs)
    except Exception:
        pass

    variants = [
        (model, agent_id, params),
        (agent_id, model, params),
        (model, params),
        (agent_id, model),
    ]
    last: Optional[Exception] = None
    for args in variants:
        try:
            return AgentCls(*args)
        except TypeError as e:
            last = e
            continue
    raise TypeError(f"Could not construct {AgentCls.__name__} for id={agent_id}. Last error: {last}")


class FAIRCAMModel(Model):
    """Top-level Mesa model for FAIR-CAM."""

    def __init__(self, model_data: Dict[str, Any], seed: int, steps: Optional[int] = None,
                 use_isolated_streams: bool = False, use_crn: bool = False,
                 collect_timeseries: bool = True):
        super().__init__()
        self.random.seed(int(seed))
        # Per-entity stream isolation for marginal value analysis.
        # Each agent/processor gets its own deterministic PRNG stream so that
        # removing a control for counterfactual comparison doesn't shift
        # random draws for unrelated entities. See STREAM_ISOLATION.md.
        _isolate = use_isolated_streams or use_crn  # use_crn kept for backward compat
        self.use_isolated_streams = bool(_isolate)
        self.streams = StreamedRNG(int(seed)) if _isolate else None

        self.steps = int(steps if steps is not None else cfg.get("model.default_steps"))
        self.schedule = RandomActivation(self)

        self.metrics_state = MetricsState()
        # Mesa's DataCollector accumulates per-step agent-level snapshots (~34 MB
        # per 1-year run) and is only consumed by export_results()'s timeseries
        # dataframe. Monte Carlo runners that read aggregate totals from
        # metrics_state never need it, and the accumulated snapshots leak across
        # iterations when the model is reinstantiated in a loop. Set
        # collect_timeseries=False to skip it.
        self.datacollector = create_data_collector(self) if collect_timeseries else None
        try:
            self.narrative = NarrativeCollector(self)
        except TypeError:
            # Backwards-compatible: older NarrativeCollector() without model
            self.narrative = NarrativeCollector()
        self.network = FAIRCAMNetwork()

        self.compromised_tech_assets: set[str] = set()

        # Org events are applied to personnel behavior on the *next* tick.
        self._org_events_pending: List[str] = []
        self._org_events_next: List[str] = []

        self._init_agents_from_data(model_data)
        self._init_network_from_data(model_data)

        # Threat agent templates (from Excel "Threat Agents" sheet). These are instantiated
        # on-demand by ThreatSource agents.
        self.threat_agent_templates: Dict[str, Dict[str, Any]] = {}
        for row in model_data.get("threat_agent_params", []) or []:
            if not isinstance(row, dict):
                continue
            tid = str(row.get("ID") or row.get("id") or "").strip()
            if tid:
                self.threat_agent_templates[tid] = dict(row)

        # Dynamic threat agent IDs counter
        self._threat_agent_seq: int = 0

        # Personnel behavior integration (ownership + network)
        self.personnel_integration = PersonnelIntegration(model=self)

        # Core processors
        self.dsc_decision_model = DSCDecisionModel(self)
        self.remediation = RemediationQueue(self)
        self.vmc_detector = VMCDetector(self)
        self.loss_event_processor = LossEventProcessor(self)
        self.contact_processor = ContactProcessor(self)
        # Note: Variance events are now driven solely by each control's Change Freq
        # distribution (from Excel), triggered in BaseControlAgent.step() when
        # next_change_time is reached. The previous ChangeEventGenerator added
        # non-spec monthly/quarterly events that caused excess variance.

        # Cost tracking - accumulate CapEx once at initialization
        self._accumulate_capex()
        self._last_opex_tick = 0

        # Threat landscape change scheduling (extrinsic variance — KB §09)
        self._next_threat_landscape_tick: Optional[int] = None
        self._schedule_next_threat_landscape_change()

        # Monthly personnel-driven variance tracking (spec slide 38)
        self._last_personnel_variance_tick: int = 0

    def spawn_threat_agent(self, threat_source: Any) -> Optional[Any]:
        """Instantiate and schedule a ThreatAgent spawned from a ThreatSource.

        The ThreatSource can optionally specify a template ID (e.g., "Generated Threat Type ID")
        in its params. If no template is specified (or is missing), a random template is used.
        """

        templates = self.threat_agent_templates or {}
        if not templates:
            return None

        # Template selection
        tpl_id = None
        try:
            tpl_id = str(getattr(threat_source, "params", {}) or {}).get("Threat_Template")
        except Exception:
            tpl_id = None

        if tpl_id is not None:
            tpl_id = str(tpl_id).strip()

        if tpl_id and tpl_id in templates:
            base_params = dict(templates[tpl_id])
        else:
            # Fallback to a random template
            keys = list(templates.keys())
            _r = self.streams.get("threat_spawn") if self.streams else self.random
            tpl_id = keys[int(_r.random() * len(keys))]
            base_params = dict(templates[tpl_id])

        # Unique ID for this instantiated agent
        self._threat_agent_seq += 1
        uid = f"{tpl_id}__inst_{self._threat_agent_seq}"
        while uid in self.network.all_node_ids():
            self._threat_agent_seq += 1
            uid = f"{tpl_id}__inst_{self._threat_agent_seq}"

        agent = _construct_agent(ThreatAgent, self, uid, base_params)
        # Ensure the newly spawned threat attempts its first contact promptly.
        try:
            agent.next_contact_tick = int(getattr(self.schedule, "steps", 0))
        except Exception:
            pass
        self.schedule.add(agent)
        # Register in network so processors can look it up
        self.network.register_agent(uid, agent)
        return agent

    # ------------------------------------------------------------------
    # Public helpers called by processors
    # ------------------------------------------------------------------

    def record_org_event(self, event_name: str, targets: Optional[List[str]] = None) -> None:
        """Record an organizational event to be applied to personnel next tick.

        Args:
            event_name: name of the org event (e.g., 'security_breach', 'audit_finding')
            targets: optional list of personnel ids that should receive the event.
                     If None, the event is broadcast org-wide.
        """
        name = str(event_name or "").strip()
        if not name:
            return
        payload = {"name": name, "targets": list(targets) if targets else None}
        self._org_events_next.append(payload)

    def _consume_org_events(self) -> List[Dict[str, Any]]:
        """Move next -> pending and return pending payloads."""
        events = list(self._org_events_pending)
        self._org_events_pending = list(self._org_events_next)
        self._org_events_next = []
        return events

    def cleanup_after_loss(self, tech_asset_id: str, threat_id: str) -> None:
        """Clean up compromised state after loss event terminates.

        Return assets to normal and remove threat agent.
        """
        # Return tech asset to normal
        self.compromised_tech_assets.discard(tech_asset_id)

        # Remove threat agent from schedule + network
        if threat_id:
            agent = self.network.get_agent(threat_id)
            if agent is not None:
                try:
                    self.schedule.remove(agent)
                except Exception:
                    pass
                try:
                    self.network.G.remove_node(threat_id)
                except Exception:
                    pass
                self.network._agent_registry.pop(threat_id, None)

    def all_controls(self) -> List[Any]:
        controls = []
        for a in self.schedule.agents:
            if a.__class__.__name__ in ("LECAgent", "VMCAgent", "DSCAgent"):
                controls.append(a)
        return controls

    def get_control_owners(self, control_id: str) -> List[str]:
        """Ownership mapping (Option 3) - provided by YAML."""
        return self.personnel_integration.get_control_owners(control_id)

    # ------------------------------------------------------------------
    # Extrinsic variance: threat landscape changes (KB §09, spec slide 38)
    # ------------------------------------------------------------------

    def _schedule_next_threat_landscape_change(self) -> None:
        """Schedule next threat landscape change using Poisson (exponential inter-arrival)."""
        freq = float(cfg.get("threat_landscape.change_frequency_per_year", 0))
        if freq <= 0:
            self._next_threat_landscape_tick = None
            return

        hours_per_year = float(cfg.get("time.hours_per_year", 8760))
        mean_interval = hours_per_year / freq

        # Exponential inter-arrival time
        _r = self.streams.get("landscape") if self.streams else self.random
        u = max(1e-12, min(1.0 - 1e-12, float(_r.random())))
        interval = -math.log(u) * mean_interval

        current_tick = int(getattr(self.schedule, "steps", 0))
        self._next_threat_landscape_tick = current_tick + int(max(1, interval))

    def _process_threat_landscape_change(self) -> None:
        """Process threat landscape change: all software-based normal controls become variant.

        Extrinsic variance: conditions outside the organisation
        (e.g., new zero-day exploits, CVE disclosures) reduce control efficacy.
        Bypasses DSC/VMC prevention gates because the
        controls themselves haven't changed but the threat landscape has.
        """
        if self._next_threat_landscape_tick is None:
            return

        tick = int(getattr(self.schedule, "steps", 0))
        if tick < self._next_threat_landscape_tick:
            return

        affect_detection = bool(
            cfg.get("threat_landscape.affect_detection_controls", False)
        )

        affected = 0
        for control in self.all_controls():
            if getattr(control, "state", None) != "normal":
                continue
            if not control.is_software_based():
                continue
            # Optionally exclude VMC/DSC controls from threat landscape variance
            if not affect_detection:
                cls_name = control.__class__.__name__
                if cls_name in ("VMCAgent", "DSCAgent"):
                    continue
            try:
                control.on_change_event("threat_landscape")
                affected += 1
            except Exception:
                pass

        logger.info(
            "Threat landscape change at tick %d: %d software controls became variant",
            tick, affected,
        )

        # Schedule next
        self._schedule_next_threat_landscape_change()

    # ------------------------------------------------------------------
    # Intrinsic variance: personnel-driven
    # ------------------------------------------------------------------

    def _process_monthly_personnel_variance(self) -> None:
        """Monthly personnel-driven variance check.

        Intrinsic variance — irregular, internally-driven:
        actions (or inaction) within the organisation cause controls to
        become variant.  Personnel with admin privileges who are
        "misaligned" (making bad security decisions) can degrade the
        controls they manage.

        For each control, check if any linked personnel agent (with admin_privileges)
        causes a misaligned decision via the DSC decision model and VM reduce-prob gate.
        """
        ticks_per_month = int(cfg.get("time.ticks_per_month", 730))
        current_tick = int(getattr(self.schedule, "steps", 0))

        if current_tick < self._last_personnel_variance_tick + ticks_per_month:
            return

        self._last_personnel_variance_tick = current_tick

        integration = getattr(self, "personnel_integration", None)
        if integration is None or not getattr(integration, "enabled", False):
            return

        for control in self.all_controls():
            if getattr(control, "state", None) != "normal":
                continue

            owner_ids = integration.get_control_owners(str(control.unique_id))
            if not owner_ids:
                continue

            for oid in owner_ids:
                pb = integration.behaviors.get(oid)
                if pb is None:
                    continue

                # attempt_personnel_variance checks admin, DSC, VMC gates
                if control.attempt_personnel_variance(pb.agent):
                    break  # Control is now variant, no need to check more personnel

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _init_agents_from_data(self, model_data: Dict[str, Any]):
        for row in model_data.get("dsc_params", []) or []:
            if isinstance(row, dict) and (aid := _agent_id(row)):
                self.schedule.add(_construct_agent(DSCAgent, self, aid, row))

        for row in model_data.get("vmc_params", []) or []:
            if isinstance(row, dict) and (aid := _agent_id(row)):
                self.schedule.add(_construct_agent(VMCAgent, self, aid, row))

        for row in model_data.get("lec_params", []) or []:
            if isinstance(row, dict) and (aid := _agent_id(row)):
                self.schedule.add(_construct_agent(LECAgent, self, aid, row))

        for row in model_data.get("tech_asset_params", []) or []:
            if isinstance(row, dict) and (aid := _agent_id(row)):
                self.schedule.add(_construct_agent(TechAsset, self, aid, row))

        for row in model_data.get("business_asset_params", []) or []:
            if isinstance(row, dict) and (aid := _agent_id(row)):
                self.schedule.add(_construct_agent(BusinessAsset, self, aid, row))

        for row in model_data.get("threat_source_params", []) or []:
            if isinstance(row, dict) and (aid := _agent_id(row)):
                self.schedule.add(_construct_agent(ThreatSourceAgent, self, aid, row))

        # threat_agent templates are kept in model_data, not scheduled directly

        # Personnel agents from topology/scenario data (HA nodes)
        for row in model_data.get("personnel_params", []) or []:
            if isinstance(row, dict) and (aid := _agent_id(row)):
                self.schedule.add(_construct_agent(PersonnelAgent, self, aid, row))

    def _init_network_from_data(self, model_data: Dict[str, Any]):
        # Register scheduled agents as nodes
        for agent in self.schedule.agents:
            aid = str(getattr(agent, "unique_id", "")).strip()
            if aid:
                self.network.register_agent(aid, agent)

        # Add edges from loader
        for edge in model_data.get("edges", []) or []:
            try:
                source_id, target_id, rel_type = edge
            except Exception:
                continue

            s = str(source_id).strip()
            t = str(target_id).strip()
            if not s or not t or s == t:
                continue

            if self.network.get_agent(s) is None:
                self.network.add_placeholder_node(s)
            if self.network.get_agent(t) is None:
                self.network.add_placeholder_node(t)

            if not isinstance(rel_type, RelationshipType):
                try:
                    rel_type = RelationshipType[str(rel_type)]
                except Exception:
                    rel_type = RelationshipType.VMC_MONITORS

            self.network.add_relationship(s, t, rel_type)

    # ------------------------------------------------------------------
    # Cost tracking
    # ------------------------------------------------------------------

    def _accumulate_capex(self):
        """Accumulate CapEx from all control agents at initialization."""
        if not cfg.get("controls.cost_tracking.accumulate_capex_at_init", True):
            return
        total_capex = 0.0
        for agent in self.schedule.agents:
            if agent.__class__.__name__ in ("LECAgent", "VMCAgent", "DSCAgent"):
                capex = getattr(agent, "capex", 0.0)
                if capex and isinstance(capex, (int, float)):
                    total_capex += float(capex)
        self.metrics_state.cumulative_capex = total_capex

    def _accumulate_opex_if_due(self):
        """Accumulate OpEx from all control agents at configured intervals."""
        interval_mode = cfg.get("controls.cost_tracking.opex_accumulation_interval", "annual")
        if interval_mode == "none":
            return

        current_tick = int(getattr(self.schedule, "steps", 0))

        # Determine interval in ticks
        if interval_mode == "annual":
            interval_ticks = int(cfg.get("time.hours_per_year", 8760))
        elif interval_mode == "monthly":
            interval_ticks = int(cfg.get("time.ticks_per_month", 730))
        else:
            return  # Unknown mode

        # Check if we've crossed an interval boundary
        if current_tick > 0 and current_tick >= self._last_opex_tick + interval_ticks:
            total_opex = 0.0
            for agent in self.schedule.agents:
                if agent.__class__.__name__ in ("LECAgent", "VMCAgent", "DSCAgent"):
                    opex = getattr(agent, "opex", 0.0)
                    if opex and isinstance(opex, (int, float)):
                        total_opex += float(opex)
            self.metrics_state.cumulative_opex += total_opex
            self._last_opex_tick = current_tick

    # ------------------------------------------------------------------
    # Simulation step
    # ------------------------------------------------------------------

    def step(self):
        # 0) Advance personnel behavior using org events from *previous* tick
        if getattr(self.personnel_integration, "enabled", False):
            self.personnel_integration.step(organizational_events=self._consume_org_events())
        else:
            self._consume_org_events()  # still advance buffers

        # 0.5) Accumulate OpEx at configured intervals (annual/monthly)
        self._accumulate_opex_if_due()

        # 0.7) Threat landscape changes (externally-driven variance, spec slide 38)
        self._process_threat_landscape_change()

        # 0.8) Monthly personnel-driven variance (irregular, internally-driven, spec slide 38)
        self._process_monthly_personnel_variance()

        # 1) Periodic VMC monitoring (variance detection)
        self.vmc_detector.step()

        # 2) Realize pending losses
        self.loss_event_processor.step()

        # 3) Remediation queue (start/finish)
        self.remediation.step()

        # 4) Step all agents (threat contacts + self-driven variance happen here)
        self.schedule.step()

        # 5) Collect data
        if self.datacollector is not None:
            self.datacollector.collect(self)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_results(self, sample_interval: Optional[int] = None) -> Dict[str, Any]:
        """Export simulation results.

        Args:
            sample_interval: If provided, sample time series at this interval (ticks).
                           If None, uses ticks_per_month from config for monthly sampling.
        """
        summary: Dict[str, Any] = {}
        try:
            summary = self.metrics_state.to_summary_dict()
        except Exception:
            summary = {}

        time_series: List[Dict[str, Any]] = []
        if self.datacollector is not None:
            try:
                df = self.datacollector.get_model_vars_dataframe()
                df = df.reset_index().rename(columns={"index": "tick"})

                # Sample time series to reduce data size (monthly by default)
                if sample_interval is None:
                    sample_interval = int(cfg.get("time.ticks_per_month", 730))

                if sample_interval > 1 and len(df) > sample_interval:
                    # Sample at regular intervals, always include first and last
                    indices = list(range(0, len(df), sample_interval))
                    if indices[-1] != len(df) - 1:
                        indices.append(len(df) - 1)
                    df = df.iloc[indices]

                time_series = df.to_dict(orient="records")
            except Exception:
                time_series = []

        narrative: Dict[str, Any] = {}
        try:
            if hasattr(self.narrative, "export_narratives"):
                narrative = self.narrative.export_narratives()
            elif hasattr(self.narrative, "export"):
                narrative = self.narrative.export()
        except Exception:
            narrative = {}

        graph: Dict[str, Any] = {}
        try:
            graph = self.network.export_graph()
        except Exception:
            graph = {}

        return {"summary": summary, "timeSeries": time_series, "narrative": narrative, "graph": graph}