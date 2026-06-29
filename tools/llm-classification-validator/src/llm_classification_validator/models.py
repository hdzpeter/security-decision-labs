"""Shared data models for the evaluation framework."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Verdict(Enum):
    """Evaluation outcome."""

    PASS = "PASS"
    MARGINAL = "MARGINAL"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


@dataclass
class MetricResult:
    """A single metric measurement from any dimension."""

    dimension: str
    metric_name: str
    value: float
    interpretation: str = ""

    @property
    def summary(self) -> str:
        """One-line summary."""
        interp = f" ({self.interpretation})" if self.interpretation else ""
        return f"{self.dimension}/{self.metric_name}: {self.value:.4f}{interp}"


@dataclass
class RuleResult:
    """Result of a single rule evaluation."""

    rule_id: str
    rule_name: str
    category: str
    severity: str  # "error", "warning", "info"
    passed: bool
    item_id: str | None
    message: str
    details: dict[str, Any] | None = None


@dataclass
class CaseResult:
    """Result of a single test case (adversarial or stability)."""

    test_type: str
    test_id: str
    passed: bool
    details: str = ""
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        """One-line summary."""
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.test_type}/{self.test_id}: {self.details}"


@dataclass
class DimensionReport:
    """Report from a single evaluation dimension."""

    dimension: str
    verdict: Verdict
    metrics: list[MetricResult] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    item_issues: list[ItemIssue] = field(default_factory=list)
    duration_s: float = 0.0
    error: str | None = None


@dataclass
class ItemIssue:
    """A single issue found for a specific item."""

    item_id: str
    dimension: str
    severity: str  # "error", "warning", "info"
    message: str


@dataclass
class ItemReport:
    """Per-item evaluation summary across dimensions."""

    item_id: str
    label: str = ""
    predicted: dict[str, str] = field(default_factory=dict)
    reference: dict[str, str] = field(default_factory=dict)
    issues: list[ItemIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def domain_match(self) -> bool | None:
        pred = self.predicted.get("domain")
        ref = self.reference.get("domain")
        if pred is None or ref is None:
            return None
        return pred == ref


@dataclass
class EvaluationReport:
    """Consolidated report across all dimensions."""

    overall_verdict: Verdict
    dimensions: list[DimensionReport] = field(default_factory=list)
    items: list[ItemReport] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, str]:
        """Map dimension name to verdict string."""
        return {d.dimension: d.verdict.value for d in self.dimensions}

    def to_dict(self) -> dict[str, Any]:
        def _convert(obj: Any) -> Any:
            if isinstance(obj, Enum):
                return obj.value
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_convert(v) for v in obj]
            return obj
        return _convert(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationReport:
        dims = []
        for d in data.get("dimensions", []):
            issues = [ItemIssue(**ii) for ii in d.get("item_issues", [])]
            metrics = [MetricResult(**m) for m in d.get("metrics", [])]
            dims.append(DimensionReport(
                dimension=d["dimension"],
                verdict=Verdict(d["verdict"]),
                metrics=metrics,
                details=d.get("details", {}),
                item_issues=issues,
                duration_s=d.get("duration_s", 0.0),
                error=d.get("error"),
            ))
        items = []
        for it in data.get("items", []):
            issues = [ItemIssue(**ii) for ii in it.get("issues", [])]
            items.append(ItemReport(
                item_id=it["item_id"],
                label=it.get("label", ""),
                predicted=it.get("predicted", {}),
                reference=it.get("reference", {}),
                issues=issues,
            ))
        return cls(
            overall_verdict=Verdict(data["overall_verdict"]),
            dimensions=dims,
            items=items,
        )

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: str | Path) -> EvaluationReport:
        return cls.from_dict(json.loads(Path(path).read_text()))
