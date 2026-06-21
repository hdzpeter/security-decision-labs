"""
Data acquisition and refresh pipeline.

Automates data fetching where possible, validates completeness otherwise.

    tef-estimator refresh snapshot   # Fetch API data
    tef-estimator refresh check      # Validate staleness
    tef-estimator refresh full       # Both
"""

from tef_estimator.refresh.fetchers import run_snapshot_refresh
from tef_estimator.refresh.validators import check_freshness, run_check

__all__ = ["run_snapshot_refresh", "run_check", "check_freshness"]
