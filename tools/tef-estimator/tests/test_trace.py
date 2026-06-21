"""Tests for calculation trace recording."""

from tef_estimator.trace import CalculationStep, CalculationTrace


class TestCalculationStep:
    def test_render_line(self):
        step = CalculationStep(
            label="Base rate",
            value=0.01,
            operation="=",
            source="Three-anchor consensus",
            running=0.01,
        )
        line = step.render_line()
        assert "Base rate" in line
        assert "0.01000" in line
        assert "Three-anchor consensus" in line


class TestCalculationTrace:
    def test_empty_trace(self):
        trace = CalculationTrace(vector_name="Test")
        assert trace.final_value == 0.0
        assert "no trace recorded" in trace.render_text()

    def test_add_steps(self):
        trace = CalculationTrace(vector_name="Credential")
        trace.add_step("Base rate", 0.01, "=", "Consensus", 0.01)
        trace.add_step("Sector mult", 1.5, "x", "IRIS", 0.015)
        assert len(trace.steps) == 2
        assert trace.final_value == 0.015

    def test_render_text(self):
        trace = CalculationTrace(vector_name="Exploitation")
        trace.add_step("Floor", 0.005, "=", "IRIS", 0.005)
        trace.add_step("Proportion", 0.22, "x", "DBIR", 0.0011)
        text = trace.render_text()
        assert "EXPLOITATION" in text
        assert "Floor" in text
        assert "Proportion" in text

    def test_to_dict(self):
        trace = CalculationTrace(vector_name="Phishing")
        trace.add_step("Step 1", 0.01, "=", "Source A", 0.01)
        d = trace.to_dict()
        assert d["vector_name"] == "Phishing"
        assert len(d["steps"]) == 1
        assert d["steps"][0]["label"] == "Step 1"
        assert d["steps"][0]["value"] == 0.01
