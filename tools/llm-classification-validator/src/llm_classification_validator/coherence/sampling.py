"""Stratified sampling for coherence validation.

This module produces a statistically sufficient stratified
sample plan based on the cross-tabulation of source and target categories
assigned by the LLM, so that every mapping region is represented in the
human review set.
"""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SamplePlan:
    """A reproducible sampling plan for manual coherence review.

    Attributes
    ----------
    sample_ids:
        Item IDs selected for review.
    total_items:
        Total number of items in the population.
    sample_size:
        Number of items in the sample (== len(sample_ids)).
    strata:
        Mapping of stratum label ``"(source_cat, target_cat)"`` to count
        of items drawn from that stratum.
    warnings:
        Human-readable warnings about coverage or sufficiency problems.
    sufficient:
        ``True`` when the plan meets all critical thresholds.
    """

    sample_ids: list[str]
    total_items: int
    sample_size: int
    strata: dict[str, int]
    warnings: list[str] = field(default_factory=list)
    sufficient: bool = True

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: str | Path) -> SamplePlan:
        return cls(**json.loads(Path(path).read_text()))


def _stratum_key(source_cat: str, target_cat: str) -> str:
    """Canonical string key for a (source, target) stratum."""
    return f"({source_cat}, {target_cat})"


def compute_sample_plan(
    items: list[dict[str, Any]],
    *,
    min_per_stratum: int = 3,
    min_total: int = 20,
    confidence: float = 0.90,
    seed: int = 42,
) -> SamplePlan:
    """Build a stratified sample plan for manual coherence review.

    Stratification is by the cross-tabulation of ``source_category`` and
    ``target_category``.  Items missing either field are placed in an
    ``"_unknown"`` stratum on that axis.

    Parameters
    ----------
    items:
        List of item dicts.  Each must contain ``"id"``; optionally
        ``"source_category"`` and ``"target_category"``.
    min_per_stratum:
        Minimum items drawn from every stratum (or all items if the
        stratum is smaller).
    min_total:
        Minimum total sample size.
    confidence:
        Confidence level (used for sufficiency messaging; the sample
        is always at least ``min_total``).
    seed:
        Random seed for reproducibility.

    Returns
    -------
    SamplePlan
    """
    rng = random.Random(seed)
    warnings: list[str] = []
    sufficient = True

    if not items:
        return SamplePlan(
            sample_ids=[],
            total_items=0,
            sample_size=0,
            strata={},
            warnings=["No items provided"],
            sufficient=False,
        )

    # ── 1. Group items into strata ──────────────────────────────────
    strata_items: dict[str, list[str]] = defaultdict(list)
    for item in items:
        src = item.get("source_category", "_unknown")
        tgt = item.get("target_category", "_unknown")
        strata_items[_stratum_key(src, tgt)].append(item["id"])

    # ── 2. Guaranteed minimum per stratum ───────────────────────────
    selected: set[str] = set()
    strata_counts: dict[str, int] = {}

    for key, ids in strata_items.items():
        rng.shuffle(ids)
        take = min(min_per_stratum, len(ids))
        for item_id in ids[:take]:
            selected.add(item_id)
        strata_counts[key] = take

        if len(ids) < min_per_stratum:
            warnings.append(
                f"Stratum {key}: only {len(ids)} item(s), "
                f"below minimum {min_per_stratum}"
            )

    # ── 3. Top-up to reach min_total, proportional to stratum size ─
    remaining_needed = max(0, min_total - len(selected))

    if remaining_needed > 0:
        # Build pool of not-yet-selected items, grouped by stratum
        pool_by_stratum: dict[str, list[str]] = {}
        total_pool = 0
        for key, ids in strata_items.items():
            available = [i for i in ids if i not in selected]
            if available:
                pool_by_stratum[key] = available
                total_pool += len(available)

        if total_pool > 0:
            # Proportional allocation (rounding down, then fill remainder)
            alloc: dict[str, int] = {}
            allocated = 0
            for key, available in pool_by_stratum.items():
                share = int(
                    math.floor(remaining_needed * len(available) / total_pool)
                )
                share = min(share, len(available))
                alloc[key] = share
                allocated += share

            # Distribute leftover slots one per stratum (largest first)
            leftover = remaining_needed - allocated
            if leftover > 0:
                ordered = sorted(
                    pool_by_stratum.keys(),
                    key=lambda k: len(pool_by_stratum[k]) - alloc.get(k, 0),
                    reverse=True,
                )
                for key in ordered:
                    if leftover <= 0:
                        break
                    headroom = len(pool_by_stratum[key]) - alloc[key]
                    add = min(leftover, headroom)
                    alloc[key] += add
                    leftover -= add

            for key, count in alloc.items():
                available = pool_by_stratum[key]
                rng.shuffle(available)
                for item_id in available[:count]:
                    selected.add(item_id)

            strata_counts = _recount_strata(items, selected, strata_items)

    # ── 4. Sufficiency checks ───────────────────────────────────────
    sample_size = len(selected)

    if sample_size < min_total:
        if len(items) >= min_total:
            warnings.append(
                f"Sample size {sample_size} is below minimum {min_total}"
            )
            sufficient = False
        else:
            warnings.append(
                f"Population ({len(items)}) is smaller than "
                f"minimum sample size ({min_total}); "
                f"sampling all items"
            )

    # Sort IDs for deterministic output
    sample_ids = sorted(selected)

    return SamplePlan(
        sample_ids=sample_ids,
        total_items=len(items),
        sample_size=len(sample_ids),
        strata=strata_counts,
        warnings=warnings,
        sufficient=sufficient,
    )


