"""
Peer percentile computation.

Runs the engine against a grid of profiles -- all sector/revenue/geo
combinations at default technology settings -- and reports where the
current estimate falls relative to peers.

"Your positioned TEF of 1.8% is at the 78th percentile across all
mid-market profiles."
"""

from __future__ import annotations

import json
from pathlib import Path

from tef_estimator.data.common import Geography, RevenueBand, Sector
from tef_estimator.profile import OrganizationProfile


def build_grid(engine) -> dict[str, list[float]]:
    """Evaluate TEF for all sector x revenue_band x geography combos.

    Returns a dict keyed by revenue band value, each containing a sorted
    list of positioned_median values.
    """
    grid: dict[str, list[float]] = {}

    for band in RevenueBand:
        modes = []
        for sector in Sector:
            for geo in Geography:
                profile = OrganizationProfile(
                    sector=sector,
                    revenue_band=band,
                    geography=geo,
                )
                result = engine.estimate(profile)
                modes.append(result.total_positioned_median)
        grid[band.value] = sorted(modes)

    return grid


def percentile(tef_mode: float, grid: dict[str, list[float]], revenue_band: RevenueBand) -> int:
    """Compute where tef_mode falls within its revenue band peers.

    Returns an integer 0-100.
    """
    band_values = grid.get(revenue_band.value, [])
    if not band_values:
        return 50  # No data

    count_below = sum(1 for v in band_values if v <= tef_mode)
    return round((count_below / len(band_values)) * 100)


def save_grid(grid: dict[str, list[float]], path: Path) -> None:
    """Save peer grid to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(grid, f, indent=2)


def load_grid(path: Path) -> dict[str, list[float]] | None:
    """Load peer grid from JSON, or None if not found."""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def compute_and_set_percentile(
    result,
    revenue_band: RevenueBand,
    grid: dict[str, list[float]],
) -> None:
    """Compute and set peer percentile on a TEFResult."""
    pct = percentile(result.total_positioned_median, grid, revenue_band)
    result.peer_percentile = pct
    context = revenue_band.value.replace("_", "-")
    qualifiers = []
    qualifiers.append("tech-neutral peers")
    if result.has_credibility_data:
        qualifiers.append("excludes org-specific telemetry")
    context += " (" + "; ".join(qualifiers) + ")"
    result.peer_context = context
