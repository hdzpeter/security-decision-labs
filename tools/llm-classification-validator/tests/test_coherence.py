"""Tests for Dimension 1: Coherence (kappa, bootstrap, analysis)."""

import pytest

from llm_classification_validator.coherence.kappa import (
    build_ratings_matrix,
    cohens_kappa,
    fleiss_kappa,
)
from llm_classification_validator.coherence.bootstrap import bootstrap_ci
from llm_classification_validator.coherence.analysis import run_coherence_analysis
from llm_classification_validator.config import CoherenceConfig, BootstrapConfig, ThresholdConfig


# -- Cohen's kappa --


class TestCohensKappa:
    def test_perfect_agreement(self):
        a = ["cat", "dog", "cat", "dog"]
        b = ["cat", "dog", "cat", "dog"]
        assert cohens_kappa(a, b) == pytest.approx(1.0)

    def test_no_agreement(self):
        # Complete disagreement with non-overlapping categories:
        # Po=0, Pe=(0.5*0.5 + 0.5*0.5)=0.5, kappa=(0-0.5)/(1-0.5)=-1.0
        a = ["cat", "cat", "dog", "dog"]
        b = ["dog", "dog", "cat", "cat"]
        kappa = cohens_kappa(a, b)
        assert kappa < 0.0  # Worse than chance

    def test_moderate_agreement(self):
        a = ["A", "B", "A", "B", "A", "B", "A", "B", "A", "B"]
        b = ["A", "B", "A", "B", "B", "B", "A", "A", "A", "B"]
        kappa = cohens_kappa(a, b)
        assert 0.0 < kappa < 1.0

    def test_empty_sequences(self):
        assert cohens_kappa([], []) == 0.0

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="Length mismatch"):
            cohens_kappa(["a"], ["a", "b"])

    def test_single_category_both_raters(self):
        # When both raters assign same category to all items, Pe=1
        # and the function should return 1.0 (perfect agreement)
        a = ["X", "X", "X"]
        b = ["X", "X", "X"]
        assert cohens_kappa(a, b) == pytest.approx(1.0)

    def test_known_value(self):
        # Hand-computed example
        # 20 items, 2 categories (A, B)
        # Rater 1: 10A, 10B; Rater 2: 10A, 10B; 15 agree
        a = ["A"] * 8 + ["B"] * 2 + ["A"] * 2 + ["B"] * 8
        b = ["A"] * 10 + ["B"] * 10
        po = 16 / 20  # 8 + 8 = 16 agreements
        # Pa = 10/20 * 10/20 = 0.25, Pb = 10/20 * 10/20 = 0.25
        pe = 0.5  # (10/20)*(10/20) + (10/20)*(10/20)
        expected = (po - pe) / (1 - pe)
        assert cohens_kappa(a, b) == pytest.approx(expected, abs=0.001)


# -- Fleiss' kappa --


class TestFleissKappa:
    def test_perfect_agreement(self):
        # 3 raters, 4 items, 2 categories, all agree
        matrix = [
            [3, 0],  # all say cat. 0
            [0, 3],  # all say cat. 1
            [3, 0],
            [0, 3],
        ]
        assert fleiss_kappa(matrix) == pytest.approx(1.0)

    def test_random_agreement(self):
        # 2 raters perfectly split on every item -> maximum disagreement
        # Fleiss' kappa = -1/(n_raters - 1) = -1 for 2 raters
        matrix = [
            [1, 1],
            [1, 1],
            [1, 1],
            [1, 1],
        ]
        assert fleiss_kappa(matrix) == pytest.approx(-1.0)

    def test_empty_matrix(self):
        assert fleiss_kappa([]) == 0.0

    def test_single_rater(self):
        matrix = [[1, 0], [0, 1]]
        assert fleiss_kappa(matrix) == 0.0  # n_raters=1, returns 0