def _recount_strata(
    items: list[dict[str, Any]],
    selected: set[str],
    strata_items: dict[str, list[str]],
) -> dict[str, int]:
    """Recount how many selected items fall in each stratum."""
    counts: dict[str, int] = {}
    for key, ids in strata_items.items():
        n = sum(1 for i in ids if i in selected)
        if n > 0:
            counts[key] = n
    return counts


def check_sample_sufficiency(
    sample_ids: list[str],
    items: list[dict[str, Any]],
    *,
    min_per_stratum: int = 3,
    min_total: int = 20,
) -> tuple[list[str], bool]:
    """Check whether an existing sample adequately covers all strata.

    Use this to validate a hand-picked or externally generated sample
    against the same stratification rules used by :func:`compute_sample_plan`.

    Parameters
    ----------
    sample_ids:
        IDs of items already in the sample.
    items:
        Full population (same format as ``compute_sample_plan``).
    min_per_stratum:
        Required minimum items per stratum.
    min_total:
        Required minimum total sample size.

    Returns
    -------
    (warnings, sufficient):
        A list of human-readable warnings and a boolean indicating
        whether the sample meets all requirements.
    """
    warnings: list[str] = []
    sufficient = True
    sample_set = set(sample_ids)

    if not items:
        return ["No items provided"], False

    # Build strata from full population
    strata_items: dict[str, list[str]] = defaultdict(list)
    for item in items:
        src = item.get("source_category", "_unknown")
        tgt = item.get("target_category", "_unknown")
        strata_items[_stratum_key(src, tgt)].append(item["id"])

    # Check coverage per stratum
    for key, ids in strata_items.items():
        sampled = [i for i in ids if i in sample_set]
        if len(sampled) == 0:
            warnings.append(f"Stratum {key}: not covered (0 of {len(ids)} items)")
            sufficient = False
        elif len(sampled) < min_per_stratum and len(ids) >= min_per_stratum:
            warnings.append(
                f"Stratum {key}: underrepresented "
                f"({len(sampled)} of {len(ids)}, minimum {min_per_stratum})"
            )
            sufficient = False

    # Check total size
    total_sampled = len(sample_set)
    if total_sampled < min_total and len(items) >= min_total:
        warnings.append(
            f"Total sample size {total_sampled} is below minimum {min_total}"
        )
        sufficient = False

    return warnings, sufficient
