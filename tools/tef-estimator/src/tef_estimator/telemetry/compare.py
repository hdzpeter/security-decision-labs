"""Threshold-based change detection against a stored baseline.

After integration, compare current 7-day rolling averages against a
snapshot baseline. Emit signals when deviation exceeds the threshold.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from tef_estimator.telemetry.db import TelemetryDB

log = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.20
DEFAULT_BASELINE_DIR = Path.home() / ".tef-estimator"


@dataclass(frozen=True)
class Signal:
    source_id: str
    metric_name: str
    baseline_value: float
    current_value: float
    pct_change: float
    direction: str


@dataclass
class CompareResult:
    signals: list[Signal]
    metrics_checked: int
    threshold: float

    @property
    def has_signals(self) -> bool:
        return len(self.signals) > 0


def _baseline_path(baseline_dir: Path) -> Path:
    return baseline_dir / "telemetry_baseline.json"


def snapshot_baseline(
    db: TelemetryDB,
    *,
    baseline_dir: Path = DEFAULT_BASELINE_DIR,
) -> dict[str, dict[str, float]]:
    """Save current 7-day rolling averages as the baseline."""
    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute(
        """SELECT source_id, metric_name, value
           FROM time_series
           WHERE metric_name LIKE '%_7d_avg'
             AND series_date = (
                 SELECT MAX(series_date) FROM time_series
                 WHERE metric_name LIKE '%_7d_avg'
             )"""
    )
    rows = cursor.fetchall()
    conn.close()

    baseline: dict[str, dict[str, float]] = {}
    for source_id, metric_name, value in rows:
        baseline.setdefault(source_id, {})[metric_name] = value

    baseline_dir.mkdir(parents=True, exist_ok=True)
    path = _baseline_path(baseline_dir)
    path.write_text(json.dumps(baseline, indent=2))

    total = sum(len(v) for v in baseline.values())
    log.info("Baseline saved: %d metrics across %d sources → %s",
             total, len(baseline), path)

    return baseline


def load_baseline(
    baseline_dir: Path = DEFAULT_BASELINE_DIR,
) -> dict[str, dict[str, float]] | None:
    path = _baseline_path(baseline_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def compare(
    db: TelemetryDB,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    baseline_dir: Path = DEFAULT_BASELINE_DIR,
) -> CompareResult:
    """Compare current rolling averages against the stored baseline."""
    baseline = load_baseline(baseline_dir)
    if baseline is None:
        log.warning("No baseline found — run 'tef-estimator telemetry baseline' first")
        return CompareResult(signals=[], metrics_checked=0, threshold=threshold)

    conn = db.connect()
    cursor = conn.cursor()

    cursor.execute(
        """SELECT source_id, metric_name, value
           FROM time_series
           WHERE metric_name LIKE '%_7d_avg'
             AND series_date = (
                 SELECT MAX(series_date) FROM time_series
                 WHERE metric_name LIKE '%_7d_avg'
             )"""
    )
    current: dict[str, dict[str, float]] = {}
    for source_id, metric_name, value in cursor.fetchall():
        current.setdefault(source_id, {})[metric_name] = value

    conn.close()

    signals: list[Signal] = []
    metrics_checked = 0

    for source_id, baseline_metrics in baseline.items():
        current_metrics = current.get(source_id, {})
        for metric_name, base_val in baseline_metrics.items():
            cur_val = current_metrics.get(metric_name)
            if cur_val is None:
                continue

            metrics_checked += 1

            if abs(base_val) < 1e-9:
                if abs(cur_val) > 1e-9:
                    pct = 1.0
                else:
                    continue
            else:
                pct = (cur_val - base_val) / abs(base_val)

            if abs(pct) >= threshold:
                signals.append(Signal(
                    source_id=source_id,
                    metric_name=metric_name,
                    baseline_value=base_val,
                    current_value=cur_val,
                    pct_change=pct,
                    direction="up" if pct > 0 else "down",
                ))

    if signals:
        log.warning("%d signal(s) detected (threshold=%.0f%%)", len(signals), threshold * 100)
        for s in signals:
            log.warning(
                "  %s/%s: %.2f → %.2f (%+.1f%%)",
                s.source_id, s.metric_name,
                s.baseline_value, s.current_value, s.pct_change * 100,
            )
    else:
        log.info("No signals detected (%d metrics checked)", metrics_checked)

    return CompareResult(
        signals=signals,
        metrics_checked=metrics_checked,
        threshold=threshold,
    )
