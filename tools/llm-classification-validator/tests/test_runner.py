"""Tests for the evaluation runner (orchestrator)."""

import pytest

from llm_classification_validator.models import DimensionReport, Verdict
from llm_classification_validator.runner import run_evaluation


def _make_report(dimension: str, verdict: Verdict) -> DimensionReport:
    return DimensionReport(dimension=dimension, verdict=verdict)


class TestRunner:
    def test_all_pass(self):
        def coherence():
            return _make_report("coherence", Verdict.PASS)

        def consistency():
            return _make_report("consistency", Verdict.PASS)

        result = run_evaluation(foundation=[coherence, consistency])
        assert result.overall_verdict == Verdict.PASS
        assert len(result.dimensions) == 2

    def test_one_fail(self):
        def good():
            return _make_report("good", Verdict.PASS)

        def bad():
            return _make_report("bad", Verdict.FAIL)

        result = run_evaluation(foundation=[good, bad])
        assert result.overall_verdict == Verdict.FAIL

    def test_marginal_propagates(self):
        def pass_dim():
            return _make_report("pass", Verdict.PASS)

        def marginal_dim():
            return _make_report("marginal", Verdict.MARGINAL)

        result = run_evaluation(foundation=[pass_dim, marginal_dim])
        assert result.overall_verdict == Verdict.MARGINAL

    def test_advanced_parallel(self):
        def adv1():
            return _make_report("adversarial", Verdict.PASS)

        def adv2():
            return _make_report("stability", Verdict.PASS)

        result = run_evaluation(advanced=[adv1, adv2], parallel_advanced=True)
        assert result.overall_verdict == Verdict.PASS
        assert len(result.dimensions) == 2

    def test_exception_produces_error(self):
        def exploding():
            raise RuntimeError("boom")

        result = run_evaluation(foundation=[exploding])
        assert result.overall_verdict == Verdict.ERROR
        assert result.dimensions[0].error == "boom"

    def test_mixed_phases(self):
        def foundation_dim():
            return _make_report("coherence", Verdict.PASS)

        def advanced_dim():
            return _make_report("stability", Verdict.PASS)

        result = run_evaluation(
            foundation=[foundation_dim],
            advanced=[advanced_dim],
        )
        assert result.overall_verdict == Verdict.PASS
        assert len(result.dimensions) == 2

    def test_empty_evaluation(self):
        result = run_evaluation()
        # No dimensions at all -> SKIPPED
        assert result.overall_verdict in (Verdict.SKIPPED, Verdict.ERROR)

    def test_summary(self):
        def d1():
            return _make_report("coherence", Verdict.PASS)

        def d2():
            return _make_report("consistency", Verdict.MARGINAL)

        result = run_evaluation(foundation=[d1, d2])
        s = result.summary
        assert s["coherence"] == "PASS"
        assert s["consistency"] == "MARGINAL"
