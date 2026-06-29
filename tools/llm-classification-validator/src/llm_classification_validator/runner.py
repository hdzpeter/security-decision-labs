"""Orchestrator: run all evaluation dimensions and consolidate results.

Supports running dimensions sequentially or in parallel where
dependencies allow. The pattern follows:

    Phase 1 (foundation): coherence, consistency, convergent -- sequential
    Phase 2 (advanced): adversarial, stability -- parallel
    Phase 3: consolidation
"""

from __future__ import annotations

import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from llm_classification_validator.models import DimensionReport, EvaluationReport, ItemReport, Verdict
from llm_classification_validator.verdict import aggregate_verdicts


# Type for a dimension runner: takes no args, returns a DimensionReport
DimensionRunner = Callable[[], DimensionReport]


def run_evaluation(
    foundation: list[DimensionRunner] | None = None,
    advanced: list[DimensionRunner] | None = None,
    parallel_advanced: bool = True,
    max_workers: int = 2,
) -> EvaluationReport:
    """Run a full evaluation across multiple dimensions.

    Parameters
    ----------
    foundation:
        Dimension runners for the foundation phase (run sequentially).
        Typically: coherence, consistency, convergent.
    advanced:
        Dimension runners for the advanced phase (can run in parallel).
        Typically: adversarial, stability.
    parallel_advanced:
        If True, run advanced dimensions in parallel.
    max_workers:
        Maximum parallel workers for the advanced phase.

    Returns
    -------
    EvaluationReport
        Consolidated report with per-dimension results and overall verdict.
    """
    dimension_reports: list[DimensionReport] = []

    total = len(foundation or []) + len(advanced or [])
    completed = 0

    # Phase 1: Foundation (sequential)
    if foundation:
        for runner in foundation:
            name = getattr(runner, "__name__", str(runner))
            print(f"  [{completed + 1}/{total}] Running {name}...", flush=True)
            start = time.time()
            try:
                report = runner()
                report.duration_s = time.time() - start
            except Exception as e:
                report = DimensionReport(
                    dimension="unknown",
                    verdict=Verdict.ERROR,
                    duration_s=time.time() - start,
                    error=str(e),
                )
            completed += 1
            print(f"         {report.dimension}: {report.verdict.value} ({report.duration_s:.1f}s)", flush=True)
            dimension_reports.append(report)

    # Phase 2: Advanced (parallel or sequential)
    if advanced:
        names = [getattr(r, "__name__", str(r)) for r in advanced]
        if parallel_advanced and len(advanced) > 1:
            print(f"  [{completed + 1}-{completed + len(advanced)}/{total}] Running {', '.join(names)} in parallel...", flush=True)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for runner in advanced:
                    futures[executor.submit(_timed_run, runner)] = runner

                for future in as_completed(futures):
                    report = future.result()
                    completed += 1
                    print(f"         {report.dimension}: {report.verdict.value} ({report.duration_s:.1f}s)", flush=True)
                    dimension_reports.append(report)
        else:
            for runner in advanced:
                name = getattr(runner, "__name__", str(runner))
                print(f"  [{completed + 1}/{total}] Running {name}...", flush=True)
                report = _timed_run(runner)
                completed += 1
                print(f"         {report.dimension}: {report.verdict.value} ({report.duration_s:.1f}s)", flush=True)
                dimension_reports.append(report)

    # Overall verdict
    verdicts = [r.verdict for r in dimension_reports]
    overall = aggregate_verdicts(verdicts)

    # Merge per-item issues from all dimensions
    issues_by_item: dict[str, list] = defaultdict(list)
    for report in dimension_reports:
        for issue in report.item_issues:
            issues_by_item[issue.item_id].append(issue)

    items = [
        ItemReport(item_id=item_id, issues=issues)
        for item_id, issues in sorted(issues_by_item.items())
    ]

    return EvaluationReport(
        overall_verdict=overall,
        dimensions=dimension_reports,
        items=items,
    )


def _timed_run(runner: DimensionRunner) -> DimensionReport:
    """Run a dimension runner with timing."""
    start = time.time()
    try:
        report = runner()
        report.duration_s = time.time() - start
        return report
    except Exception as e:
        return DimensionReport(
            dimension="unknown",
            verdict=Verdict.ERROR,
            duration_s=time.time() - start,
            error=str(e),
        )
