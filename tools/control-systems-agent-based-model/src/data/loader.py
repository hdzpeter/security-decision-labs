"""
Excel data loader for FAIR-CAM model configuration.

Loads from two Excel files:
1. Control Parameters: DSC, VMC, LEC, Assets, Threats, (optionally Personnel)
2. Network Topology: Either a single-sheet adjacency matrix or multi-sheet format
   with edgelist + per-relationship-type sub-matrices.

Key behavior:
- Topology matrix cells contain markers (typically 'x') that indicate an edge exists.
- Relationship types are inferred from source/target IDs.
- VM -> (LEC/VM/DSC) edges are typed using VM's "Control Type" in control_params.xlsx (sheet VM).
- Self-loops (A -> A) are ignored.
- Unknown relationship types resolve to RelationshipType.UNKNOWN (if available) and warn.

Supported topology formats:
- Single-sheet adjacency matrix (e.g., webapp_exploit): One sheet with IDs in row/col headers
- Multi-sheet (e.g., hospital_ransomware): Sheets "Net Topo" (edgelist), "LECs x Assets",
  "VMCs x LECs", "VMCs x VMCs", "DSCs", "Asset Connections"
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from ..config import get_config
from ..network.relationships import RelationshipType

logger = logging.getLogger(__name__)
config = get_config()


def _parse_efficacy_method(method_str: str) -> dict:
    """
    Parse the 'Efficacy Method' column to determine parameter interpretation.

    Returns a dict with:
      - semantic_type: 'efficacy' | 'probability' | 'time_hours'
      - behavior: 'compare_sophistication' | 'bernoulli_trial' | 'sample_time_interval'
      - time_type: None | 'detection_time' | 'termination_time' | 'recovery_time' | 'remediation_time'
      - legacy_type: backward-compatible string for existing code

    Semantic types:
      - 'efficacy': params represent efficacy [0-1] for comparison to threat sophistication
      - 'probability': params represent probability [0-1] for random draw or variance adjustment
      - 'time_hours': params represent time in hours (Beta-PERT)

    Behavior types:
      - 'compare_sophistication': compare set-and-hold efficacy against threat sophistication
      - 'bernoulli_trial': sample probability, perform Bernoulli trial
      - 'sample_time_interval': sample time interval in hours
    """
    s = str(method_str or "").strip().lower()

    # LEC: "comparison to threat sophistication"
    if "comparison" in s and "sophistication" in s:
        return {
            "semantic_type": "efficacy",
            "behavior": "compare_sophistication",
            "time_type": None,
            "legacy_type": "efficacy",
        }

    # LEC/DSC: "random draw, success/failure outcome" or "random draw to binomial eval"
    if "random draw" in s:
        return {
            "semantic_type": "probability",
            "behavior": "bernoulli_trial",
            "time_type": None,
            "legacy_type": "probability",
        }

    # LEC: "timing interval for detection sweep"
    if "timing interval" in s and "detection" in s:
        return {
            "semantic_type": "time_hours",
            "behavior": "sample_time_interval",
            "time_type": "detection_time",
            "legacy_type": "detection_time",
        }

    # LEC: "timing interval for loss termination"
    if "timing interval" in s and "termination" in s:
        return {
            "semantic_type": "time_hours",
            "behavior": "sample_time_interval",
            "time_type": "termination_time",
            "legacy_type": "termination_time",
        }

    # LEC: "timing interval for recovery"
    if "timing interval" in s and "recovery" in s:
        return {
            "semantic_type": "time_hours",
            "behavior": "sample_time_interval",
            "time_type": "recovery_time",
            "legacy_type": "recovery_time",
        }

    # VMC: "variance probability adjustment factor" or "variance probability adjustment"
    if "variance probability" in s:
        return {
            "semantic_type": "probability",
            "behavior": "bernoulli_trial",
            "time_type": None,
            "legacy_type": "probability",
        }

    # VMC: "time interval for variance detection sweep"
    if "time interval" in s and "detection" in s:
        return {
            "semantic_type": "time_hours",
            "behavior": "sample_time_interval",
            "time_type": "detection_time",
            "legacy_type": "detection_time",
        }

    # VMC: "time interval for variance correction"
    if "time interval" in s and ("correction" in s or "remediation" in s):
        return {
            "semantic_type": "time_hours",
            "behavior": "sample_time_interval",
            "time_type": "remediation_time",
            "legacy_type": "remediation_time",
        }

    # Fallback to efficacy comparison for unknown methods
    logger.warning(
        "Unrecognised Efficacy Method '%s' — falling back to probability-based "
        "efficacy comparison. If this is a time-based control (detection sweep, "
        "remediation interval), parameters will be misinterpreted as probabilities. "
        "Valid methods include: 'comparison to threat sophistication', "
        "'timing interval for detection sweep', 'timing interval for loss termination', "
        "'timing interval for recovery', 'variance probability adjustment factor', "
        "'time interval for variance detection sweep', "
        "'time interval for variance correction'.",
        method_str,
    )
    return {
        "semantic_type": "efficacy",
        "behavior": "compare_sophistication",
        "time_type": None,
        "legacy_type": "efficacy",
    }


def _require(key: str):
    v = config.get(key, None)
    if v is None:
        raise ValueError(f"Missing required config key: {key}")
    return v


def _clean_unnamed_columns(params: Dict[str, Any]) -> Dict[str, Any]:
    """Remove columns that pandas auto-names (e.g., 'Unnamed: 17')."""
    return {k: v for k, v in params.items() if not str(k).startswith("Unnamed:")}


def _normalize_actor_type(raw: Any) -> str:
    """Map 'Control Actor - Software/Human/Other' values to canonical Actor_Type."""
    s = str(raw or "").strip().lower()
    if s in ("software", "sw"):
        return "technology"
    if s in ("human", "person", "people"):
        return "human"
    if s in ("other", ""):
        return "other"
    return s


class ExcelLoader:
    """Load FAIR-CAM model configuration from Excel files."""

    def __init__(self, params_file: Path, topology_file: Path, debug: bool = False):
        self.params_file = Path(params_file)
        self.topology_file = Path(topology_file)
        self.debug = debug

        self._params_data: Dict[str, pd.DataFrame] = {}
        self._topology_data: Optional[pd.DataFrame] = None
        # All topology sheets (for multi-sheet format)
        self._topology_sheets: Dict[str, pd.DataFrame] = {}
        self._topology_format: str = "unknown"  # "single_matrix" | "multi_sheet"

        # VM id -> normalized control type string (lower/strip)
        self._vm_control_type_by_id: Dict[str, str] = {}

    def load_all(self) -> Dict[str, Any]:
        self._load_params_file()
        self._load_topology_file()

        data = {
            "dsc_params": self._parse_dsc_sheet(),
            "vmc_params": self._parse_vmc_sheet(),
            "lec_params": self._parse_lec_sheet(),
            "tech_asset_params": self._parse_tech_assets_sheet(),
            "business_asset_params": self._parse_business_assets_sheet(),
            "threat_source_params": self._parse_threat_sources_sheet(),
            "threat_agent_params": self._parse_threat_agents_sheet(),  # templates only
            "personnel_params": self._parse_personnel_sheet(),
            "edges": self._parse_topology(),
        }

        # --- collect topology IDs for mismatch check ---
        topo_ids_all = self._collect_topology_ids(data["edges"])

        # --- topology expected to cover core nodes only ---
        core_prefixes = {"DSC", "VM", "LEC", "TA", "BA"}
        topo_ids_core = {x for x in topo_ids_all if self._get_prefix(x) in core_prefixes}

        constrained_keys = (
            "dsc_params",
            "vmc_params",
            "lec_params",
            "tech_asset_params",
            "business_asset_params",
        )
        constrained_ids: Set[str] = set()
        for key in constrained_keys:
            for row in data.get(key, []) or []:
                rid = row.get("ID")
                if rid:
                    constrained_ids.add(str(rid).strip())

        constrained_missing = sorted(constrained_ids - topo_ids_core)
        constrained_extra = sorted(topo_ids_core - constrained_ids)

        data["topology_missing_ids"] = constrained_missing
        data["topology_extra_ids"] = constrained_extra

        if constrained_missing:
            logger.warning("IDs in params but missing from topology matrix (core nodes): %s", constrained_missing)
        if constrained_extra:
            logger.warning("IDs in topology matrix but not in params (core nodes): %s", constrained_extra)

        # --- apply topology policy (warn|fail|filter) ---
        policy_val = config.get("network.topology_policy", None)
        if policy_val is None:
            raise ValueError("Missing required config: network.topology_policy")
        policy = str(policy_val).strip().lower()
        if policy not in ("warn", "fail", "filter"):
            raise ValueError(
                f"Invalid network.topology_policy='{policy}'. Allowed: warn | fail | filter. "
                f"(synthesize is disabled to ensure no edges are created outside Excel.)"
            )

        if policy == "fail":
            if constrained_missing:
                raise ValueError(
                    f"Topology policy 'fail': missing IDs in topology matrix for core nodes: {constrained_missing}"
                )

        elif policy == "filter":
            # Keep only DSC/VM/LEC/TA/BA present in topology core IDs.
            for key in constrained_keys:
                before = len(data[key])
                data[key] = [row for row in data[key] if str(row.get("ID", "")).strip() in topo_ids_core]
                after = len(data[key])
                if self.debug:
                    print(f"[TOPO-FILTER] {key}: {before} -> {after}")

        if self.debug:
            self._print_debug_dump(data)

        return data

    def _collect_topology_ids(self, edges: List[Tuple[str, str, RelationshipType]]) -> Set[str]:
        """Collect all node IDs referenced in the topology."""
        ids: Set[str] = set()
        for s, t, _ in edges:
            ids.add(str(s).strip())
            ids.add(str(t).strip())

        # Also include IDs from adjacency matrix headers if single-matrix format
        if self._topology_format == "single_matrix" and self._topology_data is not None:
            df = self._topology_data
            if not df.empty:
                id_row_idx, id_col_start = self._detect_matrix_layout(df)
                if id_row_idx is not None:
                    for x in df.iloc[id_row_idx, id_col_start:].tolist():
                        if pd.notna(x) and str(x).strip():
                            ids.add(str(x).strip())
                    for x in df.iloc[id_row_idx + 2:, 0].tolist():
                        if pd.notna(x) and str(x).strip():
                            ids.add(str(x).strip())
        return ids

    def _load_params_file(self) -> None:
        xl = pd.ExcelFile(self.params_file)
        for sheet_name in xl.sheet_names:
            self._params_data[sheet_name] = pd.read_excel(xl, sheet_name=sheet_name)
            logger.info("Loaded sheet '%s' with %s rows", sheet_name, len(self._params_data[sheet_name]))

    def _load_topology_file(self) -> None:
        """Load topology file, auto-detecting format from sheet names."""
        xl = pd.ExcelFile(self.topology_file)
        sheet_names = xl.sheet_names

        # Multi-sheet format: has "Net Topo" or relationship-specific sheets
        multi_sheet_markers = {"Net Topo", "LECs x Assets", "VMCs x LECs", "Asset Connections"}
        if multi_sheet_markers.intersection(set(sheet_names)):
            self._topology_format = "multi_sheet"
            for sn in sheet_names:
                self._topology_sheets[sn] = pd.read_excel(xl, sheet_name=sn, header=None)
            logger.info(
                "Loaded multi-sheet topology (%d sheets: %s)",
                len(self._topology_sheets),
                list(self._topology_sheets.keys()),
            )
            # Set _topology_data to None; multi-sheet uses _topology_sheets
            self._topology_data = None
        else:
            # Single-sheet adjacency matrix
            self._topology_format = "single_matrix"
            self._topology_data = pd.read_excel(xl, header=None)
            logger.info("Loaded single-sheet topology matrix: %s", getattr(self._topology_data, "shape", None))

    # -------------------------------------------------------------------------
    # Params sheet parsers
    # -------------------------------------------------------------------------

    def _parse_dsc_sheet(self) -> List[Dict[str, Any]]:
        df = self._params_data.get("DSC", pd.DataFrame())
        return self._rows_to_dicts(df, "DSC")

    def _parse_vmc_sheet(self) -> List[Dict[str, Any]]:
        df = self._params_data.get("VM", pd.DataFrame())
        rows = self._rows_to_dicts(df, "VMC")

        # Build VM ID -> normalized control type lookup for relationship inference
        vm_map: Dict[str, str] = {}
        for r in rows:
            rid = str(r.get("ID") or "").strip()
            ct = r.get("Control_Type", r.get("Control Type", None))
            cts = str(ct or "").strip().lower()
            if rid:
                vm_map[rid] = cts
        self._vm_control_type_by_id = vm_map

        return rows

    def _parse_lec_sheet(self) -> List[Dict[str, Any]]:
        df = self._params_data.get("LEC", pd.DataFrame())
        rows = self._rows_to_dicts(df, "LEC")
        return self._merge_duplicate_ids(rows)

    def _parse_tech_assets_sheet(self) -> List[Dict[str, Any]]:
        df = self._params_data.get("Tech Assets", pd.DataFrame())
        return self._rows_to_dicts(df, "TechAsset")

    def _parse_business_assets_sheet(self) -> List[Dict[str, Any]]:
        df = self._params_data.get("Bus Assets", pd.DataFrame())
        return self._rows_to_dicts(df, "BusinessAsset")

    def _parse_threat_sources_sheet(self) -> List[Dict[str, Any]]:
        df = self._params_data.get("Threat Sources", pd.DataFrame())
        return self._rows_to_dicts(df, "ThreatSource")

    def _parse_threat_agents_sheet(self) -> List[Dict[str, Any]]:
        df = self._params_data.get("Threat Agents", pd.DataFrame())
        return self._rows_to_dicts(df, "ThreatAgent")

    def _parse_personnel_sheet(self) -> List[Dict[str, Any]]:
        df = self._params_data.get("Personnel", pd.DataFrame())
        if df.empty:
            return []
        return self._rows_to_dicts(df, "Personnel")

    # -------------------------------------------------------------------------
    # Duplicate ID merging (multi-row controls like webapp LEC3)
    # -------------------------------------------------------------------------

    def _merge_duplicate_ids(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge rows that share the same ID (e.g., LEC3 with resistance/visibility/recognition).

        The first occurrence is kept as the base row. Additional Control_Type values
        are collected into a 'Control_Types' list field.
        """
        seen: Dict[str, int] = {}  # ID -> index in result
        result: List[Dict[str, Any]] = []

        for row in rows:
            rid = str(row.get("ID") or "").strip()
            if not rid:
                result.append(row)
                continue

            if rid in seen:
                # Merge: collect additional Control_Type into list
                base = result[seen[rid]]
                extra_ct = str(row.get("Control_Type") or "").strip().lower()
                if extra_ct:
                    if "Control_Types" not in base:
                        base["Control_Types"] = [str(base.get("Control_Type") or "").strip().lower()]
                    if extra_ct not in base["Control_Types"]:
                        base["Control_Types"].append(extra_ct)
                logger.info("Merged duplicate ID '%s' (extra Control_Type='%s')", rid, extra_ct)
            else:
                seen[rid] = len(result)
                result.append(row)

        return result

    # -------------------------------------------------------------------------
    # Row -> dict conversion with column normalization
    # -------------------------------------------------------------------------

    def _rows_to_dicts(self, df: pd.DataFrame, agent_type: str) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            params = row.to_dict()
            params["_agent_type"] = agent_type

            # Clean Unnamed: columns (Excel spacer columns)
            params = _clean_unnamed_columns(params)

            # Primary ID normalization
            if "Network Node ID" in params and pd.notna(params.get("Network Node ID")):
                params["ID"] = params["Network Node ID"]
            elif "ID Tag" in params and pd.notna(params.get("ID Tag")):
                params["ID"] = params["ID Tag"]

            # Clean NaN
            params = {k: (None if pd.isna(v) else v) for k, v in params.items()}

            # --- Remediation cost normalization (all control types) ---
            if agent_type in ("VMC", "LEC", "DSC"):
                if params.get("RemCostMin") is not None:
                    params["Remediation_Cost_Min"] = params["RemCostMin"]
                if params.get("RemCostML") is not None:
                    params["Remediation_Cost_ML"] = params["RemCostML"]
                if params.get("RemCost Max") is not None:
                    params["Remediation_Cost_Max"] = params["RemCost Max"]

            # VMC/LEC: map Dist Type + Param 1-4 => Efficacy fields
            if agent_type in ("VMC", "LEC"):
                if params.get("Dist Type") is not None:
                    params["Efficacy Dist Type"] = params.get("Dist Type")
                    params["Efficacy Param 1"] = params.get("Param 1")
                    params["Efficacy Param 2"] = params.get("Param 2")
                    params["Efficacy Param 3"] = params.get("Param 3")
                    params["Efficacy Param 4"] = params.get("Param 4")

                # Parse Efficacy Method to determine semantic interpretation of params
                efficacy_method_raw = params.get("Efficacy Method", "")
                efficacy_method_parsed = _parse_efficacy_method(efficacy_method_raw)
                params["_efficacy_method_raw"] = efficacy_method_raw
                params["_efficacy_method_type"] = efficacy_method_parsed["legacy_type"]  # backward compat
                params["_efficacy_semantic_type"] = efficacy_method_parsed["semantic_type"]
                params["_efficacy_behavior"] = efficacy_method_parsed["behavior"]
                params["_efficacy_time_type"] = efficacy_method_parsed["time_type"]

                # Fill missing efficacy distribution fields from YAML defaults (no hard-coded defaults in code)
                eff_def = _require("controls.defaults.efficacy")
                params.setdefault("Efficacy Dist Type", eff_def.get("dist_type"))
                params.setdefault("Efficacy Param 1", eff_def.get("param1"))
                params.setdefault("Efficacy Param 2", eff_def.get("param2"))
                params.setdefault("Efficacy Param 3", eff_def.get("param3"))
                params.setdefault("Efficacy Param 4", eff_def.get("param4"))

                ch_def = _require("controls.defaults.change_freq")
                params.setdefault("Change Freq Dist Type", ch_def.get("dist_type"))
                params.setdefault("Change Freq Param 1", ch_def.get("param1"))
                params.setdefault("Change Freq Param 2", ch_def.get("param2"))
                params.setdefault("Change Freq Param 3", ch_def.get("param3"))
                params.setdefault("Change Freq Param 4", ch_def.get("param4"))

                # Fill missing cost fields
                params.setdefault("CapEx", _require("controls.defaults.capex"))
                params.setdefault("OpEx", _require("controls.defaults.opex"))

                # Binary Variance Efficacy flag
                bve = params.get("Binary Variance Efficacy?")
                if bve is not None:
                    if isinstance(bve, (bool, int, float)):
                        params["Binary_Variance_Efficacy"] = bool(int(bve))
                    else:
                        params["Binary_Variance_Efficacy"] = str(bve).strip().lower() in (
                            "true", "t", "yes", "y", "1",
                        )

            if agent_type == "LEC":
                # Normalize control_type + lec_type + actor_type.
                # If Excel does not provide a value, fall back to YAML defaults.
                params["Control_Type"] = params.get(
                    "Control Type",
                    params.get("Control_Type", _require("controls.defaults.control_types.lec")),
                )
                params["LEC_Type"] = params.get(
                    "LEC_Type",
                    params.get("LEC Type", _require("controls.defaults.lec.defaults.lec_type")),
                )

                # Actor_Type: check multiple possible column names
                actor_raw = params.get("Control Actor - Software/Human/Other")
                if actor_raw is not None:
                    params["Actor_Type"] = _normalize_actor_type(actor_raw)
                else:
                    # Fallback: infer from Description field if it looks like
                    # "Human" / "Technology" / "Software", otherwise use config default.
                    desc = str(params.get("Description", "")).strip().lower()
                    if desc in ("human",):
                        params["Actor_Type"] = "human"
                    elif desc in ("technology", "software", "tech"):
                        params["Actor_Type"] = "technology"
                    else:
                        params["Actor_Type"] = params.get(
                            "Actor_Type",
                            params.get("Actor Type", _require("controls.defaults.lec.defaults.actor_type")),
                        )

            if agent_type == "VMC":
                params["Control_Type"] = params.get(
                    "Control Type",
                    params.get("Control_Type", _require("controls.defaults.control_types.vmc")),
                )

            # DSC: parse efficacy method and distribution params
            if agent_type == "DSC":
                # Parse Efficacy Method to determine semantic interpretation of params
                efficacy_method_raw = params.get("Efficacy Method", "")
                efficacy_method_parsed = _parse_efficacy_method(efficacy_method_raw)
                params["_efficacy_method_raw"] = efficacy_method_raw
                params["_efficacy_method_type"] = efficacy_method_parsed["legacy_type"]  # backward compat
                params["_efficacy_semantic_type"] = efficacy_method_parsed["semantic_type"]
                params["_efficacy_behavior"] = efficacy_method_parsed["behavior"]
                params["_efficacy_time_type"] = efficacy_method_parsed["time_type"]

                # DSC uses "Efficacy Dist Type" and "Efficacy Param 1..4" columns
                # Fill from YAML defaults if missing
                dsc_prob_def = config.get("controls.defaults.dsc.defaults.prob_dist", {})
                params.setdefault("Efficacy Dist Type", "Beta PERT")
                params.setdefault("Efficacy Param 1", dsc_prob_def.get("min", 0.0))
                params.setdefault("Efficacy Param 2", dsc_prob_def.get("mode", 0.5))
                params.setdefault("Efficacy Param 3", dsc_prob_def.get("max", 1.0))
                params.setdefault("Efficacy Param 4", dsc_prob_def.get("confidence", 4))

                # Fill change freq from YAML defaults
                ch_def = _require("controls.defaults.change_freq")
                params.setdefault("Change Freq Dist Type", ch_def.get("dist_type"))
                params.setdefault("Change Freq Param 1", ch_def.get("param1"))
                params.setdefault("Change Freq Param 2", ch_def.get("param2"))
                params.setdefault("Change Freq Param 3", ch_def.get("param3"))
                params.setdefault("Change Freq Param 4", ch_def.get("param4"))

                # Fill missing cost fields
                params.setdefault("CapEx", _require("controls.defaults.capex"))
                params.setdefault("OpEx", _require("controls.defaults.opex"))

            # TechAsset: normalize network layer & visibility
            if agent_type == "TechAsset":
                if params.get("Network Layer") is not None:
                    params["Network_Layer"] = params.get("Network Layer")

                # Normalize Visible to boolean when provided.
                if "Visible" in params:
                    v = params.get("Visible")
                    if v is None:
                        params["Visible"] = None
                    elif isinstance(v, (bool, int, float)):
                        params["Visible"] = bool(int(v))
                    else:
                        s = str(v).strip().lower()
                        if s in ("true", "t", "yes", "y", "1"):
                            params["Visible"] = True
                        elif s in ("false", "f", "no", "n", "0", ""):
                            params["Visible"] = False
                        else:
                            params["Visible"] = False

                # Fill missing TechAsset fields from YAML defaults
                if params.get("Network_Layer") is None:
                    params["Network_Layer"] = _require("assets.tech_asset.defaults.network_layer")
                if params.get("Visible") is None:
                    params["Visible"] = _require("assets.tech_asset.defaults.visible")

                # Scale Param passthrough (already consumed by contact.py)
                if params.get("Scale Param") is not None:
                    params["Scale_Param"] = params.get("Scale Param")

            if agent_type == "BusinessAsset":
                if params.get("Type") is not None:
                    params["Asset_Type"] = params.get("Type")
                if params.get("Record Size") is not None:
                    params["Record_Count"] = params.get("Record Size")

                # Fill missing BusinessAsset fields from YAML defaults
                if params.get("Asset_Type") is None:
                    params["Asset_Type"] = _require("assets.business_asset.defaults.asset_type")
                if params.get("Record_Count") is None:
                    params["Record_Count"] = _require("assets.business_asset.defaults.record_count")

            if agent_type == "ThreatSource":
                if params.get("Generated Threat Type ID") is not None:
                    params["Threat_Template"] = params.get("Generated Threat Type ID")

                # Normalize contact freq param column names.
                # Webapp uses "Contact Freq Param 1 (years)" etc.
                for i in range(1, 5):
                    canonical = f"Param {i}"
                    if params.get(canonical) is None:
                        # Try alternative column names
                        for alt in [
                            f"Contact Freq Param {i} (years)",
                            f"Contact Freq Param {i}",
                        ]:
                            if params.get(alt) is not None:
                                params[canonical] = params[alt]
                                break

            if agent_type == "ThreatAgent":
                origin = params.get("Threat Origin (internal/external)")
                if origin is not None:
                    params["Origin"] = origin

                if params.get("Sophistication Dist Type") is not None:
                    params["Sophistication Param 1"] = params.get("Param 1")
                    params["Sophistication Param 2"] = params.get("Param 2")
                    params["Sophistication Param 3"] = params.get("Param 3")
                    params["Sophistication Param 4"] = params.get("Param 4")

                if params.get("Mean Event Velocity for Losses") is not None:
                    params["Mean_Velocity_Hours"] = params.get("Mean Event Velocity for Losses")
                if params.get("Loss Rate Exponent (based on hours estimate)") is not None:
                    params["Exp_Loss_Rate"] = params.get("Loss Rate Exponent (based on hours estimate)")

                # Threat Target Pref passthrough
                if params.get("Threat Target Pref") is not None:
                    params["Target_Preference"] = params.get("Threat Target Pref")

            if agent_type == "Personnel":
                # Personnel rows: passthrough with ID normalization (already done above).
                # Normalize Personnel Type
                if params.get("Personnel Type") is not None:
                    params["Personnel_Type"] = params.get("Personnel Type")
                if params.get("Personnel Org Level Team ID") is not None:
                    params["Team_ID"] = params.get("Personnel Org Level Team ID")
                if params.get("Agent Count") is not None:
                    params["Agent_Count"] = params.get("Agent Count")

            result.append(params)

        return result

    # -------------------------------------------------------------------------
    # Topology parsing
    # -------------------------------------------------------------------------

    def _is_edge_cell(self, cell_value: Any) -> bool:
        if cell_value is None or (isinstance(cell_value, float) and pd.isna(cell_value)):
            return False
        if isinstance(cell_value, str):
            return cell_value.strip().lower() == "x" or cell_value.strip() == "1"
        if isinstance(cell_value, bool):
            return bool(cell_value)
        if isinstance(cell_value, (int, float)):
            try:
                return int(cell_value) == 1
            except Exception:
                return False
        return False

    def _parse_topology(self) -> List[Tuple[str, str, RelationshipType]]:
        """Parse topology into edge list, dispatching based on detected format."""
        if self._topology_format == "multi_sheet":
            return self._parse_topology_multi_sheet()
        else:
            return self._parse_topology_single_matrix()

    def _parse_topology_single_matrix(self) -> List[Tuple[str, str, RelationshipType]]:
        """
        Parse single-sheet adjacency matrix into edge list.

        Auto-detects layout by finding the row that contains agent IDs (DSC/VM/LEC/TA/BA)
        in columns, and the column that contains agent IDs in rows.
        """
        df = self._topology_data
        edges: List[Tuple[str, str, RelationshipType]] = []
        if df is None or df.empty:
            return edges

        id_row_idx, id_col_start = self._detect_matrix_layout(df)
        if id_row_idx is None:
            logger.warning("Could not detect adjacency matrix layout in topology file")
            return edges

        # Data rows start 2 below the ID header row (ID row, then name row)
        data_row_start = id_row_idx + 2

        col_headers = df.iloc[id_row_idx, id_col_start:].tolist()
        row_headers = df.iloc[data_row_start:, 0].tolist()

        seen = set()

        for i, source in enumerate(row_headers):
            if pd.isna(source):
                continue
            source = str(source).strip()
            if not source:
                continue

            for j, target in enumerate(col_headers):
                if pd.isna(target):
                    continue
                target = str(target).strip()
                if not target:
                    continue

                cell_value = df.iloc[i + data_row_start, j + id_col_start]
                if not self._is_edge_cell(cell_value):
                    continue

                rel_type = self._infer_relationship_type(source, target)

                # Skip edges that should be ignored (e.g., LEC -> VM reverse references)
                if rel_type is None:
                    continue

                source_prefix = self._get_prefix(source)
                target_prefix = self._get_prefix(target)

                s, t = source, target

                # If TA -> LEC is marked, flip to LEC -> TA
                if (
                    rel_type == getattr(RelationshipType, "LEC_PROTECTS_ASSET", rel_type)
                    and source_prefix == "TA"
                    and target_prefix == "LEC"
                ):
                    s, t = target, source

                # Drop self-loops (these are almost always spreadsheet artifacts)
                if str(s).strip() == str(t).strip():
                    continue

                key = (s, t, rel_type)
                if key not in seen:
                    seen.add(key)
                    edges.append((s, t, rel_type))

        logger.info("Parsed %s edges from single-sheet topology", len(edges))
        return edges

    def _detect_matrix_layout(self, df: pd.DataFrame) -> Tuple[Optional[int], int]:
        """Detect which row contains the column header IDs and where data columns start.

        Returns (id_row_index, id_col_start) or (None, 0) if not found.
        Scans the first few rows looking for one that contains agent ID patterns
        (DSC1, VM1, LEC1, TA1, BA1, etc.) in multiple columns.
        """
        agent_id_pattern = re.compile(r"^(DSC|VM|LEC|TA|BA|TS|TRT|HA)\d", re.IGNORECASE)

        for row_idx in range(min(5, len(df))):
            matches_by_col_start: Dict[int, int] = {}
            for col_idx in range(df.shape[1]):
                val = df.iloc[row_idx, col_idx]
                if pd.notna(val) and agent_id_pattern.match(str(val).strip()):
                    # Find the first column with an ID in this row
                    if col_idx not in matches_by_col_start:
                        matches_by_col_start[col_idx] = 0
                    matches_by_col_start[col_idx] += 1

            # Count total ID matches in this row
            total_matches = sum(1 for col_idx in range(df.shape[1])
                                if pd.notna(df.iloc[row_idx, col_idx])
                                and agent_id_pattern.match(str(df.iloc[row_idx, col_idx]).strip()))

            if total_matches >= 3:  # Need at least 3 IDs to be confident
                # Find where IDs start (first column with an ID)
                first_id_col = min(
                    col_idx for col_idx in range(df.shape[1])
                    if pd.notna(df.iloc[row_idx, col_idx])
                    and agent_id_pattern.match(str(df.iloc[row_idx, col_idx]).strip())
                )
                return row_idx, first_id_col

        return None, 0

    def _parse_topology_multi_sheet(self) -> List[Tuple[str, str, RelationshipType]]:
        """Parse multi-sheet topology format (hospital_ransomware style).

        Sheets:
        - "Net Topo": Source/Target/Weight edgelist
        - "LECs x Assets": LEC-to-TA adjacency sub-matrix
        - "VMCs x LECs": VMC-to-LEC adjacency sub-matrix
        - "VMCs x VMCs": VMC-to-VMC adjacency sub-matrix
        - "DSCs": DSC-to-target adjacency sub-matrix
        - "Asset Connections": TA-to-TA / TA-to-BA adjacency sub-matrix
        """
        edges: List[Tuple[str, str, RelationshipType]] = []
        seen: Set[Tuple[str, str, RelationshipType]] = set()

        def _add_edge(s: str, t: str, rt: RelationshipType) -> None:
            s, t = s.strip(), t.strip()
            if s == t:
                return  # skip self-loops
            key = (s, t, rt)
            if key not in seen:
                seen.add(key)
                edges.append((s, t, rt))

        # 1) "Net Topo" edgelist sheet
        if "Net Topo" in self._topology_sheets:
            df = self._topology_sheets["Net Topo"]
            # First row may be header ("Source", "Target", "Weight") or data
            start = 0
            if df.shape[0] > 0:
                first_val = str(df.iloc[0, 0]).strip().lower() if pd.notna(df.iloc[0, 0]) else ""
                if first_val in ("source", "from", "src"):
                    start = 1  # skip header row

            for i in range(start, len(df)):
                src = df.iloc[i, 0]
                tgt = df.iloc[i, 1]
                if pd.isna(src) or pd.isna(tgt):
                    continue
                src_s, tgt_s = str(src).strip(), str(tgt).strip()
                if not src_s or not tgt_s:
                    continue
                rel = self._infer_relationship_type(src_s, tgt_s)
                if rel is not None:
                    _add_edge(src_s, tgt_s, rel)

        # 2) Parse adjacency sub-matrices from named sheets
        sub_matrix_sheets = [
            "LECs x Assets",
            "VMCs x LECs",
            "VMCs x VMCs",
            "DSCs",
            "Asset Connections",
        ]
        for sheet_name in sub_matrix_sheets:
            if sheet_name not in self._topology_sheets:
                continue
            df = self._topology_sheets[sheet_name]
            sub_edges = self._parse_sub_matrix(df, sheet_name)
            for s, t, rt in sub_edges:
                _add_edge(s, t, rt)

        logger.info("Parsed %s edges from multi-sheet topology", len(edges))
        return edges

    def _parse_sub_matrix(
        self, df: pd.DataFrame, sheet_name: str
    ) -> List[Tuple[str, str, RelationshipType]]:
        """Parse a sub-matrix sheet (e.g., 'LECs x Assets').

        Layout (typical):
        - Row 0: column headers (names)
        - Row 1: column header IDs (e.g., 'Network Node ID', 'TA1', 'TA2', ...)
        - Rows 2+: data rows with row IDs in column 1 (Network Node ID column)
        """
        edges: List[Tuple[str, str, RelationshipType]] = []
        if df is None or df.empty or df.shape[0] < 3 or df.shape[1] < 3:
            return edges

        # Find the ID row: look for a row where column 1 says "Network Node ID"
        # and subsequent columns contain agent IDs
        id_row_idx = None
        id_col_offset = 2  # default: IDs start at column 2
        agent_id_pattern = re.compile(r"^(DSC|VM|LEC|TA|BA|HA)\d", re.IGNORECASE)

        for row_idx in range(min(4, len(df))):
            # Check if this row has "Network Node ID" in column 0 or 1
            c0 = str(df.iloc[row_idx, 0]).strip().lower() if pd.notna(df.iloc[row_idx, 0]) else ""
            c1 = str(df.iloc[row_idx, 1]).strip().lower() if pd.notna(df.iloc[row_idx, 1]) else ""
            if "network node id" in c0 or "network node id" in c1 or "node id" in c0 or "node id" in c1:
                id_row_idx = row_idx
                break
            # Also check if this row simply has lots of agent IDs
            id_count = sum(
                1 for col_idx in range(2, df.shape[1])
                if pd.notna(df.iloc[row_idx, col_idx])
                and agent_id_pattern.match(str(df.iloc[row_idx, col_idx]).strip())
            )
            if id_count >= 2:
                id_row_idx = row_idx
                break

        if id_row_idx is None:
            logger.warning("Could not find ID row in sub-matrix sheet '%s'", sheet_name)
            return edges

        # Column header IDs are in row id_row_idx, starting at id_col_offset
        col_ids = []
        for j in range(id_col_offset, df.shape[1]):
            val = df.iloc[id_row_idx, j]
            if pd.notna(val) and str(val).strip():
                col_ids.append((j, str(val).strip()))
            else:
                col_ids.append((j, None))

        # Data rows start after the ID row
        data_start = id_row_idx + 1

        # Row IDs are in column 1 (Network Node ID column)
        row_id_col = 1

        for i in range(data_start, df.shape[0]):
            row_id_val = df.iloc[i, row_id_col]
            if pd.isna(row_id_val):
                continue
            source = str(row_id_val).strip()
            if not source:
                continue

            for j, target in col_ids:
                if target is None:
                    continue
                cell = df.iloc[i, j]
                if not self._is_edge_cell(cell):
                    continue

                rel = self._infer_relationship_type(source, target)
                if rel is not None:
                    src_prefix = self._get_prefix(source)
                    tgt_prefix = self._get_prefix(target)
                    s, t = source, target

                    # Flip TA -> LEC to LEC -> TA
                    if (
                        rel == getattr(RelationshipType, "LEC_PROTECTS_ASSET", rel)
                        and src_prefix == "TA"
                        and tgt_prefix == "LEC"
                    ):
                        s, t = target, source

                    # Flip BA -> TA to TA -> BA (canonical: TECH_HOSTS_BUSINESS)
                    if (
                        src_prefix == "BA"
                        and tgt_prefix == "TA"
                    ):
                        s, t = target, source

                    if s != t:
                        edges.append((s, t, rel))

        return edges

    # -------------------------------------------------------------------------
    # Relationship inference
    # -------------------------------------------------------------------------

    def _infer_relationship_type(self, source: str, target: str) -> Optional[RelationshipType]:
        """Infer relationship type from source/target IDs and (for VM) VM Control Type.

        Returns None if the edge should be skipped (e.g., redundant reverse references).
        """
        UNKNOWN = getattr(RelationshipType, "UNKNOWN", None)

        source_prefix = self._get_prefix(source)
        target_prefix = self._get_prefix(target)

        # DSC
        if source_prefix == "DSC" and target_prefix in ["Personnel", "PERS", "HA"]:
            return getattr(RelationshipType, "DSC_AFFECTS_PERSONNEL", UNKNOWN or RelationshipType.TECH_CONNECTS_TECH)

        if source_prefix == "DSC" and target_prefix in ["VM", "LEC"]:
            return getattr(RelationshipType, "DSC_AFFECTS_CONTROL", UNKNOWN or RelationshipType.TECH_CONNECTS_TECH)

        # VM: driven by VM.Control Type
        if source_prefix == "VM" and target_prefix in ["LEC", "VM", "DSC"]:
            return self._infer_vmc_relationship_from_vm_control_type(source)

        # LEC protects assets
        if source_prefix == "LEC" and target_prefix in ["TA", "BA"]:
            return getattr(RelationshipType, "LEC_PROTECTS_ASSET", UNKNOWN or RelationshipType.TECH_CONNECTS_TECH)

        # Assets
        if source_prefix == "TA" and target_prefix == "BA":
            return getattr(RelationshipType, "TECH_HOSTS_BUSINESS", UNKNOWN or RelationshipType.TECH_CONNECTS_TECH)

        if source_prefix == "TA" and target_prefix == "TA":
            return getattr(RelationshipType, "TECH_CONNECTS_TECH", UNKNOWN or RelationshipType.TECH_CONNECTS_TECH)

        # BA -> TA from "Asset Connections" sheet: the canonical direction is
        # TA -> BA (TECH_HOSTS_BUSINESS).  Return the relationship type and let
        # the caller reverse the edge direction.
        if source_prefix == "BA" and target_prefix == "TA":
            return getattr(RelationshipType, "TECH_HOSTS_BUSINESS", UNKNOWN or RelationshipType.TECH_CONNECTS_TECH)

        # tolerate reverse references
        if source_prefix == "TA" and target_prefix == "LEC":
            return getattr(RelationshipType, "LEC_PROTECTS_ASSET", UNKNOWN or RelationshipType.TECH_CONNECTS_TECH)

        # LEC -> VM marks are redundant reverse references from symmetric matrix.
        # An LEC doesn't have an outgoing relationship to a VMC.
        # Skip these edges (return None to signal caller to drop).
        if source_prefix == "LEC" and target_prefix == "VM":
            return None  # Signal to skip this edge

        logger.warning("Unknown relationship type: %s -> %s (defaulting to UNKNOWN)", source, target)
        return UNKNOWN or getattr(RelationshipType, "TECH_CONNECTS_TECH")

    def _infer_vmc_relationship_from_vm_control_type(self, vm_id: str) -> RelationshipType:
        """
        Map VM 'Control Type' (sheet VM, column Control Type) to RelationshipType.
        Uses tolerant matching (not only exact strings).
        """
        UNKNOWN = getattr(RelationshipType, "UNKNOWN", None)

        ct = self._vm_control_type_by_id.get(str(vm_id).strip(), "")
        k = re.sub(r"\s+", " ", str(ct or "").strip().lower())

        # tolerant matching
        if "reduce" in k and ("freq" in k or "frequency" in k or "change" in k):
            return getattr(RelationshipType, "VMC_REDUCES_CHANGE_FREQ", UNKNOWN or getattr(RelationshipType, "VMC_MONITORS"))
        if "reduce" in k and ("prob" in k or "probability" in k):
            return getattr(RelationshipType, "VMC_REDUCES_VAR_PROB", UNKNOWN or getattr(RelationshipType, "VMC_MONITORS"))
        if "threat" in k and ("intel" in k or "intelligence" in k):
            return getattr(RelationshipType, "VMC_THREAT_INTEL", UNKNOWN or getattr(RelationshipType, "VMC_MONITORS"))
        if "monitor" in k or "controls monitoring" in k:
            return getattr(RelationshipType, "VMC_MONITORS", UNKNOWN or getattr(RelationshipType, "VMC_MONITORS"))
        if "treatment" in k and ("select" in k or "prior" in k or "priorit" in k):
            return getattr(RelationshipType, "VMC_SELECTS_TREATMENT", UNKNOWN or getattr(RelationshipType, "VMC_MONITORS"))
        if "implement" in k:
            return getattr(RelationshipType, "VMC_IMPLEMENTS_REMEDIATION", UNKNOWN or getattr(RelationshipType, "VMC_MONITORS"))
        if "remediat" in k:
            return getattr(RelationshipType, "VMC_REMEDIATES", UNKNOWN or getattr(RelationshipType, "VMC_MONITORS"))

        logger.warning("VM '%s' has unknown Control Type '%s' -> UNKNOWN relationship", vm_id, ct)
        return UNKNOWN or getattr(RelationshipType, "VMC_MONITORS")

    def _get_prefix(self, agent_id: str) -> str:
        match = re.match(r"^([A-Za-z]+)", str(agent_id))
        return match.group(1) if match else str(agent_id)

    def _print_debug_dump(self, data: Dict[str, Any]) -> None:
        print("\n=== Sheet columns (as loaded) ===")
        for sheet, df in self._params_data.items():
            print(f"{sheet}: {list(df.columns)}")

        print("\n=== Parsed counts ===")
        for key in (
            "dsc_params",
            "vmc_params",
            "lec_params",
            "tech_asset_params",
            "business_asset_params",
            "threat_source_params",
            "threat_agent_params",
            "personnel_params",
            "edges",
        ):
            print(f"{key}: {len(data.get(key, []))}")

        print("\n=== Topology mismatch (core nodes only) ===")
        print("missing:", data.get("topology_missing_ids", []))
        print("extra:", data.get("topology_extra_ids", []))
        print()
