"""Tests for three-anchor base rate triangulation."""

from tef_estimator.data.common import PERTRange
from tef_estimator.triangulation import triangulate, extract_anchors


class TestTriangulate:
    def test_suggested_low_is_min_of_anchor_lows(self):
        anchors = {
            "a": PERTRange(0.003, 0.005, 0.007),
            "b": PERTRange(0.005, 0.015, 0.08),
            "c": PERTRange(0.006, 0.012, 0.015),
        }
        result = triangulate(anchors)
        assert result.suggested.low == 0.003

    def test_suggested_mode_is_mean_of_anchor_modes(self):
        anchors = {
            "a": PERTRange(0.003, 0.005, 0.007),
            "b": PERTRange(0.005, 0.015, 0.08),
            "c": PERTRange(0.006, 0.012, 0.015),
        }
        result = triangulate(anchors)
        expected = round((0.005 + 0.015 + 0.012) / 3, 4)
        assert result.suggested.mode == expected

    def test_suggested_high_capped_at_max_anchor_high(self):
        anchors = {
            "a": PERTRange(0.01, 0.02, 0.03),
            "b": PERTRange(0.01, 0.02, 0.03),
            "c": PERTRange(0.01, 0.02, 0.03),
        }
        result = triangulate(anchors)
        assert result.suggested.high <= 0.03

    def test_convergent_anchors(self):
        anchors = {
            "a": PERTRange(0.003, 0.005, 0.007),
            "b": PERTRange(0.005, 0.015, 0.08),
            "c": PERTRange(0.006, 0.012, 0.015),
        }
        result = triangulate(anchors)
        assert result.is_convergent is True
        assert result.convergence_ratio == 3.0

    def test_divergent_anchors(self):
        anchors = {
            "a": PERTRange(0.001, 0.001, 0.002),
            "b": PERTRange(0.05, 0.10, 0.20),
            "c": PERTRange(0.001, 0.015, 0.03),
        }
        result = triangulate(anchors)
        assert result.is_convergent is False
        assert result.convergence_ratio > 10.0

    def test_validation_messages_include_anchors(self):
        anchors = {
            "tempo": PERTRange(0.003, 0.005, 0.007),
            "iris": PERTRange(0.005, 0.015, 0.08),
        }
        result = triangulate(anchors)
        anchor_lines = [v for v in result.validation if "tempo" in v]
        assert len(anchor_lines) == 1

    def test_actual_consensus_deviation_check(self):
        anchors = {
            "a": PERTRange(0.003, 0.005, 0.007),
            "b": PERTRange(0.005, 0.015, 0.08),
            "c": PERTRange(0.006, 0.012, 0.015),
        }
        consensus = PERTRange(0.003, 0.010, 0.025)
        result = triangulate(anchors, actual_consensus=consensus)
        deviation_lines = [v for v in result.validation if "Consensus within" in v]
        assert len(deviation_lines) == 1

    def test_large_deviation_produces_warning(self):
        anchors = {
            "a": PERTRange(0.01, 0.02, 0.03),
            "b": PERTRange(0.01, 0.02, 0.03),
        }
        bad_consensus = PERTRange(0.001, 0.001, 0.003)
        result = triangulate(anchors, actual_consensus=bad_consensus)
        warning_lines = [v for v in result.validation if "WARNING" in v]
        assert len(warning_lines) == 1

    def test_ordering_low_lt_mode_lt_high(self):
        anchors = {
            "a": PERTRange(0.10, 0.15, 0.20),
            "b": PERTRange(0.05, 0.08, 0.12),
        }
        result = triangulate(anchors)
        assert result.suggested.low < result.suggested.mode < result.suggested.high


class TestExtractAnchors:
    def test_separates_consensus_from_anchors(self):
        tri = {
            "operational_tempo": PERTRange(0.003, 0.005, 0.007),
            "iris_back_calculation": PERTRange(0.005, 0.015, 0.08),
            "consensus": PERTRange(0.003, 0.010, 0.025),
        }
        anchors, consensus = extract_anchors(tri)
        assert "consensus" not in anchors
        assert len(anchors) == 2
        assert consensus == PERTRange(0.003, 0.010, 0.025)

    def test_no_consensus_key(self):
        tri = {
            "a": PERTRange(0.01, 0.02, 0.03),
            "b": PERTRange(0.02, 0.03, 0.04),
        }
        anchors, consensus = extract_anchors(tri)
        assert consensus is None
        assert len(anchors) == 2


class TestRansomwareTriangulation:
    def test_ransomware_consensus_within_tolerance(self):
        from tef_estimator.data.scenarios.ransomware import RansomwareScenario
        scenario = RansomwareScenario()
        anchors, consensus = extract_anchors(scenario.base_rate_triangulation)
        result = triangulate(anchors, consensus)
        assert result.is_convergent
        mode_delta = abs(consensus.mode - result.suggested.mode) / result.suggested.mode
        assert mode_delta < 0.50


class TestBECTriangulation:
    def test_bec_consensus_within_tolerance(self):
        from tef_estimator.data.scenarios.bec import BECScenario
        scenario = BECScenario()
        anchors, consensus = extract_anchors(scenario.base_rate_triangulation)
        result = triangulate(anchors, consensus)
        assert result.is_convergent
        mode_delta = abs(consensus.mode - result.suggested.mode) / result.suggested.mode
        assert mode_delta < 0.50
