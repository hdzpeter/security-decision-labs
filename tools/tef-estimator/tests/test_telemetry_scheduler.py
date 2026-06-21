"""Tests for tef_estimator.telemetry.scheduler."""

import json
import pytest
from datetime import datetime, timedelta, timezone

from tef_estimator.telemetry.scheduler import (
    is_due,
    load_state,
    save_state,
)


class TestIsDue:
    def test_never_run_is_due(self):
        due, reason = is_due("dshield", 1, {})
        assert due is True
        assert "never" in reason

    def test_force_is_due(self):
        state = {"dshield": {"last_success": datetime.now(timezone.utc).isoformat()}}
        due, reason = is_due("dshield", 1, state, force=True)
        assert due is True
        assert reason == "forced"

    def test_recent_not_due(self):
        now = datetime.now(timezone.utc).isoformat()
        state = {"dshield": {"last_success": now}}
        due, reason = is_due("dshield", 1, state)
        assert due is False

    def test_old_is_due(self):
        old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        state = {"dshield": {"last_success": old}}
        due, reason = is_due("dshield", 1, state)
        assert due is True

    def test_invalid_timestamp(self):
        state = {"dshield": {"last_success": "not-a-date"}}
        due, reason = is_due("dshield", 1, state)
        assert due is True
        assert "invalid" in reason


class TestStateIO:
    def test_save_and_load(self, tmp_path):
        state = {"dshield": {"last_success": "2026-06-13T12:00:00"}}
        save_state(state, tmp_path)

        loaded = load_state(tmp_path)
        assert loaded == state

    def test_load_missing(self, tmp_path):
        loaded = load_state(tmp_path)
        assert loaded == {}
