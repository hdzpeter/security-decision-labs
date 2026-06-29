"""Tests for Dimension 5: Stability and sensitivity."""

import pytest

from llm_classification_validator.stability.paraphrase import ParaphraseVariant
from llm_classification_validator.stability.perturbation import ExpectedDirection, PerturbationVariant
from llm_classification_validator.stability.analysis import run_stability_analysis
from llm_classification_validator.config import StabilityConfig, ThresholdConfig, BootstrapConfig


class TestStabilityAnalysis:
    def _make_config(self) -> StabilityConfig:
        return StabilityConfig(
            thresholds=[
                ThresholdConfig(metric="stability", target=0.80, minimum=0.60),
            ],
            bootstrap=BootstrapConfig(iterations=100, seed=42),
        )

    def test_perfect_stability(self):
        """Paraphrases produce identical labels -> stability = 1.0."""
        base_items = {"item1": "do something", "item2": "do other"}

        def classifier(text: str) -> dict[str, str]:
            return {"category": "A"}

        paraphrases = [
            ParaphraseVariant("item1", "item1_p1", "formal", "do the thing"),
            ParaphraseVariant("item2", "item2_p1", "informal", "do another"),
        ]
        config = self._make_config()
        report = run_stability_analysis(
            base_items, classifier, paraphrases=paraphrases, config=config,
        )
        stab = next(m for m in report.metrics if m.metric_name == "stability")
        assert stab.value == pytest.approx(1.0)
        assert report.verdict.value == "PASS"

    def test_zero_stability(self):
        """Paraphrases always produce different labels -> stability = 0."""
        base_items = {"item1": "foo"}
        call_count = [0]

        def classifier(text: str) -> dict[str, str]:
            call_count[0] += 1
            # Alternate between labels
            return {"category": "A" if call_count[0] % 2 == 1 else "B"}

        paraphrases = [
            ParaphraseVariant("item1", "item1_p1", "formal", "bar"),
        ]
        config = self._make_config()
        report = run_stability_analysis(
            base_items, classifier, paraphrases=paraphrases, config=config,
        )
        stab = next(m for m in report.metrics if m.metric_name == "stability")
        assert stab.value == pytest.approx(0.0)
        assert report.verdict.value == "FAIL"

    def test_multi_dimension_stability(self):
        """Track stability across multiple label dimensions."""
        base_items = {"item1": "test"}

        def classifier(text: str) -> dict[str, str]:
            return {"cat": "A", "subcat": "X"}

        paraphrases = [
            ParaphraseVariant("item1", "item1_p1", "formal", "test rephrased"),
        ]
        config = self._make_config()
        report = run_stability_analysis(
            base_items, classifier, paraphrases=paraphrases,
            label_dimensions=["cat", "subcat"], config=config,
        )
        # Both dimensions should show 1.0
        cat_stab = next(
            m for m in report.metrics if m.metric_name == "stability_cat"
        )
        assert cat_stab.value == pytest.approx(1.0)

    def test_sensitivity_change_detection(self):
        """Perturbation that should cause a change is detected."""
        base_items = {"item1": "original"}

        def classifier(text: str) -> dict[str, str]:
            if "modified" in text:
                return {"category": "B"}
            return {"category": "A"}

        perturbations = [
            PerturbationVariant(
                item_id="item1",
                variant_id="item1_t1",
                perturbation_type="add_modifier",
                text="modified original",
                expected_direction=ExpectedDirection(
                    changes_expected={"category": True},
                    expected_values={"category": "B"},
                ),
            ),
        ]
        config = StabilityConfig(
            thresholds=[
                ThresholdConfig(metric="change_detection", target=0.70, minimum=0.50),
                ThresholdConfig(metric="direction_accuracy", target=0.80, minimum=0.60),
            ],
            bootstrap=BootstrapConfig(iterations=100, seed=42),
        )
        report = run_stability_analysis(
            base_items, classifier, perturbations=perturbations, config=config,
        )
        cdr = next(m for m in report.metrics if m.metric_name == "change_detection")
        assert cdr.value == pytest.approx(1.0)

        da = next(m for m in report.metrics if m.metric_name == "direction_accuracy")
        assert da.value == pytest.approx(1.0)

    def test_false_change_rate(self):
        """Noop perturbation should not cause label change."""
        base_items = {"item1": "same text"}

        def classifier(text: str) -> dict[str, str]:
            return {"category": "A"}

        perturbations = [
            PerturbationVariant(
                item_id="item1",
                variant_id="item1_noop",
                perturbation_type="noop",
                text="same text with filler",
                expected_direction=ExpectedDirection(
                    changes_expected={},
                    expected_values={},
                ),
            ),
        ]
        config = StabilityConfig(
            thresholds=[],
            false_change_max=0.15,
            bootstrap=BootstrapConfig(iterations=100, seed=42),
        )
        report = run_stability_analysis(
            base_items, classifier, perturbations=perturbations, config=config,
        )
        fcr = next(m for m in report.metrics if m.metric_name == "false_change_rate")
        assert fcr.value == pytest.approx(0.0)
        assert report.verdict.value == "PASS"


class TestExpectedDirection:
    def test_expects_any_change(self):
        ed = ExpectedDirection(changes_expected={"cat": True})
        assert ed.expects_any_change() is True

    def test_no_change_expected(self):
        ed = ExpectedDirection(changes_expected={"cat": False})
        assert ed.expects_any_change() is False

    def test_empty(self):
        ed = ExpectedDirection()
        assert ed.expects_any_change() is False


class TestSkippedVerdict:
    def test_no_data_returns_skipped(self):
        report = run_stability_analysis(
            base_items={"x": "text"},
            classifier=lambda t: {"cat": "A"},
        )
        assert report.verdict.value == "SKIPPED"
