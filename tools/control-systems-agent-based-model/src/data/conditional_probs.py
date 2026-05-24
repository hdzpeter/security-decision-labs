"""src/data/conditional_probs.py

DSC conditional probability tables (misalignment table).

The table defines P(misaligned decision) given the 5 DSC dimensions:
  expectation_alignment, awareness, capability, situational, incentive

Each dimension is a boolean "final_success" after intrinsic+correction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Tuple, Optional
import csv

from ..config import get_config


Key = Tuple[bool, bool, bool, bool, bool]


@dataclass(frozen=True)
class ConditionalProbTable:
    """Mapping from (G,A,C,S,I) -> p_misaligned"""
    name: str
    probs: Dict[Key, float]


def _boolish(v) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "t", "yes", "y", "on"):
        return True
    if s in ("0", "false", "f", "no", "n", "off"):
        return False
    raise ValueError(f"Not a boolean value: {v!r}")


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _build_from_rows(name: str, rows: Iterable[Mapping]) -> ConditionalProbTable:
    rows_list = list(rows)
    if not rows_list:
        raise ValueError(f"Conditional prob table '{name}' has no rows.")

    has_governance = "expectation_alignment" in rows_list[0]

    probs: Dict[Key, float] = {}

    if has_governance:
        # 5-dimension table: expect 32 rows (E, A, C, S, I)
        for r in rows_list:
            g = _boolish(r["expectation_alignment"])
            a = _boolish(r["awareness"])
            c = _boolish(r["capability"])
            s = _boolish(r["situational"])
            i = _boolish(r["incentive"])
            p = _clamp01(float(r["p_misaligned"]))
            probs[(g, a, c, s, i)] = p

        if len(probs) != 32:
            missing = 32 - len(probs)
            raise ValueError(
                f"Conditional prob table '{name}' must define all 32 combinations "
                f"(5 dimensions), but has {len(probs)} entries (missing {missing})."
            )
    else:
        # Legacy 4-dimension table (16 rows): duplicate each row for both
        # expectation_alignment=True and expectation_alignment=False, preserving backward compat.
        for r in rows_list:
            a = _boolish(r["awareness"])
            c = _boolish(r["capability"])
            s = _boolish(r["situational"])
            i = _boolish(r["incentive"])
            p = _clamp01(float(r["p_misaligned"]))
            probs[(True, a, c, s, i)] = p
            probs[(False, a, c, s, i)] = p

        if len(probs) != 32:
            missing = 32 - len(probs)
            raise ValueError(
                f"Conditional prob table '{name}' must define all 16 legacy combinations "
                f"(4 dimensions), but has {len(probs) // 2} entries (missing {missing // 2})."
            )

    return ConditionalProbTable(name=name, probs=probs)


def load_conditional_prob_table_from_config() -> ConditionalProbTable:
    """
    Load the DSC conditional probability table from YAML config.

    Supported config forms:

    dsc_decision:
      conditional_prob_table:
        name: "phase2_default"
        inline:
          - expectation_alignment: true
            awareness: true
            capability: true
            situational: true
            incentive: true
            p_misaligned: 0.02
          ... (32 rows, or 16 rows without expectation_alignment for backward compat)

    OR

    dsc_decision:
      conditional_prob_table:
        name: "phase2_csv"
        csv_path: "calibration/dsc_conditional_probs.csv"
    """
    cfg = get_config()
    table_cfg = cfg.get_section("dsc_decision").get("conditional_prob_table", None)
    if not table_cfg or not isinstance(table_cfg, dict):
        raise ValueError(
            "Missing required config: dsc_decision.conditional_prob_table "
            "(no hard-coded defaults are allowed)."
        )

    name = str(table_cfg.get("name", "dsc_table")).strip() or "dsc_table"
    inline = table_cfg.get("inline", None)
    csv_path = table_cfg.get("csv_path", None)

    if inline is not None:
        if not isinstance(inline, list):
            raise ValueError("dsc_decision.conditional_prob_table.inline must be a list of rows")
        return _build_from_rows(name=name, rows=inline)

    if csv_path:
        abs_path = cfg.resolve_path(str(csv_path), base="project")
        rows: List[dict] = []
        with open(abs_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required = {"awareness", "capability", "situational", "incentive", "p_misaligned"}
            missing_cols = required - set((reader.fieldnames or []))
            if missing_cols:
                raise ValueError(f"CSV missing required columns: {sorted(missing_cols)}")
            # expectation_alignment column is optional for backward compat (16-row legacy tables)
            for r in reader:
                rows.append(r)
        return _build_from_rows(name=name, rows=rows)

    raise ValueError(
        "dsc_decision.conditional_prob_table must include either 'inline' or 'csv_path'."
    )


def get_misalignment_probability(
    expectation_alignment_ok: bool,
    awareness_ok: bool,
    capability_ok: bool,
    situational_ok: bool,
    incentive_ok: bool,
    table: ConditionalProbTable,
) -> float:
    key: Key = (bool(expectation_alignment_ok), bool(awareness_ok), bool(capability_ok), bool(situational_ok), bool(incentive_ok))
    if key not in table.probs:
        raise KeyError(f"Missing key {key} in conditional probability table '{table.name}'")
    return float(table.probs[key])


# Cached default table, still config-driven (loaded on first use)
_CACHED_DEFAULT_TABLE: Optional[ConditionalProbTable] = None


def get_default_conditional_prob_table() -> ConditionalProbTable:
    global _CACHED_DEFAULT_TABLE
    if _CACHED_DEFAULT_TABLE is None:
        _CACHED_DEFAULT_TABLE = load_conditional_prob_table_from_config()
    return _CACHED_DEFAULT_TABLE
