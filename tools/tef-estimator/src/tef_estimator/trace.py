"""
Calculation trace -- step-by-step arithmetic per vector.

Every calculation step carries a label, value, operation, source citation,
and running total. An analyst can point at any step and know exactly what
substituting their own number would do.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CalculationStep:
    """One step in a calculation trace."""
    label: str
    value: float
    operation: str  # "x", "+", "max()", "dampened()", "="
    source: str
    running: float

    def render_line(self, label_width: int = 30) -> str:
        return (
            f"  {self.operation:>3} {self.label:<{label_width}} "
            f"{self.value:>10.5f}   {self.source}"
        )


@dataclass
class CalculationTrace:
    """Step-by-step arithmetic for one vector or the aggregation."""
    vector_name: str
    steps: list[CalculationStep] = field(default_factory=list)

    def add_step(
        self,
        label: str,
        value: float,
        operation: str,
        source: str,
        running: float,
    ) -> None:
        self.steps.append(CalculationStep(
            label=label,
            value=value,
            operation=operation,
            source=source,
            running=running,
        ))

    @property
    def final_value(self) -> float:
        if self.steps:
            return self.steps[-1].running
        return 0.0

    def render_text(self) -> str:
        if not self.steps:
            return f"{self.vector_name} -- no trace recorded"

        label_width = max(len(s.label) for s in self.steps)
        label_width = max(label_width, 20)

        lines = [
            f"{self.vector_name.upper()} VECTOR -- Calculation Trace",
            "-" * 70,
        ]
        for step in self.steps:
            lines.append(step.render_line(label_width))
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "vector_name": self.vector_name,
            "steps": [
                {
                    "label": s.label,
                    "value": s.value,
                    "operation": s.operation,
                    "source": s.source,
                    "running": s.running,
                }
                for s in self.steps
            ],
        }
