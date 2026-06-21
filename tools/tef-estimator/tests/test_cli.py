"""Tests for CLI commands -- verifies they run without error."""

import json

import pytest
from typer.testing import CliRunner

from tef_estimator.cli import app

runner = CliRunner()


class TestEstimate:
    def test_default_output(self):
        result = runner.invoke(app, [
            "estimate",
            "--sector", "manufacturing",
            "--revenue", "100m_1b",
            "--geo", "us",
            "--remote-access", "fortinet",
            "--employees", "2000",
        ])
        assert result.exit_code == 0, result.output
        assert "VECTOR BREAKDOWN" in result.output

    def test_brief(self):
        result = runner.invoke(app, [
            "estimate",
            "--sector", "education",
            "--revenue", "10m_100m",
            "--geo", "western_europe",
            "--brief",
        ])
        assert result.exit_code == 0, result.output
        assert "TEF ESTIMATE" in result.output

    def test_full(self):
        result = runner.invoke(app, [
            "estimate",
            "--sector", "manufacturing",
            "--revenue", "100m_1b",
            "--geo", "us",
            "--full",
        ])
        assert result.exit_code == 0, result.output
        assert "THREAT EVENT FREQUENCY ESTIMATE" in result.output

    def test_json_output(self):
        result = runner.invoke(app, [
            "estimate",
            "--sector", "financial",
            "--revenue", "1b_10b",
            "--geo", "us",
            "--json",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "summary" in data
        assert "analysis" in data
        assert "audit" in data

    def test_custom_base_rate(self):
        result = runner.invoke(app, [
            "estimate",
            "--sector", "manufacturing",
            "--revenue", "100m_1b",
            "--geo", "us",
            "--base-rate", "0.05",
            "--brief",
        ])
        assert result.exit_code == 0, result.output


class TestExplain:
    def test_explain_runs(self):
        result = runner.invoke(app, [
            "explain",
            "--sector", "manufacturing",
            "--revenue", "100m_1b",
            "--geo", "us",
        ])
        assert result.exit_code == 0, result.output
        assert "THREAT EVENT FREQUENCY ESTIMATE" in result.output


class TestCompare:
    def test_compare_runs(self):
        result = runner.invoke(app, [
            "compare",
            "--sector", "manufacturing",
            "--revenue", "100m_1b",
            "--geo", "us",
            "--b-sector", "financial",
        ])
        assert result.exit_code == 0, result.output
        assert "PROFILE COMPARISON" in result.output

    def test_compare_json(self):
        result = runner.invoke(app, [
            "compare",
            "--sector", "manufacturing",
            "--revenue", "100m_1b",
            "--geo", "us",
            "--b-sector", "financial",
            "--json",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "vector_deltas" in data


class TestSensitivity:
    def test_sensitivity_runs(self):
        result = runner.invoke(app, [
            "sensitivity",
            "--sector", "manufacturing",
            "--revenue", "100m_1b",
            "--geo", "us",
        ])
        assert result.exit_code == 0, result.output
        assert "SENSITIVITY ANALYSIS" in result.output

    def test_sensitivity_json(self):
        result = runner.invoke(app, [
            "sensitivity",
            "--sector", "manufacturing",
            "--revenue", "100m_1b",
            "--geo", "us",
            "--json",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert len(data) >= 3


class TestDataCommands:
    def test_show_multipliers(self):
        result = runner.invoke(app, ["data", "multipliers"])
        assert result.exit_code == 0, result.output

    def test_show_base_rate(self):
        result = runner.invoke(app, ["data", "base-rate"])
        assert result.exit_code == 0, result.output

    def test_show_vectors(self):
        result = runner.invoke(app, ["data", "vectors"])
        assert result.exit_code == 0, result.output
