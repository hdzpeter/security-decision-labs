"""Watch mode: continuous monitoring with re-estimation on signal.

Pipeline: check schedule → collect due sources → integrate →
compare against baseline → re-estimate watched profiles if signals fire.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tef_estimator.telemetry.compare import CompareResult, compare
from tef_estimator.telemetry.db import TelemetryDB
from tef_estimator.telemetry.scheduler import run_due_collections

log = logging.getLogger(__name__)


@dataclass
class WatchProfile:
    """A profile to re-estimate when signals are detected."""
    name: str
    profile_kwargs: dict[str, Any]
    scenario_name: str | None = None


@dataclass
class WatchCycleResult:
    collection_results: list[dict[str, Any]]
    compare_result: CompareResult | None
    re_estimated: list[dict[str, Any]] = field(default_factory=list)

    @property
    def had_signals(self) -> bool:
        return self.compare_result is not None and self.compare_result.has_signals


def run_once(
    db: TelemetryDB,
    *,
    profiles: list[WatchProfile] | None = None,
    threshold: float = 0.20,
    force: bool = False,
    baseline_dir: Path | None = None,
    state_dir: Path | None = None,
) -> WatchCycleResult:
    """Execute one full watch cycle.

    1. Run due collectors + integrate
    2. Compare against baseline
    3. If signals, re-estimate any watched profiles
    """
    from tef_estimator.engine import TEFEngine
    from tef_estimator.profile import OrganizationProfile

    kwargs: dict[str, Any] = {"force": force}
    if state_dir:
        kwargs["state_dir"] = state_dir
    collection_results = run_due_collections(db, **kwargs)

    any_new_data = any(
        r.get("status") == "completed" and r.get("records_inserted", 0) > 0
        for r in collection_results
        if r.get("source") != "integrator"
    )

    compare_result = None
    re_estimated: list[dict[str, Any]] = []

    if any_new_data:
        compare_kwargs: dict[str, Any] = {"threshold": threshold}
        if baseline_dir:
            compare_kwargs["baseline_dir"] = baseline_dir
        compare_result = compare(db, **compare_kwargs)

        if compare_result.has_signals and profiles:
            log.info("Signals detected — re-estimating %d profile(s)", len(profiles))
            engine = TEFEngine()

            for wp in profiles:
                try:
                    profile = OrganizationProfile(**wp.profile_kwargs)
                    result = engine.estimate(profile)
                    re_estimated.append({
                        "profile": wp.name,
                        "composite_tef": result.composite_tef,
                        "signals_count": len(compare_result.signals),
                    })
                    log.info(
                        "  %s: composite TEF = %.4f",
                        wp.name, result.composite_tef,
                    )
                except Exception as e:
                    log.error("  Re-estimation failed for %s: %s", wp.name, e)
                    re_estimated.append({
                        "profile": wp.name,
                        "error": str(e),
                    })
    else:
        log.info("No new data — skipping compare")

    return WatchCycleResult(
        collection_results=collection_results,
        compare_result=compare_result,
        re_estimated=re_estimated,
    )


def watch_loop(
    db: TelemetryDB,
    *,
    interval_minutes: int = 60,
    profiles: list[WatchProfile] | None = None,
    threshold: float = 0.20,
    baseline_dir: Path | None = None,
    state_dir: Path | None = None,
    max_cycles: int | None = None,
) -> None:
    """Run the watch cycle repeatedly."""
    cycle = 0
    while True:
        cycle += 1
        log.info("=== Watch cycle %d ===", cycle)

        try:
            result = run_once(
                db,
                profiles=profiles,
                threshold=threshold,
                baseline_dir=baseline_dir,
                state_dir=state_dir,
            )

            if result.had_signals:
                log.info(
                    "Cycle %d: %d signal(s), %d re-estimation(s)",
                    cycle,
                    len(result.compare_result.signals),
                    len(result.re_estimated),
                )
            else:
                log.info("Cycle %d: no signals", cycle)

        except Exception as e:
            log.error("Cycle %d failed: %s", cycle, e)

        if max_cycles and cycle >= max_cycles:
            log.info("Reached max_cycles=%d, stopping", max_cycles)
            break

        log.info("Sleeping %d minutes...", interval_minutes)
        time.sleep(interval_minutes * 60)
