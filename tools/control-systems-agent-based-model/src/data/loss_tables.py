# src/data/loss_tables.py
"""src/data/loss_tables.py

Loss magnitude lookup tables and empirical samplers.

- EmpiricalBreachSampler: data breach loss from IRIS 2025 empirical distributions
- EmpiricalOutageSampler: business interruption loss from NetDiligence empirical distributions
- LossMagnitudeTables: legacy CSV-based outage lookup (fallback if JSON not configured)

Expected CSV format:
- Two header rows (MultiIndex) where the first two columns define a bin range:
    Outage: Dur Min, Dur Max
- Remaining columns are grouped loss components with subcolumns: Min, ML, Max

Lookup policy for out-of-range values:
- loss.tables.lookup_policy:
    - "clamp"   (default): below min -> first bin, above max -> last bin
    - "nearest": choose bin with closest boundary
    - "fail":    return None (caller will raise/fallback)

Path handling:
The project typically stores calibrated tables under "calibration/loss_tables" at
the repository root. When running scripts from a subdirectory (e.g., "scripts/"),
relative paths may not resolve. This module therefore resolves paths robustly by
also trying the repository root.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import logging
import numpy as np
import pandas as pd

from ..config import get_config

logger = logging.getLogger(__name__)
config = get_config()


@dataclass
class LossBinRow:
    lo: float
    hi: float
    components: Dict[str, Tuple[float, float, float]]  # comp -> (min, ml, max)


class LossMagnitudeTables:
    """Loads and samples from calibrated loss tables.

    Currently supports outage tables (bins by duration in hours).
    Data breach magnitude is handled by EmpiricalBreachSampler.
    """

    def __init__(
        self,
        outage_table_path: Optional[str] = None,
    ):
        self.outage_table_path = str(outage_table_path) if outage_table_path else None

        self._outage_bins: List[LossBinRow] = []

        if self.outage_table_path:
            self._outage_bins = self._load_table(self.outage_table_path, kind="outage")

        logger.info(
            "LossMagnitudeTables loaded: outage_bins=%s",
            len(self._outage_bins),
        )

    # -------------------------
    # Public sampling API
    # -------------------------

    def has_outage(self) -> bool:
        return bool(self._outage_bins)

    def sample_outage_total(self, duration_hours: float, rng: np.random.RandomState) -> float:
        row = self._lookup_bin(self._outage_bins, float(duration_hours), kind="outage")
        if row is None:
            raise KeyError(f"No outage bin matched duration_hours={duration_hours}")
        return self._sample_components_total(row, rng)

    # -------------------------
    # Internals
    # -------------------------

    def _resolve_table_path(self, path: str) -> Path:
        """Resolve a table path robustly.

        Resolution order:
          1) As provided (absolute or relative to CWD)
          2) Relative to the repository root (two levels above src/)
          3) Convenience: <repo_root>/calibration/loss_tables/<filename>
        """

        p = Path(path)

        # 1) As provided
        if p.is_absolute():
            if p.exists():
                return p
        else:
            if p.exists():
                return p.resolve()

        # 2) Relative to repo root
        repo_root = Path(__file__).resolve().parents[2]
        p2 = repo_root / p
        if p2.exists():
            return p2

        # 3) Convenience: allow passing just the filename or partial path
        p3 = repo_root / "calibration" / "loss_tables" / p.name
        if p3.exists():
            return p3

        tried = [str(p), str(p2), str(p3)]
        raise FileNotFoundError(f"Loss table not found: {path}. Tried: {', '.join(tried)}")

    def _load_table(self, path: str, kind: str) -> List[LossBinRow]:
        p = self._resolve_table_path(path)

        df = pd.read_csv(p, header=[0, 1])
        df.columns = self._normalize_columns(df.columns)

        lo_col, hi_col = self._infer_bin_cols(df.columns, kind=kind)
        component_cols = self._group_component_cols(df.columns, exclude={lo_col, hi_col})

        bins: List[LossBinRow] = []
        for _, r in df.iterrows():
            lo = float(r[lo_col])
            hi = float(r[hi_col])

            components: Dict[str, Tuple[float, float, float]] = {}
            for comp, cols in component_cols.items():
                cmin = float(r[cols["min"]])
                cml = float(r[cols["ml"]])
                cmax = float(r[cols["max"]])
                components[comp] = (cmin, cml, cmax)

            bins.append(LossBinRow(lo=lo, hi=hi, components=components))

        bins.sort(key=lambda x: x.lo)
        logger.info("Loaded %s loss bins from %s (%s)", len(bins), str(p), kind)
        return bins

    def _normalize_columns(self, cols: pd.MultiIndex) -> pd.MultiIndex:
        groups: List[str] = []
        subs: List[str] = []
        last_group = ""

        for g, s in cols:
            g = "" if g is None else str(g).strip()
            s = "" if s is None else str(s).strip()

            if (not g) or str(g).lower().startswith("unnamed"):
                g = last_group
            else:
                last_group = g

            s_norm = s.strip().lower()
            if s_norm in ("ml", "most likely", "most_likely", "mode"):
                s_norm = "ml"
            elif s_norm in ("min", "minimum"):
                s_norm = "min"
            elif s_norm in ("max", "maximum"):
                s_norm = "max"
            else:
                s_norm = s

            groups.append(g)
            subs.append(s_norm)

        return pd.MultiIndex.from_arrays([groups, subs])

    def _infer_bin_cols(self, cols: pd.MultiIndex, kind: str) -> Tuple[Tuple[str, str], Tuple[str, str]]:
        sub_names = [str(s).strip().lower() for _, s in cols]

        def find_sub(target: str) -> Tuple[str, str]:
            t = target.lower()
            for (g, s), sn in zip(cols, sub_names):
                if sn == t:
                    return (g, s)
            raise KeyError(f"Could not find required bin column '{target}' in table headers")

        lo = find_sub("dur min")
        hi = find_sub("dur max")

        return lo, hi

    def _group_component_cols(
        self,
        cols: pd.MultiIndex,
        exclude: set,
    ) -> Dict[str, Dict[str, Tuple[str, str]]]:
        comps: Dict[str, Dict[str, Tuple[str, str]]] = {}

        for (g, s) in cols:
            if (g, s) in exclude:
                continue

            comp = (g or "").strip()
            if not comp:
                continue

            sub = str(s).strip().lower()
            if sub not in ("min", "ml", "max"):
                continue

            comps.setdefault(comp, {})
            comps[comp][sub] = (g, s)

        complete: Dict[str, Dict[str, Tuple[str, str]]] = {}
        for comp, d in comps.items():
            if all(k in d for k in ("min", "ml", "max")):
                complete[comp] = d

        if not complete:
            raise ValueError("No complete component triplets (min/ml/max) were found in loss table")

        return complete

    def _lookup_bin(self, bins: List[LossBinRow], x: float, kind: str) -> Optional[LossBinRow]:
        if not bins:
            return None

        # exact match first
        for b in bins:
            if b.lo <= x <= b.hi:
                return b

        policy_val = config.get("loss.tables.lookup_policy", None)
        if policy_val is None:
            raise ValueError("Missing required config: loss.tables.lookup_policy")
        policy = str(policy_val).lower()
        min_lo = bins[0].lo
        max_hi = bins[-1].hi

        if policy == "fail":
            return None

        if policy == "clamp":
            if x < min_lo:
                logger.debug("Clamping %s=%s to first bin [%s,%s]", kind, x, bins[0].lo, bins[0].hi)
                return bins[0]
            if x > max_hi:
                logger.debug("Clamping %s=%s to last bin [%s,%s]", kind, x, bins[-1].lo, bins[-1].hi)
                return bins[-1]
            return None

        if policy == "nearest":
            best = None
            best_dist = float("inf")
            for b in bins:
                if x < b.lo:
                    d = b.lo - x
                elif x > b.hi:
                    d = x - b.hi
                else:
                    d = 0.0
                if d < best_dist:
                    best_dist = d
                    best = b
            return best

        raise ValueError(
            f"Invalid loss.tables.lookup_policy='{policy}'. Allowed: fail | clamp | nearest"
        )

    def _sample_components_total(self, row: LossBinRow, rng: np.random.RandomState) -> float:
        """Sample loss components using Beta-PERT distribution (KB §01, §04).

        FAIR methodology uses Beta-PERT for loss magnitude estimation. Standard
        lambda=4 provides appropriate tail weight for cyber risk scenarios where
        extreme losses are more probable than triangular would suggest.
        """
        total = 0.0
        lam = 4.0  # Standard PERT confidence parameter
        for _, (cmin, cml, cmax) in row.components.items():
            lo = min(cmin, cml, cmax)
            hi = max(cmin, cml, cmax)
            mode = float(np.clip(cml, lo, hi))
            if hi <= lo:
                total += lo
                continue
            alpha = 1.0 + lam * (mode - lo) / (hi - lo)
            beta = 1.0 + lam * (hi - mode) / (hi - lo)
            x = float(rng.beta(alpha, beta))
            total += lo + x * (hi - lo)
        return float(total)


# ---------------------------------------------------------------------------
# Empirical breach loss sampler (replaces record-count-binned tables)
# ---------------------------------------------------------------------------

_Z_P95 = 1.6449
_Z_P90 = 1.2816


class EmpiricalBreachSampler:
    """Samples data breach loss magnitude from IRIS 2025 empirical distributions.

    Lookup strategy (fallback ladder):
      1. scenario_type anchor (ransomware/data_breach/insider) as base distribution
      2. Multiply by sector ratio (sector_median / baseline_median)
      3. Multiply by revenue ratio (revenue_median / baseline_median)
      If scenario_type unknown → use baseline directly with sector+revenue scaling.

    Dwell time does NOT scale magnitude here. Per FAIR-CAM it avoids asserting specific
    time-to-loss curves. For information assets, detection stage determines outcome class
    (via stage-gated detection model), not a continuous dwell multiplier.
    Outage/process assets retain duration-based magnitude lookup because business interruption cost IS time-driven.
    """

    def __init__(self, json_path: Optional[str] = None):
        import json as _json

        if json_path is None:
            json_path = str(config.get("loss.tables.empirical_breach_json", None) or "")
            if not json_path:
                raise ValueError("Missing config: loss.tables.empirical_breach_json")

        resolved = self._resolve_path(json_path)
        with open(resolved, "r", encoding="utf-8") as f:
            self._data = _json.load(f)

        self._baseline = self._data["baseline"]
        self._by_scenario = self._data.get("by_scenario_type", {})
        self._by_sector = self._data.get("by_sector", {})
        self._by_revenue = self._data.get("by_revenue_bucket", {})

        logger.info(
            "EmpiricalBreachSampler loaded: scenarios=%d, sectors=%d, revenue_buckets=%d",
            len(self._by_scenario), len(self._by_sector), len(self._by_revenue),
        )

    def sample(
        self,
        rng: np.random.RandomState,
        scenario_type: Optional[str] = None,
        sector: Optional[str] = None,
        revenue_bucket: Optional[str] = None,
    ) -> float:
        mu, sigma = self._resolve_distribution(scenario_type, sector, revenue_bucket)
        return max(0.0, float(np.exp(rng.normal(mu, sigma))))

    def _resolve_distribution(
        self,
        scenario_type: Optional[str],
        sector: Optional[str],
        revenue_bucket: Optional[str],
    ) -> tuple:
        baseline_median = float(self._baseline["median"])
        baseline_p95 = float(self._baseline["p95"])

        if scenario_type and scenario_type in self._by_scenario:
            entry = self._by_scenario[scenario_type]
            base_median = float(entry["median"])
            upper = float(entry["upper_percentile"])
            ptype = entry.get("percentile_type", "p90")
            z = _Z_P95 if ptype == "p95" else _Z_P90
            mu = np.log(base_median)
            sigma = (np.log(upper) - mu) / z
        else:
            base_median = baseline_median
            mu = np.log(baseline_median)
            sigma = (np.log(baseline_p95) - mu) / _Z_P95

        sector_mult = 1.0
        if sector:
            s_key = sector.lower().replace(" ", "_")
            if s_key in self._by_sector:
                sector_mult = float(self._by_sector[s_key]["median"]) / baseline_median

        revenue_mult = 1.0
        if revenue_bucket:
            r_key = revenue_bucket.lower().replace(" ", "_")
            if r_key in self._by_revenue:
                revenue_mult = float(self._by_revenue[r_key]["median"]) / baseline_median

        combined_mult = sector_mult * revenue_mult
        mu_adjusted = mu + np.log(combined_mult)

        return float(mu_adjusted), float(sigma)

    @staticmethod
    def _resolve_path(path: str) -> Path:
        p = Path(path)
        if p.exists():
            return p.resolve() if not p.is_absolute() else p
        repo_root = Path(__file__).resolve().parents[2]
        p2 = repo_root / p
        if p2.exists():
            return p2
        p3 = repo_root / "calibration" / "loss_tables" / p.name
        if p3.exists():
            return p3
        raise FileNotFoundError(f"Empirical breach data not found: {path}")


# ---------------------------------------------------------------------------
# Empirical outage (BI) loss sampler (replaces duration-binned CSV tables)
# ---------------------------------------------------------------------------


def _z_for_max_of_n(n: int) -> float:
    """z-score for max order statistic of N iid standard-normal draws."""
    from scipy.stats import norm
    return float(norm.ppf(1.0 - 1.0 / (2.0 * n)))


class EmpiricalOutageSampler:
    """Samples business interruption loss from NetDiligence empirical distributions.

    Duration scales the draw: BI cost is proportional to outage length.
    The lognormal base distribution is anchored on NetDiligence ransomware
    BI claims (SME: avg $1M, N=294; large: avg $27.9M, N=15) at a
    reference duration of 72 hours. The sampled value is scaled by
    (duration_hours / reference_duration_hours).

    Revenue bucket lookup maps IRIS-style buckets to NetDiligence tiers
    (sme_under_2b / large_over_2b) via a mapping table in the JSON.
    """

    def __init__(self, json_path: Optional[str] = None):
        import json as _json

        if json_path is None:
            json_path = str(config.get("loss.tables.empirical_outage_json", None) or "")
            if not json_path:
                raise ValueError("Missing config: loss.tables.empirical_outage_json")

        resolved = self._resolve_path(json_path)
        with open(resolved, "r", encoding="utf-8") as f:
            self._data = _json.load(f)

        self._baseline = self._data["baseline"]
        self._by_revenue = self._data.get("by_revenue_bucket", {})
        self._revenue_mapping = self._data.get("_revenue_bucket_mapping", {})
        self._reference_hours = float(self._data.get("reference_duration_hours", 72))

        self._z_cache: Dict[int, float] = {}

        logger.info(
            "EmpiricalOutageSampler loaded: reference_hours=%.0f, revenue_buckets=%d",
            self._reference_hours, len(self._by_revenue),
        )

    def sample(
        self,
        rng: np.random.RandomState,
        duration_hours: float,
        revenue_bucket: Optional[str] = None,
    ) -> float:
        if duration_hours <= 0:
            return 0.0

        entry = self._resolve_entry(revenue_bucket)
        mu, sigma = self._fit_lognormal(entry)

        base_draw = float(np.exp(rng.normal(mu, sigma)))
        scaled = base_draw * (duration_hours / self._reference_hours)
        return max(0.0, scaled)

    def _resolve_entry(self, revenue_bucket: Optional[str]) -> dict:
        if revenue_bucket:
            r_key = revenue_bucket.lower().replace(" ", "_")
            mapped = self._revenue_mapping.get(r_key, r_key)
            if mapped in self._by_revenue:
                return self._by_revenue[mapped]

        return self._baseline

    def _fit_lognormal(self, entry: dict) -> Tuple[float, float]:
        avg = float(entry["avg_usd"])
        upper = float(entry["max_usd"])
        n = int(entry.get("n", 294))

        mu = np.log(avg)
        z = self._z_for_n(n)
        sigma = (np.log(upper) - mu) / z

        return float(mu), float(max(sigma, 0.1))

    def _z_for_n(self, n: int) -> float:
        if n not in self._z_cache:
            self._z_cache[n] = _z_for_max_of_n(n)
        return self._z_cache[n]

    @staticmethod
    def _resolve_path(path: str) -> Path:
        p = Path(path)
        if p.exists():
            return p.resolve() if not p.is_absolute() else p
        repo_root = Path(__file__).resolve().parents[2]
        p2 = repo_root / p
        if p2.exists():
            return p2
        p3 = repo_root / "calibration" / "loss_tables" / p.name
        if p3.exists():
            return p3
        raise FileNotFoundError(f"Empirical outage data not found: {path}")
