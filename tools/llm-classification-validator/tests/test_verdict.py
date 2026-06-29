"""Tests for verdict logic."""

import pytest

from llm_classification_validator.config import ThresholdConfig
from llm_classification_validator.models import Verdict
from llm_classification_validator.verdict import (
    aggregate_verdicts,
    compute_verdict,
    compute_verdict_from_threshold,
    interpret_kappa,
)


class TestComputeVerdict:
    def test_pass(self):
        assert compute_verdict(0.85, target=0.80, minimum=0.60) == Verdict.PASS

    def test_marginal(self):
        assert compute_verdict(0.70, target=0.80, minimum=0.60) == Verdict.MARGINAL

    def test_fail(self):
        assert compute_verdict(0.50, target=0.80, minimum=0.60) == Verdict.FAIL

    def test_exact_target(self):
        assert compute_verdict(0.80, target=0.80, minimum=0.60) == Verdict.PASS

    def test_exact_minimum(self):
        assert compute_verdict(0.60, target=0.80, minimum=0.60) == Verdict.MARGINAL

    def test_from_threshold(self):
        t = ThresholdConfig(metric="kappa", target=0.65, minimum=0.50)
        assert compute_verdict_from_threshold(0.70, t) == Verdict.PASS
        assert compute_verdict_from_threshold(0.55, t) == Verdict.MARGINAL
        assert compute_verdict_from_threshold(0.40, t) == Verdict.FAIL


class TestAggregateVerdicts:
    def test_all_pass(self):
        assert aggregate_verdicts([Verdict.PASS, Verdict.PASS]) == Verdict.PASS

    def test_one_fail(self):
        assert aggregate_verdicts([Verdict.PASS, Verdict.FAIL]) == Verdict.FAIL

    def test_one_marginal(self):
        assert aggregate_verdicts([Verdict.PASS, Verdict.MARGINAL]) == Verdict.MARGINAL

    def test_fail_overrides_marginal(self):
        assert aggregate_verdicts([Verdict.MARGINAL, Verdict.FAIL]) == Verdict.FAIL

    def test_skip_ignored(self):
        assert aggregate_verdicts([Verdict.PASS, Verdict.SKIPPED]) == Verdict.PASS

    def test_all_skipped(self):
        assert aggregate_verdicts([Verdict.SKIPPED]) == Verdict.ERROR

    def test_empty(self):
        assert aggregate_verdicts([]) == Verdict.SKIPPED


class TestInterpretKappa:
    def test_perfect(self):
        assert interpret_kappa(1.0) == "perfect"

    def test_below_perfect(self):
        assert interpret_kappa(0.85) == ""
        assert interpret_kappa(0.65) == ""
        assert interpret_kappa(0.10) == ""
