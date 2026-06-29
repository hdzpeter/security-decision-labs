"""Tests for Dimension 3: Convergent validity (Jaccard, kappa, analysis)."""

import pytest

from llm_classification_validator.convergent.jaccard import (
    jaccard_distance,
    jaccard_similarity,
    mean_jaccard,
)
from llm_classification_validator.convergent.analysis import run_convergent_analysis
from llm_classification_validator.config import ConvergentConfig, ThresholdConfig, BootstrapConfig


class TestJaccardSimilarity:
    def test_identical_sets(self):
        assert jaccard_similarity({"a", "b", "c"}, {"a", "b", "c"}) == pytest.approx(1.0)

    def test_disjoint_sets(self):
        assert jaccard_similarity({"a", "b"}, {"c", "d"}) == pytest.approx(0.0)

    def test_partial_overlap(self):
        # {a, b, c} & {b, c, d} = {b, c}, union = {a, b, c, d}
        assert jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"}) == pytest.approx(0.5)

    def test_both_empty(self):
        assert jaccard_similarity(set(), set()) == pytest.approx(1.0)

    def test_one_empty(self):
        assert jaccard_similarity({"a"}, set()) == pytest.approx(0.0)

    def test_accepts_lists(self):
        assert jaccard_similarity(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)

    def test_duplicates_in_input(self):
        # Duplicates are collapsed to set
        assert jaccard_similarity(["a", "a", "b"], ["a", "b"]) == pytest.approx(1.0)


class TestJaccardDistance:
    def test_identical(self):
        assert jaccard_distance({"a"}, {"a"}) == pytest.approx(0.0)

    def test_disjoint(self):
        assert jaccard_distance({"a"}, {"b"}) == pytest.approx(1.0)


class TestMeanJaccard:
    def test_basic(self):
        pairs = [
            ({"a", "b"}, {"a", "b"}),  # 1.0
            ({"a"}, {"b"}),             # 0.0
        ]
        assert mean_jaccard(pairs) == pytest.approx(0.5)

    def test_empty(self):
        assert mean_jaccard([]) == pytest.approx(0.0)


class TestConvergentAnalysis:
    def test_perfect_categorical(self):
        predicted = ["A", "B", "A", "B"]
        reference = ["A", "B", "A", "B"]
        report = run_convergent_analysis(predicted, reference)
        kappa = next(m for m in report.metrics if m.metric_name == "kappa")
        assert kappa.value == pytest.approx(1.0)

    def test_set_based(self):
        pred_sets = [{"a", "b"}, {"c", "d"}]
        ref_sets = [{"a", "b"}, {"c", "d"}]
        report = run_convergent_analysis(
            predicted_labels=[], reference_labels=[],
            predicted_sets=pred_sets, reference_sets=ref_sets,
        )
        jac = next(m for m in report.metrics if m.metric_name == "jaccard")
        assert jac.value == pytest.approx(1.0)

    def test_length_mismatch(self):
        report = run_convergent_analysis(["A"], ["A", "B"])
        assert report.verdict.value == "FAIL"

    def test_custom_thresholds(self):
        predicted = ["A", "B", "A", "B"]
        reference = ["A", "B", "B", "A"]
        config = ConvergentConfig(
            thresholds=[ThresholdConfig(metric="kappa", target=0.99, minimum=0.80)],
            bootstrap=BootstrapConfig(iterations=100),
        )
        report = run_convergent_analysis(predicted, reference, config=config)
        assert report.verdict.value in ("FAIL", "MARGINAL")

    def test_no_thresholds_returns_skipped(self):
        config = ConvergentConfig(thresholds=[])
        report = run_convergent_analysis(["A"], ["A"], config=config)
        assert report.verdict.value == "SKIPPED"
