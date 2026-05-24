"""
FAIR-CAM Network topology with typed relationships.

This module stores typed edges between model agents and can export a UI-friendly graph.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Set

import networkx as nx

from .relationships import RelationshipType
from ..agents.tech_asset import TechAsset
from ..agents.threat_agent import ThreatAgent

logger = logging.getLogger(__name__)


def _node_type_from_id(node_id: str) -> str:
    s = str(node_id or "").strip().upper()
    if s.startswith("BA"):
        return "business_asset"
    if s.startswith("TA"):
        return "tech_asset"
    if s.startswith("LEC"):
        return "lec"
    if s.startswith("VM") or s.startswith("VMC"):
        return "vmc"
    if s.startswith("DSC"):
        return "dsc"
    if s.startswith("TS") or s.startswith("THREATSOURCE"):
        return "threat_source"
    if s.startswith("AG") or s.startswith("THREATAGENT"):
        return "threat_agent"
    if s.startswith("HA") or s.startswith("PERS") or s.startswith("PERSONNEL"):
        return "personnel"
    return "node"


class FAIRCAMNetwork:
    """Unified network for all FAIR-CAM agent relationships."""

    def __init__(self):
        self.G = nx.MultiDiGraph()
        self._agent_registry: Dict[str, Any] = {}

    def register_agent(self, agent_id: str, agent: Any):
        """Register an agent for lookup and ensure a graph node exists."""
        aid = str(agent_id)
        self._agent_registry[aid] = agent
        if aid not in self.G:
            self.G.add_node(aid, agent=agent)
        else:
            self.G.nodes[aid]["agent"] = agent

    def get_agent(self, agent_id: str) -> Optional[Any]:
        """Get agent by ID."""
        return self._agent_registry.get(str(agent_id))

    def all_node_ids(self) -> Set[str]:
        """All node IDs currently present in the topology graph."""
        return set(self.G.nodes())

    def add_placeholder_node(self, node_id: str):
        """Create a graph node even if no agent exists."""
        nid = str(node_id)
        if nid not in self.G:
            self.G.add_node(nid, agent=None)

    def add_relationship(self, source_id: str, target_id: str, rel_type: RelationshipType, **attrs):
        """Add a typed relationship between agents."""
        s = str(source_id)
        t = str(target_id)

        # Ensure endpoints exist
        if s not in self.G:
            self.G.add_node(s, agent=self._agent_registry.get(s))
        if t not in self.G:
            self.G.add_node(t, agent=self._agent_registry.get(t))

        self.G.add_edge(s, t, rel_type=rel_type, **attrs)
        logger.debug("Added relationship: %s --[%s]--> %s", s, getattr(rel_type, "name", str(rel_type)), t)

    # ---------------- Queries used by processors ----------------

    def _get_neighbors_by_type(self, node_id: str, rel_type: RelationshipType, direction: str = "out") -> List[Any]:
        neighbors: List[Any] = []

        if direction == "out":
            edges = self.G.out_edges(str(node_id), data=True, keys=True)
            for _, target, _, data in edges:
                if data.get("rel_type") == rel_type:
                    a = self.get_agent(target)
                    if a:
                        neighbors.append(a)
        else:
            edges = self.G.in_edges(str(node_id), data=True, keys=True)
            for source, _, _, data in edges:
                if data.get("rel_type") == rel_type:
                    a = self.get_agent(source)
                    if a:
                        neighbors.append(a)

        # de-dupe by agent unique_id if present
        seen: Set[Any] = set()
        out: List[Any] = []
        for a in neighbors:
            uid = getattr(a, "unique_id", id(a))
            if uid not in seen:
                seen.add(uid)
                out.append(a)
        return out

    def _get_neighbors_ids_by_types(
        self, node_id: str, rel_types: Iterable[RelationshipType], direction: str = "in"
    ) -> List[str]:
        """Return neighbor IDs (even if no agent registered), matching any of rel_types."""
        rel_types_set = set(rel_types)
        out_ids: List[str] = []

        try:
            if direction == "out":
                edges = self.G.out_edges(str(node_id), data=True, keys=True)
                for _, target, _, data in edges:
                    if data.get("rel_type") in rel_types_set:
                        out_ids.append(str(target))
            else:
                edges = self.G.in_edges(str(node_id), data=True, keys=True)
                for source, _, _, data in edges:
                    if data.get("rel_type") in rel_types_set:
                        out_ids.append(str(source))
        except Exception:
            return []

        seen: Set[str] = set()
        deduped: List[str] = []
        for x in out_ids:
            if x not in seen:
                seen.add(x)
                deduped.append(x)
        return deduped

    def get_business_assets(self, tech_asset_id: str) -> List:
        return self._get_neighbors_by_type(tech_asset_id, RelationshipType.TECH_HOSTS_BUSINESS, "out")

    # Compatibility alias used by some processors
    def get_hosted_business_assets(self, tech_asset_id: str) -> List:
        return self.get_business_assets(tech_asset_id)

    def get_protecting_lecs(self, asset_id: str) -> List:
        return self._get_neighbors_by_type(asset_id, RelationshipType.LEC_PROTECTS_ASSET, "in")

    # ------------------------------------------------------------------
    # Threat targeting / compromise edges
    # ------------------------------------------------------------------

    def choose_target_tech_asset_for_threat(self, threat: Any) -> Optional[TechAsset]:
        """Pick a target tech asset for a threat agent.

        Minimal, spec-consistent heuristic:
        - External threats prefer visible assets.
        - If none are visible, fall back to any tech asset.
        - Uses the model RNG for reproducibility.
        """

        assets = self.get_all_tech_assets()
        if not assets:
            return None

        origin = str(getattr(threat, "origin", "external") or "external").strip().lower()
        candidates = assets
        if origin == "external":
            vis = [a for a in assets if bool(getattr(a, "visible", False))]
            if vis:
                candidates = vis

        rng = getattr(getattr(threat, "model", None), "random", None)
        if rng is None:
            return candidates[0]

        return rng.choice(list(candidates))

    def add_threat_compromise_edge(self, threat_id: str, tech_asset_id: str) -> None:
        try:
            self.add_relationship(str(threat_id), str(tech_asset_id), RelationshipType.THREAT_COMPROMISES)
        except Exception:
            # Never let narrative/edge recording block simulation
            return

    # ------------------------------------------------------------------
    # Upstream control discovery (used by ContactProcessor)
    # ------------------------------------------------------------------

    def get_controls_upstream(self, target_id: str, depth: int = 1) -> List[Any]:
        """Return controls relevant to the target tech asset.

        Loss Event Controls (LECs) protect assets, and other controls (VMC/DSC)
        influence those LECs. This helper returns:
          - LECs that protect the asset
          - if depth>1: controls that influence those LECs (upstream), up to depth-1

        The function is tolerant to orphan/missing nodes.
        """

        tid = str(target_id)
        if depth <= 0:
            return []

        lecs = self.get_protecting_lecs(tid) or []
        out: List[Any] = list(lecs)

        if depth <= 1 or not lecs:
            return out

        # Include upstream influencers of each LEC
        seen = {getattr(a, "unique_id", id(a)) for a in out}
        for lec in lecs:
            cid = str(getattr(lec, "unique_id", "") or "").strip()
            if not cid:
                continue
            for upstream_id in self.get_upstream_controls_ids(cid, max_depth=depth - 1):
                a = self.get_agent(upstream_id)
                if not a:
                    continue
                uid = getattr(a, "unique_id", id(a))
                if uid in seen:
                    continue
                seen.add(uid)
                out.append(a)

        return out

    def get_dscs_for_personnel(self, personnel_id: str) -> List:
        return self._get_neighbors_by_type(personnel_id, RelationshipType.DSC_AFFECTS_PERSONNEL, "in")

    def get_personnel_for_control(self, control_id: str) -> List:
        return self._get_neighbors_by_type(control_id, RelationshipType.PERSONNEL_ACCESSES, "in")

    def get_peer_personnel(self, personnel_id: str) -> List:
        return self._get_neighbors_by_type(personnel_id, RelationshipType.PERSONNEL_PEERS, "out")

    def get_connected_tech_assets(self, tech_asset_id: str) -> List:
        return self._get_neighbors_by_type(tech_asset_id, RelationshipType.TECH_CONNECTS_TECH, "out")

    def get_lateral_movement_targets(self, tech_asset_id: str, implicit_connectivity: bool = True) -> List[TechAsset]:
        """Return Tech Assets reachable via lateral movement from the given TA.

        Args:
            tech_asset_id: The compromised Tech Asset ID.
            implicit_connectivity: If True, assume all TAs are connected (full mesh).
                                   If False, only use explicit TECH_CONNECTS_TECH edges.

        Returns:
            List of TechAsset agents that can be targeted via lateral movement.
            Excludes the source TA itself.
        """
        tid = str(tech_asset_id)

        if implicit_connectivity:
            # Full mesh: all TAs are reachable except the source
            return [a for a in self.get_all_tech_assets()
                    if str(getattr(a, "unique_id", "")) != tid]
        else:
            # Only explicit TECH_CONNECTS_TECH edges
            return self.get_connected_tech_assets(tid)

    def get_all_tech_assets(self) -> List[TechAsset]:
        return [a for a in self._agent_registry.values() if isinstance(a, TechAsset)]

    def get_all_threat_agents(self) -> List[ThreatAgent]:
        return [a for a in self._agent_registry.values() if isinstance(a, ThreatAgent)]

    def get_monitoring_vmcs(self, control_id: str) -> List[Any]:
        return self._get_neighbors_by_type(control_id, RelationshipType.VMC_MONITORS, "in")

    def get_monitored_controls(self, vmc_id: str) -> List[Any]:
        return self._get_neighbors_by_type(vmc_id, RelationshipType.VMC_MONITORS, "out")

    def get_controls_monitored_by_vmc(self, vmc_id: str) -> List[Any]:
        return self.get_monitored_controls(vmc_id)

    # ---------------- VMC variance prevention queries (Gaps 2+3) ----------------

    def get_vmc_reduce_freq_controls(self, control_id: str) -> List[Any]:
        """Return VMCs that reduce change frequency for this control."""
        return self._get_neighbors_by_type(control_id, RelationshipType.VMC_REDUCES_CHANGE_FREQ, "in")

    def get_vmc_reduce_prob_controls(self, control_id: str) -> List[Any]:
        """Return VMCs that reduce variance probability for this control."""
        return self._get_neighbors_by_type(control_id, RelationshipType.VMC_REDUCES_VAR_PROB, "in")

    # ---------------- VMC relationship queries (Known Limitation #5) --------

    def get_implementing_vmcs(self, control_id: str) -> List[Any]:
        """Get VMCs linked via VMC_IMPLEMENTS_REMEDIATION to this control."""
        return self._get_neighbors_by_type(control_id, RelationshipType.VMC_IMPLEMENTS_REMEDIATION, "in")

    def get_treatment_selection_vmcs(self, control_id: str) -> List[Any]:
        """Get VMCs linked via VMC_SELECTS_TREATMENT to this control."""
        return self._get_neighbors_by_type(control_id, RelationshipType.VMC_SELECTS_TREATMENT, "in")

    def get_threat_intel_vmcs(self, control_id: str) -> List[Any]:
        """Get VMCs linked via VMC_THREAT_INTEL to this control."""
        return self._get_neighbors_by_type(control_id, RelationshipType.VMC_THREAT_INTEL, "in")

    # ---------------- Causal chain support: upstream controls ----------------

    def get_upstream_controls_ids(self, control_id: str, max_depth: int = 2) -> List[str]:
        if max_depth <= 0:
            return []

        influence_rels = [
            RelationshipType.DSC_AFFECTS_CONTROL,
            RelationshipType.VMC_MONITORS,
            RelationshipType.VMC_REDUCES_VAR_PROB,
            RelationshipType.VMC_REDUCES_CHANGE_FREQ,
            RelationshipType.VMC_THREAT_INTEL,
            RelationshipType.VMC_SELECTS_TREATMENT,
            RelationshipType.VMC_IMPLEMENTS_REMEDIATION,
            RelationshipType.VMC_REMEDIATES,
        ]

        visited: Set[str] = set()
        frontier: List[str] = [str(control_id)]
        out: List[str] = []

        depth = 0
        while frontier and depth < max_depth:
            next_frontier: List[str] = []
            for cid in frontier:
                parents = self._get_neighbors_ids_by_types(cid, influence_rels, direction="in")
                for pid in parents:
                    if pid in visited:
                        continue
                    visited.add(pid)
                    out.append(pid)
                    next_frontier.append(pid)
            frontier = next_frontier
            depth += 1

        return out

    # ---------------- Export for UI / API ----------------

    def export_graph(self) -> Dict[str, Any]:
        """
        Export a JSON-serializable graph:

        - Node "label" is always the node ID (stable + matches your preference).
        - Additional metadata (e.g., human-readable name) is carried in "meta".
        - Edge "rel_type" is exported as the RelationshipType name (string).
        """
        nodes: List[Dict[str, Any]] = []
        for nid, attrs in self.G.nodes(data=True):
            agent = attrs.get("agent")
            meta: Dict[str, Any] = {}

            params = getattr(agent, "params", None)
            if isinstance(params, dict):
                if params.get("Name") is not None:
                    meta["name"] = params.get("Name")
                if params.get("Control_Type") is not None:
                    meta["control_type"] = params.get("Control_Type")
                if params.get("LEC_Type") is not None:
                    meta["lec_type"] = params.get("LEC_Type")
                meta["agent_type"] = params.get("_agent_type") or getattr(agent, "agent_type", None)

            nodes.append(
                {
                    "id": str(nid),
                    "label": str(nid),  # IMPORTANT: label == ID
                    "type": _node_type_from_id(str(nid)),
                    "meta": meta,
                }
            )

        edges: List[Dict[str, Any]] = []
        for source, target, key, data in self.G.edges(keys=True, data=True):
            rt = data.get("rel_type")
            rel_name = rt.name if hasattr(rt, "name") else str(rt)
            edges.append(
                {
                    "source": str(source),
                    "target": str(target),
                    "rel_type": rel_name,
                    "id": str(data.get("id") or f"{source}->{target}:{key}"),
                    "label": data.get("label"),
                }
            )

        return {"nodes": nodes, "edges": edges}

    def export_graph_filtered(self, include_types: Optional[Set[str]] = None) -> Dict[str, Any]:
        """
        Export a filtered graph containing only specified node types.

        Args:
            include_types: Set of node types to include. If None, defaults to
                          assets and controls only (no threats).
                          Valid types: tech_asset, business_asset, lec, vmc, dsc

        Returns:
            Dict with filtered nodes and edges.
        """
        if include_types is None:
            # Default: assets and controls only (for UI topology view)
            include_types = {"tech_asset", "business_asset", "lec", "vmc", "dsc"}

        nodes: List[Dict[str, Any]] = []
        included_ids: Set[str] = set()

        for nid, attrs in self.G.nodes(data=True):
            node_type = _node_type_from_id(str(nid))
            if node_type not in include_types:
                continue

            included_ids.add(str(nid))
            agent = attrs.get("agent")
            meta: Dict[str, Any] = {}

            params = getattr(agent, "params", None)
            if isinstance(params, dict):
                if params.get("Name") is not None:
                    meta["name"] = params.get("Name")
                if params.get("Control_Type") is not None:
                    meta["control_type"] = params.get("Control_Type")
                if params.get("LEC_Type") is not None:
                    meta["lec_type"] = params.get("LEC_Type")
                meta["agent_type"] = params.get("_agent_type") or getattr(agent, "agent_type", None)

            nodes.append(
                {
                    "id": str(nid),
                    "label": str(nid),
                    "type": node_type,
                    "meta": meta,
                }
            )

        # Only include edges where both endpoints are in the filtered set
        edges: List[Dict[str, Any]] = []
        for source, target, key, data in self.G.edges(keys=True, data=True):
            if str(source) not in included_ids or str(target) not in included_ids:
                continue

            rt = data.get("rel_type")
            rel_name = rt.name if hasattr(rt, "name") else str(rt)
            edges.append(
                {
                    "source": str(source),
                    "target": str(target),
                    "rel_type": rel_name,
                    "id": str(data.get("id") or f"{source}->{target}:{key}"),
                    "label": data.get("label"),
                }
            )

        return {"nodes": nodes, "edges": edges}

    def validate(self) -> List[str]:
        warnings: List[str] = []
        for node_id in self.G.nodes():
            if self.G.degree(node_id) == 0:
                warnings.append(f"Orphan node with no relationships: {node_id}")
        return warnings

