"""Tests for Dimension 4: Adversarial edge cases."""

import pytest

from llm_classification_validator.adversarial.scorer import (
    combined_score,
    pass_rate,
    score_ambiguity,
    score_discrimination,
)
from llm_classification_validator.adversarial.pairs import (
    AmbiguityCase,
    MinimalPair,
    run_adversarial_analysis,
)
from llm_classification_validator.config import AdversarialConfig
from llm_classification_validator.models import CaseResult


class TestScoreDiscrimination:
    def test_correctly_discriminated(self):
        result = score_discrimination("A", "B", "A", "B")
        assert result.passed is True

    def test_failed_to_discriminate(self):
        result = score_discrimination("A", "A")
        assert result.passed is False
        assert "failed to discriminate" in result.details

    def test_wrong_labels_despite_discrimination(self):
        result = score_discrimination("A", "B", "B", "A")
        assert result.passed is False  # Discriminated but wrong assignment

    def test_no_expected_values(self):
        result = score_discrimination("X", "Y")
        assert result.passed is True  # Just needs to discriminate


class TestScoreAmbiguity:
    def test_acceptable_label(self):
        result = score_ambiguity("A", ["A", "B"])
        assert result.passed is True

    def test_unacceptable_label(self):
        result = score_ambiguity("C", ["A", "B"])
        assert result.passed is False

    def test_empty_acceptable_set(self):
        # No constraints means anything is acceptable
        result = score_ambiguity("anything", [])
        assert result.passed is True


class TestPassRate:
    def test_all_pass(self):
        results = [
            CaseResult("t", "1", True),
            CaseResult("t", "2", True),
        ]
        assert pass_rate(results) == pytest.approx(1.0)

    def test_none_pass(self):
        results = [
            CaseResult("t", "1", False),
            CaseResult("t", "2", False),
        ]
        assert pass_rate(results) == pytest.approx(0.0)

    def test_mixed(self):
        results = [
            CaseResult("t", "1", True),
            CaseResult("t", "2", False),
        ]
        assert pass_rate(results) == pytest.approx(0.5)

    def test_empty(self):
        assert pass_rate([]) == pytest.approx(0.0)


class TestCombinedScore:
    def test_weighted_average(self):
        disc = [CaseResult("d", "1", True)]
        amb = [CaseResult("a", "1", False)]
        score = combined_score(disc, amb, 0.6, 0.4)
        expected = (1.0 * 0.6 + 0.0 * 0.4) / (0.6 + 0.4)
        assert score == pytest.approx(expected)

    def test_only_discrimination(self):
        disc = [CaseResult("d", "1", True)]
        score = combined_score(disc, [], 0.6, 0.4)
        assert score == pytest.approx(1.0)

    def test_only_ambiguity(self):
        amb = [CaseResult("a", "1", True)]
        score = combined_score([], amb, 0.6, 0.4)
        assert score == pytest.approx(1.0)

    def test_both_empty(self):
        assert combined_score([], [], 0.6, 0.4) == pytest.approx(0.0)


class TestAdversarialAnalysis:
    def test_perfect_classifier(self):
        def classifier(text: str) -> str:
            return "A" if "alpha" in text else "B"

        pairs = [
            MinimalPair("p1", "alpha item", "beta item", "A", "B"),
        ]
        ambiguity = [
            AmbiguityCase("a1", "alpha-beta", ["A", "B"]),
        ]
        report = run_adversarial_analysis(
            classifier, minimal_pairs=pairs, ambiguity_cases=ambiguity,
        )
        disc_metric = next(
            m for m in report.metrics if m.metric_name == "discrimination_score"
        )
        assert disc_metric.value == pytest.approx(1.0)

    def test_failing_classifier(self):
        def classifier(text: str) -> str:
            return "always_same"

        pairs = [
            MinimalPair("p1", "input A", "input B", "X", "Y"),
        ]
        report = run_adversarial_analysis(classifier, minimal_pairs=pairs)
        assert report.verdict.value == "FAIL"

    def test_custom_thresholds(self):
        def classifier(text: str) -> str:
            return "A"

        pairs = [MinimalPair("p1", "a", "b")]
        config = AdversarialConfig(
            discrimination_target=0.10,
            discrimination_minimum=0.05,
            combined_target=0.10,
            combined_minimum=0.05,
        )
        report = run_adversarial_analysis(
            classifier, minimal_pairs=pairs, config=config,
        )
        # Single pair, same label -> 0% discrimination, below 5% minimum
        assert report.verdict.value == "FAIL"

    def test_no_cases_returns_skipped(self):
        report = run_adversarial_analysis(lambda t: "A")
        assert report.verdict.value == "SKIPPED"

    def test_only_pairs_no_combined_check(self):
        def classifier(text: str) -> str:
            return "A" if "alpha" in text else "B"

        pairs = [MinimalPair("p1", "alpha item", "beta item", "A", "B")]
        report = run_adversarial_analysis(classifier, minimal_pairs=pairs)
        assert report.verdict.value == "PASS"
