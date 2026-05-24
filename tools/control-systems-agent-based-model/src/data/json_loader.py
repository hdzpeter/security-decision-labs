"""Load scenario data from a JSON file (created by the UI editor).

The JSON format mirrors the output of ``ExcelLoader.load_all()`` so the
simulation engine can consume it identically.  Edge ``rel_type`` strings are
converted back to ``RelationshipType`` enum members.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..network.relationships import RelationshipType

logger = logging.getLogger(__name__)

# Build a lookup table from enum name -> enum member
_REL_TYPE_LOOKUP = {rt.name: rt for rt in RelationshipType}


def _parse_edges(raw_edges: List[Dict[str, str]]) -> List[Tuple[str, str, RelationshipType]]:
    """Convert edge dicts to (source, target, RelationshipType) tuples."""
    edges: List[Tuple[str, str, RelationshipType]] = []
    for e in raw_edges:
        src = e.get("source", "")
        tgt = e.get("target", "")
        rel_str = e.get("rel_type", "")
        rt = _REL_TYPE_LOOKUP.get(rel_str)
        if rt is None:
            logger.warning("Unknown rel_type '%s' for edge %s -> %s, skipping", rel_str, src, tgt)
            continue
        edges.append((src, tgt, rt))
    return edges


class JsonLoader:
    """Drop-in replacement for ``ExcelLoader`` that reads ``scenario_data.json``."""

    def __init__(self, json_path: str):
        self._path = Path(json_path)

    def load_all(self) -> Dict[str, Any]:
        """Load and return the same dict structure as ``ExcelLoader.load_all()``."""
        raw = json.loads(self._path.read_text(encoding="utf-8"))

        # Map camelCase API keys back to internal snake_case keys
        key_map = {
            "dsc": "dsc_params",
            "vmc": "vmc_params",
            "lec": "lec_params",
            "techAssets": "tech_asset_params",
            "busAssets": "business_asset_params",
            "threatSources": "threat_source_params",
            "threatAgents": "threat_agent_params",
            "personnel": "personnel_params",
        }

        result: Dict[str, Any] = {}

        for api_key, internal_key in key_map.items():
            # Try camelCase first, then snake_case (in case JSON was already internal format)
            result[internal_key] = raw.get(api_key) or raw.get(internal_key) or []

        # Parse edges
        raw_edges = raw.get("edges", [])
        if raw_edges and isinstance(raw_edges[0], dict):
            result["edges"] = _parse_edges(raw_edges)
        else:
            result["edges"] = raw_edges  # Already tuples (shouldn't happen in JSON)

        # Validation fields
        result["topology_missing_ids"] = (
            raw.get("topology_missing_ids")
            or (raw.get("validation") or {}).get("topologyMissingIds")
            or []
        )
        result["topology_extra_ids"] = (
            raw.get("topology_extra_ids")
            or (raw.get("validation") or {}).get("topologyExtraIds")
            or []
        )

        return result
