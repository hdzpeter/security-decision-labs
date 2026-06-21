"""Tests for tef_estimator.telemetry.db."""

import sqlite3

import pytest

from tef_estimator.telemetry.db import TelemetryDB, KNOWN_SOURCES


@pytest.fixture
def db():
    """In-memory telemetry database for testing."""
    tdb = TelemetryDB(db_path=None)
    tdb.initialize()
    return tdb


class TestTelemetryDB:
    def test_initialize_creates_tables(self, db):
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "raw_observations" in tables
        assert "time_series" in tables
        assert "computed_statistics" in tables
        assert "source_health" in tables

    def test_initialize_populates_source_health(self, db):
        conn = db.connect()
        health = db.get_source_health(conn)
        conn.close()

        source_ids = {h.source_id for h in health}
        for sid, _ in KNOWN_SOURCES:
            assert sid in source_ids

    def test_insert_observation(self, db):
        conn = db.connect()
        cursor = conn.cursor()
        ts = db.collection_timestamp()

        inserted = db.insert_observation(
            cursor, "dshield", "scan_activity",
            "2026-06-13", "unique_sources_port_3389", 42.0,
            "count", ts, "abc123",
        )
        conn.commit()

        assert inserted is True

        cursor.execute("SELECT metric_value FROM raw_observations WHERE metric_name = ?",
                       ("unique_sources_port_3389",))
        row = cursor.fetchone()
        conn.close()
        assert row[0] == 42.0

    def test_insert_observation_dedup(self, db):
        conn = db.connect()
        cursor = conn.cursor()
        ts = db.collection_timestamp()

        db.insert_observation(cursor, "dshield", "scan", "2026-06-13",
                              "metric_a", 10.0, "count", ts, "h1")
        first = db.insert_observation(cursor, "dshield", "scan", "2026-06-13",
                                       "metric_a", 20.0, "count", ts, "h2")
        conn.commit()
        conn.close()

        assert first is False

    def test_update_source_health_success(self, db):
        conn = db.connect()
        db.update_source_health(conn, "dshield", True, "All good")

        health = db.get_source_health(conn)
        dshield = next(h for h in health if h.source_id == "dshield")
        conn.close()

        assert dshield.last_success is not None
        assert dshield.consecutive_failures == 0
        assert dshield.staleness_flag is False

    def test_update_source_health_failure_increments(self, db):
        conn = db.connect()
        db.update_source_health(conn, "dshield", False, "Timeout")
        db.update_source_health(conn, "dshield", False, "Timeout again")

        health = db.get_source_health(conn)
        dshield = next(h for h in health if h.source_id == "dshield")
        conn.close()

        assert dshield.consecutive_failures == 2

    def test_get_existing_metric_names(self, db):
        conn = db.connect()
        cursor = conn.cursor()
        ts = db.collection_timestamp()

        db.insert_observation(cursor, "test", "ev", "2026-01-01",
                              "metric_a", 1.0, "count", ts, "h")
        db.insert_observation(cursor, "test", "ev", "2026-01-02",
                              "metric_b", 2.0, "count", ts, "h")
        conn.commit()

        names = db.get_existing_metric_names(cursor, "test")
        conn.close()

        assert names == {"metric_a", "metric_b"}

    def test_compute_hash(self):
        h = TelemetryDB.compute_hash("hello")
        assert len(h) == 64
        assert h == TelemetryDB.compute_hash("hello")
        assert h != TelemetryDB.compute_hash("world")

    def test_in_memory_connect_no_file_check(self, db):
        conn = db.connect()
        assert conn is not None
        conn.close()