class TestBuildRatingsMatrix:
    def test_basic(self):
        raters = [
            ["A", "B", "A"],
            ["A", "B", "B"],
            ["A", "A", "B"],
        ]
        matrix, cats = build_ratings_matrix(raters)
        assert cats == ["A", "B"]
        assert len(matrix) == 3
        # Item 0: all say A -> [3, 0]
        assert matrix[0] == [3, 0]
        # Item 1: 2 say B, 1 says A -> [1, 2]
        assert matrix[1] == [1, 2]
        # Item 2: 1 says A, 2 say B -> [1, 2]
        assert matrix[2] == [1, 2]

    def test_empty(self):
        matrix, cats = build_ratings_matrix([])
        assert matrix == []
        assert cats == []

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            build_ratings_matrix([["A", "B"], ["A"]])


# -- Bootstrap CI --


class TestBootstrapCI:
    def test_point_estimate(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        point, lower, upper = bootstrap_ci(data, seed=42)
        assert point == pytest.approx(3.0)

    def test_ci_bounds_order(self):
        data = [0.5, 0.6, 0.7, 0.8, 0.9, 0.4, 0.3]
        point, lower, upper = bootstrap_ci(data, seed=42)
        assert lower <= point <= upper

    def test_narrow_ci_for_constant(self):
        data = [0.5] * 100
        point, lower, upper = bootstrap_ci(data, seed=42)
        assert point == pytest.approx(0.5)
        assert lower == pytest.approx(0.5)
        assert upper == pytest.approx(0.5)

    def test_empty_data(self):
        point, lower, upper = bootstrap_ci([])
        assert point == 0.0
        assert lower == 0.0
        assert upper == 0.0

    def test_custom_statistic(self):
        data = [1.0, 2.0, 3.0]
        point, lower, upper = bootstrap_ci(data, statistic=max, seed=42)
        assert point == 3.0

    def test_deterministic_with_seed(self):
        data = [0.1, 0.5, 0.9]
        r1 = bootstrap_ci(data, seed=123)
        r2 = bootstrap_ci(data, seed=123)
        assert r1 == r2


# -- Coherence analysis --


class TestCoherenceAnalysis:
    def test_two_perfect_raters(self):
        raters = {
            "model_a": ["X", "Y", "X", "Y"],
            "model_b": ["X", "Y", "X", "Y"],
        }
        report = run_coherence_analysis(raters)
        assert report.verdict.value == "PASS"
        # Mean kappa should be 1.0
        mean_kappa = next(
            m for m in report.metrics if m.metric_name == "mean_kappa"
        )
        assert mean_kappa.value == pytest.approx(1.0)

    def test_three_raters(self):
        raters = {
            "r1": ["A", "B", "A", "B", "A"],
            "r2": ["A", "B", "A", "A", "A"],
            "r3": ["A", "B", "B", "B", "A"],
        }
        report = run_coherence_analysis(raters)
        # Should have pairwise kappas and Fleiss
        metric_names = {m.metric_name for m in report.metrics}
        assert "fleiss_kappa" in metric_names
        assert "mean_kappa" in metric_names

    def test_insufficient_raters(self):
        raters = {"only_one": ["A", "B"]}
        report = run_coherence_analysis(raters)
        assert report.verdict.value == "FAIL"

    def test_custom_thresholds(self):
        raters = {
            "r1": ["A", "B", "A", "B"],
            "r2": ["A", "B", "B", "B"],
        }
        # Very high threshold to force FAIL
        config = CoherenceConfig(
            thresholds=[ThresholdConfig(metric="mean_kappa", target=0.99, minimum=0.95)],
            bootstrap=BootstrapConfig(iterations=100),
        )
        report = run_coherence_analysis(raters, config=config)
        assert report.verdict.value in ("FAIL", "MARGINAL")

    def test_no_thresholds_returns_skipped(self):
        raters = {"r1": ["A", "B"], "r2": ["A", "B"]}
        config = CoherenceConfig(thresholds=[])
        report = run_coherence_analysis(raters, config=config)
        assert report.verdict.value == "SKIPPED"
