"""Tests for data refresh and staleness validation."""

from __future__ import annotations

from datetime import date, timedelta

from tef_estimator.refresh.fetchers import run_snapshot_refresh
from tef_estimator.refresh.validators import check_freshness, STALENESS_WARNING_DAYS, STALENESS_STALE_DAYS


def test_run_snapshot_refresh_prints_instructions(capsys):
    """Refresh function prints update instructions."""
    run_snapshot_refresh()
    captured = capsys.readouterr()
    assert "Reference data" in captured.out
    assert "extracted.json" in captured.out


def test_check_freshness_returns_list():
    """check_freshness returns a list of strings."""
    result = check_freshness()
    assert isinstance(result, list)
    assert all(isinstance(w, str) for w in result)


def test_check_freshness_no_warnings_when_fresh():
    """No warnings when data is current (today's date)."""
    result = check_freshness(today=date(2026, 5, 24))
    staleness_msgs = [w for w in result if "days old" in w]
    assert len(staleness_msgs) == 0


def test_check_freshness_warns_at_threshold():
    """Warnings appear when data exceeds the staleness threshold."""
    future = date(2026, 5, 24) + timedelta(days=STALENESS_WARNING_DAYS + 1)
    result = check_freshness(today=future)
    staleness_msgs = [w for w in result if "days old" in w]
    assert len(staleness_msgs) > 0


def test_check_freshness_stale_includes_refresh_suggestion():
    """Stale data (>180d) suggests refreshing."""
    future = date(2026, 5, 24) + timedelta(days=STALENESS_STALE_DAYS + 1)
    result = check_freshness(today=future)
    refresh_msgs = [w for w in result if "Consider refreshing" in w]
    assert len(refresh_msgs) > 0
