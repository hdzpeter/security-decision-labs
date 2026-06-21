"""Tests for tef_estimator.telemetry.compare."""

import json
import pytest
from pathlib import Path

from tef_estimator.telemetry.db import TelemetryDB
from tef_estimator.telemetry.compare import (
    compare,
    load_baseline,
    snapshot_baseline,
    Signal,
    CompareResult,
)


@pytest.fixture
def db_with_timeseries():
    """DB with time_series data suitable for baseline/compare."""
    db = TelemetryDB(db_path=None)
    db.initialize()

    conn = db.connect()
    cursor = conn.cursor()

    for metric, value in [
        ("unique_sources_port_3389_7d_avg", 100.0),
        ("unique_sources_port_445_7d_avg", 50.0),
    ]:
        cursor.execute(
            """INSERT INTO time_series
               (source_id, series_date, event_type, metric_name, value, interpolation_flag)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("dshield", "2026-06-13", "scan_activity", metric, value, 0),
        )

    conn.commit()
    conn.close()
    return db


class TestCompare:
    def test_snapshot_baseline(self, db_with_timeseries, tmp_path):
        bl = snapshot_baseline(db_with_timeseries, baseline_dir=tmp_path)
        assert "dshield" in bl
        assert "unique_sources_port_3389_7d_avg" in bl["dshield"]
        assert (tmp_path / "telemetry_baseline.json").exists()

    def test_load_baseline(self, db_with_timeseries, tmp_path):
        snapshot_baseline(db_with_timeseries, baseline_dir=tmp_path)
        bl = load_baseline(tmp_path)
        assert bl is not None
        assert bl["dshield"]["unique_sources_port_3389_7d_avg"] == 100.0

    def test_load_baseline_missing(self, tmp_path):
        bl = load_baseline(tmp_path)
        assert bl is None

    def test_compare_no_signals(self, db_with_timeseries, tmp_path):
        snapshot_baseline(db_with_timeseries, baseline_dir=tmp_path)
        result = compare(db_with_timeseries, baseline_dir=tmp_path)

        assert not result.has_signals
        assert result.metrics_checked == 2

    def test_compare_with_signal(self, db_with_timeseries, tmp_path):
        snapshot_baseline(db_with_timeseries, baseline_dir=tmp_path)

        # Now change a value in time_series
        conn = db_with_timeseries.connect()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE time_series SET value = 150.0
               WHERE metric_name = 'unique_sources_port_3389_7d_avg'"""
        )
        conn.commit()
        conn.close()

        result = compare(db_with_timeseries, threshold=0.20, baseline_dir=tmp_path)
        assert result.has_signals
        assert len(result.signals) == 1

        sig = result.signals[0]
        assert sig.source_id == "dshield"
        assert sig.baseline_value == 100.0
        assert sig.current_value == 150.0
        assert sig.direction == "up"
        assert abs(sig.pct_change - 0.50) < 0.01

    def test_compare_below_threshold(self, db_with_timeseries, tmp_path):
        snapshot_baseline(db_with_timeseries, baseline_dir=tmp_path)

        conn = db_with_timeseries.connect()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE time_series SET value = 110.0
               WHERE metric_name = 'unique_sources_port_3389_7d_avg'"""
        )
        conn.commit()
        conn.close()

        result = compare(db_with_timeseries, threshold=0.20, baseline_dir=tmp_path)
        assert not result.has_signals

    def test_signal_dataclass(self):
        s = Signal(
            source_id="test",
            metric_name="m",
            baseline_value=100.0,
            current_value=80.0,
            pct_change=-0.20,
            direction="down",
        )
        assert s.direction == "down"
        assert s.pct_change == -0.20
