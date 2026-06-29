"""NiceGUI web interface for Assay evaluation results.

Launch via: python -m llm_classification_validator.ui
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import plotly.graph_objects as go
from nicegui import ui

from llm_classification_validator import __version__
from llm_classification_validator.coherence.sampling import SamplePlan
from llm_classification_validator.config import EvalConfig
from llm_classification_validator.models import DimensionReport, EvaluationReport, ItemReport, MetricResult, Verdict
from llm_classification_validator.verdict import compute_verdict

_CFG = EvalConfig()

ACCENT = "#E74C3C"
ACCENT_GREEN = "#2ECC71"
ACCENT_AMBER = "#F39C12"
ACCENT_BLUE = "#3498DB"
BG_DARK = "#0f172a"
TEXT_MUTED = "#94a3b8"

VERDICT_COLORS = {
    Verdict.PASS: ACCENT_GREEN,
    Verdict.MARGINAL: ACCENT_AMBER,
    Verdict.FAIL: ACCENT,
    Verdict.SKIPPED: TEXT_MUTED,
    Verdict.ERROR: ACCENT,
}

VERDICT_ICONS = {
    Verdict.PASS: "check_circle",
    Verdict.MARGINAL: "warning",
    Verdict.FAIL: "cancel",
    Verdict.SKIPPED: "remove_circle_outline",
    Verdict.ERROR: "error",
}

DIMENSION_ORDER = ["coherence", "consistency", "convergent", "adversarial", "stability"]


def _parse_stratum_key(key: str) -> tuple[str, str]:
    """Parse '(source, target)' back into readable components."""
    inner = key.strip("()")
    parts = [p.strip() for p in inner.split(",", 1)]
    if len(parts) == 2:
        return parts[0], parts[1]
    return key, ""

HEADLINE_METRICS = {
    "coherence": "mean_kappa",
    "consistency": "pass_rate",
    "convergent": "kappa",
    "adversarial": "combined_score",
    "stability": "stability",
}

OVERALL_POLICIES = {
    "all_pass": "All must PASS",
    "no_fail": "No FAIL (MARGINAL OK)",
    "majority": "Majority (3/5) PASS",
    "weighted": "Weighted (configurable)",
}


@dataclass
class DimensionThreshold:
    target: float
    minimum: float
    required: bool = True
    weight: float = 1.0


@dataclass
class ThresholdState:
    policy: str = "all_pass"
    dimensions: dict[str, DimensionThreshold] = field(default_factory=dict)

    @classmethod
    def defaults(cls) -> ThresholdState:
        coh = {t.metric: t for t in _CFG.coherence.thresholds}
        conv = {t.metric: t for t in _CFG.convergent.thresholds}
        stab = {t.metric: t for t in _CFG.stability.thresholds}
        return cls(
            policy="all_pass",
            dimensions={
                "coherence": DimensionThreshold(
                    target=coh["mean_kappa"].target,
                    minimum=coh["mean_kappa"].minimum,
                ),
                "consistency": DimensionThreshold(
                    target=_CFG.consistency.pass_rate_target,
                    minimum=_CFG.consistency.pass_rate_minimum,
                ),
                "convergent": DimensionThreshold(
                    target=conv["kappa"].target,
                    minimum=conv["kappa"].minimum,
                ),
                "adversarial": DimensionThreshold(
                    target=_CFG.adversarial.combined_target,
                    minimum=_CFG.adversarial.combined_minimum,
                ),
                "stability": DimensionThreshold(
                    target=stab["stability"].target,
                    minimum=stab["stability"].minimum,
                ),
            },
        )


def _overall_verdict(dim_verdicts: dict[str, Verdict], state: ThresholdState) -> Verdict:
    active = {d: v for d, v in dim_verdicts.items() if state.dimensions.get(d, DimensionThreshold(0, 0)).required}
    if not active:
        return Verdict.SKIPPED

    if state.policy == "all_pass":
        if any(v == Verdict.FAIL for v in active.values()):
            return Verdict.FAIL
        if any(v == Verdict.MARGINAL for v in active.values()):
            return Verdict.MARGINAL
        return Verdict.PASS

    if state.policy == "no_fail":
        if any(v == Verdict.FAIL for v in active.values()):
            return Verdict.FAIL
        return Verdict.PASS

    if state.policy == "majority":
        pass_count = sum(1 for v in active.values() if v == Verdict.PASS)
        if pass_count > len(active) / 2:
            return Verdict.PASS
        fail_count = sum(1 for v in active.values() if v == Verdict.FAIL)
        if fail_count > len(active) / 2:
            return Verdict.FAIL
        return Verdict.MARGINAL

    if state.policy == "weighted":
        total_w = sum(state.dimensions[d].weight for d in active)
        if total_w == 0:
            return Verdict.SKIPPED
        pass_w = sum(state.dimensions[d].weight for d, v in active.items() if v == Verdict.PASS)
        fail_w = sum(state.dimensions[d].weight for d, v in active.items() if v == Verdict.FAIL)
        ratio = pass_w / total_w
        if ratio >= 0.8:
            return Verdict.PASS
        if fail_w / total_w > 0.5:
            return Verdict.FAIL
        return Verdict.MARGINAL

    return Verdict.PASS


def _verdict_badge(verdict: Verdict) -> None:
    color = VERDICT_COLORS.get(verdict, TEXT_MUTED)
    ui.badge(verdict.value, color=color).classes("text-sm font-bold")


def _dimension_headline_score(dim: DimensionReport) -> float | None:
    target = HEADLINE_METRICS.get(dim.dimension)
    if target is None:
        return None
    for m in dim.metrics:
        if m.metric_name == target:
            return m.value
    return None


def _radar_figure(report: EvaluationReport, thresholds: ThresholdState) -> go.Figure:
    dim_scores: dict[str, float] = {}
    for dim in report.dimensions:
        score = _dimension_headline_score(dim)
        if score is not None:
            dim_scores[dim.dimension] = score

    ordered = [d for d in DIMENSION_ORDER if d in dim_scores]
    if not ordered:
        return go.Figure()

    labels = [d.title() for d in ordered]
    values = [dim_scores[d] for d in ordered]
    targets = [thresholds.dimensions[d].target for d in ordered]
    minimums = [thresholds.dimensions[d].minimum for d in ordered]

    labels_closed = labels + [labels[0]]
    values_closed = values + [values[0]]
    targets_closed = targets + [targets[0]]
    minimums_closed = minimums + [minimums[0]]

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=minimums_closed,
        theta=labels_closed,
        fill="toself",
        fillcolor="rgba(231, 76, 60, 0.08)",
        line=dict(color=ACCENT, width=1, dash="dot"),
        name="Minimum",
        hovertemplate="%{theta}: %{r:.2f}<extra>Minimum</extra>",
    ))
    fig.add_trace(go.Scatterpolar(
        r=targets_closed,
        theta=labels_closed,
        fill="toself",
        fillcolor="rgba(46, 204, 113, 0.08)",
        line=dict(color=ACCENT_GREEN, width=1, dash="dot"),
        name="Target",
        hovertemplate="%{theta}: %{r:.2f}<extra>Target</extra>",
    ))
    fig.add_trace(go.Scatterpolar(
        r=values_closed,
        theta=labels_closed,
        fill="toself",
        fillcolor="rgba(231, 76, 60, 0.15)",
        line=dict(color=ACCENT, width=2),
        marker=dict(size=6, color=ACCENT),
        name="Actual",
        hovertemplate="%{theta}: %{r:.4f}<extra>Actual</extra>",
    ))

    fig.update_layout(
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(
                visible=True, range=[0, 1],
                tickvals=[0.25, 0.5, 0.75, 1.0],
                ticktext=["0.25", "0.50", "0.75", "1.00"],
                gridcolor="rgba(255,255,255,0.1)",
                linecolor="rgba(255,255,255,0.1)",
                tickfont=dict(color=TEXT_MUTED, size=10),
            ),
            angularaxis=dict(
                gridcolor="rgba(255,255,255,0.1)",
                linecolor="rgba(255,255,255,0.1)",
                tickfont=dict(color="white", size=12),
            ),
        ),
        height=350,
        margin=dict(l=60, r=60, t=30, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white"),
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5,
            font=dict(size=10, color=TEXT_MUTED),
        ),
    )
    return fig


# ── Dimension detail renderers ──────────────────────────────────────────

def _render_coherence(dim: DimensionReport) -> None:
    metrics_by_name = {m.metric_name: m for m in dim.metrics}
    mean_k = metrics_by_name.get("mean_kappa")
    fleiss = metrics_by_name.get("fleiss_kappa")
    ci_lo = metrics_by_name.get("mean_kappa_ci_lower")
    ci_hi = metrics_by_name.get("mean_kappa_ci_upper")

    with ui.row().classes("w-full gap-8"):
        with ui.column().classes("items-center flex-1"):
            val = mean_k.value if mean_k else 0
            ui.label(f"{val:.4f}").classes("text-4xl font-bold font-mono").style(f"color: {ACCENT}")
            ui.label("Mean Kappa").classes("text-xs text-slate-400")
        with ui.column().classes("items-center flex-1"):
            val = fleiss.value if fleiss else 0
            ui.label(f"{val:.4f}").classes("text-4xl font-bold font-mono text-blue-400")
            ui.label("Fleiss' Kappa").classes("text-xs text-slate-400")
        if ci_lo and ci_hi:
            with ui.column().classes("items-center flex-1"):
                ui.label(f"[{ci_lo.value:.4f}, {ci_hi.value:.4f}]").classes("text-lg font-mono text-slate-300")
                ui.label("90% Bootstrap CI").classes("text-xs text-slate-400")

    pairwise = [m for m in dim.metrics if m.metric_name.startswith("cohens_kappa_")]
    if pairwise:
        ui.separator().classes("bg-slate-700 my-3")
        ui.label("Pairwise Agreement").classes("text-xs font-semibold text-slate-400")
        with ui.row().classes("w-full gap-4 flex-wrap"):
            for m in pairwise:
                pair_name = m.metric_name.replace("cohens_kappa_", "").replace("_vs_", " vs ")
                with ui.column().classes("items-center"):
                    ui.label(f"{m.value:.4f}").classes("text-sm font-mono text-white")
                    ui.label(pair_name).classes("text-xs text-slate-500")


def _render_consistency(dim: DimensionReport) -> None:
    metrics_by_name = {m.metric_name: m for m in dim.metrics}
    pr = metrics_by_name.get("pass_rate")
    errs = metrics_by_name.get("error_count")
    warns = metrics_by_name.get("warning_count")

    with ui.row().classes("w-full gap-8"):
        with ui.column().classes("items-center flex-1"):
            val = pr.value if pr else 0
            color = ACCENT_GREEN if val >= _CFG.consistency.pass_rate_target else (ACCENT_AMBER if val >= _CFG.consistency.pass_rate_minimum else ACCENT)
            ui.label(f"{val:.0%}").classes("text-4xl font-bold font-mono").style(f"color: {color}")
            ui.label("Pass Rate").classes("text-xs text-slate-400")
            if pr:
                ui.label(pr.interpretation).classes("text-xs text-slate-500 font-mono")
        with ui.column().classes("items-center flex-1"):
            val = int(errs.value) if errs else 0
            color = ACCENT_GREEN if val == 0 else ACCENT
            ui.label(str(val)).classes("text-4xl font-bold font-mono").style(f"color: {color}")
            ui.label("Errors").classes("text-xs text-slate-400")
        with ui.column().classes("items-center flex-1"):
            val = int(warns.value) if warns else 0
            color = ACCENT_GREEN if val == 0 else ACCENT_AMBER
            ui.label(str(val)).classes("text-4xl font-bold font-mono").style(f"color: {color}")
            ui.label("Warnings").classes("text-xs text-slate-400")

    details = dim.details or {}
    error_msgs = details.get("errors", [])
    warning_msgs = details.get("warnings", [])
    if error_msgs or warning_msgs:
        ui.separator().classes("bg-slate-700 my-3")
        for msg in error_msgs:
            with ui.row().classes("items-center gap-2"):
                ui.icon("error", size="xs").classes("text-red-400")
                ui.label(msg).classes("text-xs font-mono text-red-300")
        for msg in warning_msgs:
            with ui.row().classes("items-center gap-2"):
                ui.icon("warning", size="xs").classes("text-amber-400")
                ui.label(msg).classes("text-xs font-mono text-amber-300")


def _render_convergent(dim: DimensionReport) -> None:
    metrics_by_name = {m.metric_name: m for m in dim.metrics}
    kappa = metrics_by_name.get("kappa")
    accuracy = metrics_by_name.get("accuracy")
    jaccard = metrics_by_name.get("jaccard")
    jac_lo = metrics_by_name.get("jaccard_ci_lower")
    jac_hi = metrics_by_name.get("jaccard_ci_upper")

    with ui.row().classes("w-full gap-8"):
        if kappa:
            with ui.column().classes("items-center flex-1"):
                ui.label(f"{kappa.value:.4f}").classes("text-4xl font-bold font-mono").style(f"color: {ACCENT}")
                ui.label("Cohen's Kappa").classes("text-xs text-slate-400")
        if accuracy:
            with ui.column().classes("items-center flex-1"):
                ui.label(f"{accuracy.value:.0%}").classes("text-4xl font-bold font-mono text-blue-400")
                ui.label("Exact Match").classes("text-xs text-slate-400")
                ui.label(accuracy.interpretation).classes("text-xs text-slate-500 font-mono")
        if jaccard:
            with ui.column().classes("items-center flex-1"):
                ui.label(f"{jaccard.value:.4f}").classes("text-2xl font-bold font-mono text-slate-200")
                ui.label("Mean Jaccard").classes("text-xs text-slate-400")
                if jac_lo and jac_hi:
                    ui.label(f"CI [{jac_lo.value:.4f}, {jac_hi.value:.4f}]").classes("text-xs text-slate-500")


def _render_adversarial(dim: DimensionReport) -> None:
    metrics_by_name = {m.metric_name: m for m in dim.metrics}
    disc = metrics_by_name.get("discrimination_score")
    amb = metrics_by_name.get("ambiguity_score")
    combined = metrics_by_name.get("combined_score")

    _adv = _CFG.adversarial
    with ui.row().classes("w-full gap-8"):
        if combined:
            with ui.column().classes("items-center flex-1"):
                color = ACCENT_GREEN if combined.value >= _adv.combined_target else (ACCENT_AMBER if combined.value >= _adv.combined_minimum else ACCENT)
                ui.label(f"{combined.value:.2%}").classes("text-4xl font-bold font-mono").style(f"color: {color}")
                ui.label("Combined Score").classes("text-xs text-slate-400")
        if disc:
            with ui.column().classes("items-center flex-1"):
                color = ACCENT_GREEN if disc.value >= _adv.discrimination_target else (ACCENT_AMBER if disc.value >= _adv.discrimination_minimum else ACCENT)
                ui.label(f"{disc.value:.2%}").classes("text-2xl font-bold font-mono").style(f"color: {color}")
                ui.label("Discrimination").classes("text-xs text-slate-400")
                ui.label(disc.interpretation).classes("text-xs text-slate-500")
        if amb:
            with ui.column().classes("items-center flex-1"):
                ui.label(f"{amb.value:.2%}").classes("text-2xl font-bold font-mono text-blue-400")
                ui.label("Ambiguity").classes("text-xs text-slate-400")
                ui.label(amb.interpretation).classes("text-xs text-slate-500")

    # Minimal pair detail table
    disc_cases = dim.details.get("discrimination_cases", [])
    if disc_cases:
        ui.separator().classes("bg-slate-700 my-3")
        ui.label("Minimal Pairs").classes("text-xs font-semibold text-slate-400 mb-2")
        for case in disc_cases:
            passed = case.get("passed", False)
            border = "border-l-green-500" if passed else "border-l-red-500"
            icon = "check_circle" if passed else "cancel"
            with ui.card().classes(f"w-full bg-slate-900 border-slate-700 border-l-4 {border} mb-2"):
                with ui.row().classes("w-full items-center justify-between mb-2"):
                    ui.label(case.get("test_id", "")).classes("text-xs font-mono font-bold text-white")
                    ui.badge("PASS" if passed else "FAIL", color=ACCENT_GREEN if passed else ACCENT).classes("text-xs")

                with ui.grid(columns=2).classes("w-full gap-x-6 gap-y-1"):
                    # Input A
                    exp_a = case.get("expected_a", "?")
                    act_a = case.get("actual_a", "?")
                    a_ok = exp_a == act_a if exp_a else True
                    ui.label("Input A").classes("text-xs font-semibold text-slate-500")
                    with ui.row().classes("items-center gap-2"):
                        ui.badge(f"expected {exp_a}", color=ACCENT_BLUE).classes("text-xs")
                        ui.badge(f"got {act_a}", color=ACCENT_GREEN if a_ok else ACCENT).classes("text-xs")
                    ui.label(case.get("input_a", "")[:100]).classes("text-xs text-slate-400 col-span-2")

                    # Input B
                    exp_b = case.get("expected_b", "?")
                    act_b = case.get("actual_b", "?")
                    b_ok = exp_b == act_b if exp_b else True
                    ui.label("Input B").classes("text-xs font-semibold text-slate-500")
                    with ui.row().classes("items-center gap-2"):
                        ui.badge(f"expected {exp_b}", color=ACCENT_BLUE).classes("text-xs")
                        ui.badge(f"got {act_b}", color=ACCENT_GREEN if b_ok else ACCENT).classes("text-xs")
                    ui.label(case.get("input_b", "")[:100]).classes("text-xs text-slate-400 col-span-2")

    # Ambiguity detail table
    amb_cases = dim.details.get("ambiguity_cases", [])
    if amb_cases:
        ui.separator().classes("bg-slate-700 my-3")
        ui.label("Ambiguity Cases").classes("text-xs font-semibold text-slate-400 mb-2")
        for case in amb_cases:
            passed = case.get("passed", False)
            border = "border-l-green-500" if passed else "border-l-amber-500"
            with ui.card().classes(f"w-full bg-slate-900 border-slate-700 border-l-4 {border} mb-2"):
                with ui.row().classes("w-full items-center justify-between mb-1"):
                    ui.label(case.get("test_id", "")).classes("text-xs font-mono font-bold text-white")
                    with ui.row().classes("items-center gap-2"):
                        ui.badge(f"got {case.get('actual', '?')}", color=ACCENT_GREEN if passed else ACCENT_AMBER).classes("text-xs")
                        acceptable = case.get("acceptable", [])
                        ui.label(f"acceptable: {', '.join(acceptable)}").classes("text-xs text-slate-500")
                ui.label(case.get("input", "")[:120]).classes("text-xs text-slate-400")


def _render_stability(dim: DimensionReport) -> None:
    metrics_by_name = {m.metric_name: m for m in dim.metrics}
    overall = metrics_by_name.get("stability")
    ci_lo = metrics_by_name.get("stability_ci_lower")
    ci_hi = metrics_by_name.get("stability_ci_upper")
    change_det = metrics_by_name.get("change_detection")
    dir_acc = metrics_by_name.get("direction_accuracy")
    false_cr = metrics_by_name.get("false_change_rate")

    _stab_t = {t.metric: t for t in _CFG.stability.thresholds}
    _stab_thresh = _stab_t.get("stability")
    with ui.row().classes("w-full gap-8"):
        if overall:
            with ui.column().classes("items-center flex-1"):
                color = ACCENT_GREEN if overall.value >= _stab_thresh.target else (ACCENT_AMBER if overall.value >= _stab_thresh.minimum else ACCENT)
                ui.label(f"{overall.value:.2%}").classes("text-4xl font-bold font-mono").style(f"color: {color}")
                ui.label("Paraphrase Stability").classes("text-xs text-slate-400")
                if ci_lo and ci_hi:
                    ui.label(f"CI [{ci_lo.value:.4f}, {ci_hi.value:.4f}]").classes("text-xs text-slate-500")
        if change_det:
            with ui.column().classes("items-center flex-1"):
                ui.label(f"{change_det.value:.2%}").classes("text-2xl font-bold font-mono text-blue-400")
                ui.label("Change Detection").classes("text-xs text-slate-400")
        if dir_acc:
            with ui.column().classes("items-center flex-1"):
                ui.label(f"{dir_acc.value:.2%}").classes("text-2xl font-bold font-mono text-slate-200")
                ui.label("Direction Accuracy").classes("text-xs text-slate-400")

    if false_cr:
        ui.separator().classes("bg-slate-700 my-3")
        color = ACCENT_GREEN if false_cr.value <= _CFG.stability.false_change_max else ACCENT
        with ui.row().classes("items-center gap-3"):
            ui.icon("shield" if false_cr.value <= _CFG.stability.false_change_max else "warning", size="sm").style(f"color: {color}")
            ui.label(f"False change rate: {false_cr.value:.2%}").classes("text-sm font-mono").style(f"color: {color}")

    per_dim = [m for m in dim.metrics if m.metric_name.startswith("stability_") and m.metric_name not in
               ("stability_ci_lower", "stability_ci_upper", "stability_jaccard")]
    if per_dim:
        ui.separator().classes("bg-slate-700 my-3")
        ui.label("Per-Dimension Stability").classes("text-xs font-semibold text-slate-400")
        with ui.row().classes("w-full gap-4 flex-wrap"):
            for m in per_dim:
                dim_name = m.metric_name.replace("stability_", "")
                with ui.column().classes("items-center"):
                    color = ACCENT_GREEN if m.value >= _stab_thresh.target else (ACCENT_AMBER if m.value >= _stab_thresh.minimum else ACCENT)
                    ui.label(f"{m.value:.2%}").classes("text-sm font-mono").style(f"color: {color}")
                    ui.label(dim_name).classes("text-xs text-slate-500")


_DIMENSION_RENDERERS = {
    "coherence": _render_coherence,
    "consistency": _render_consistency,
    "convergent": _render_convergent,
    "adversarial": _render_adversarial,
    "stability": _render_stability,
}


# ── Main app ────────────────────────────────────────────────────────────

class ValidatorApp:
    def __init__(self, report: EvaluationReport, sample_plan: SamplePlan | None = None):
        self.report = report
        self.sample_plan = sample_plan
        self.thresholds = ThresholdState.defaults()
        self.main_container = None
        self.overall_badge_container = None

    def _recompute_verdicts(self) -> tuple[dict[str, Verdict], Verdict]:
        dim_verdicts: dict[str, Verdict] = {}
        for dim in self.report.dimensions:
            score = _dimension_headline_score(dim)
            if score is None:
                dim_verdicts[dim.dimension] = dim.verdict
                continue
            t = self.thresholds.dimensions.get(dim.dimension)
            if t is None:
                dim_verdicts[dim.dimension] = dim.verdict
                continue
            dim_verdicts[dim.dimension] = compute_verdict(score, t.target, t.minimum)
        overall = _overall_verdict(dim_verdicts, self.thresholds)
        return dim_verdicts, overall

    def _on_threshold_change(self):
        if self.main_container is None:
            return
        self.main_container.clear()
        with self.main_container:
            self._render_content()
        if self.overall_badge_container:
            self.overall_badge_container.clear()
            with self.overall_badge_container:
                _, overall = self._recompute_verdicts()
                _verdict_badge(overall)

    def _set_target(self, dim: str, value):
        if value is not None:
            self.thresholds.dimensions[dim].target = float(value)
            self._on_threshold_change()

    def _set_minimum(self, dim: str, value):
        if value is not None:
            self.thresholds.dimensions[dim].minimum = float(value)
            self._on_threshold_change()

    def _set_required(self, dim: str, value: bool):
        self.thresholds.dimensions[dim].required = value
        self._on_threshold_change()

    def _set_weight(self, dim: str, value):
        if value is not None:
            self.thresholds.dimensions[dim].weight = float(value)
            self._on_threshold_change()

    def _set_policy(self, value: str):
        self.thresholds.policy = value
        self._on_threshold_change()

    def build(self):
        ui.dark_mode(True)

        ui.add_head_html("""
        <style>
            body { background: #0f172a !important; }
            .q-card { border: 1px solid #334155 !important; }
            .q-expansion-item { border: 1px solid #334155 !important; border-radius: 8px !important; }
        </style>
        """)

        with ui.header().classes("bg-slate-900 border-b border-slate-700"):
            with ui.row().classes("w-full items-center justify-between px-4"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("science", size="md").classes("text-red-500")
                    ui.label("LLM Classification Validator").classes("text-xl font-bold text-white")
                    ui.badge(f"v{__version__}", color="grey").classes("text-xs")

                with ui.row().classes("items-center gap-3"):
                    ui.label("Overall:").classes("text-sm text-slate-400")
                    self.overall_badge_container = ui.row()
                    with self.overall_badge_container:
                        _, overall = self._recompute_verdicts()
                        _verdict_badge(overall)

        with ui.row().classes("w-full h-full").style("min-height: calc(100vh - 120px)"):
            # ── Sidebar: threshold configuration ──
            with ui.column().classes(
                "w-80 p-4 bg-slate-900 border-r border-slate-700 shrink-0 overflow-y-auto"
            ).style("min-height: calc(100vh - 120px)"):
                self._build_sidebar()

            # ── Main content ──
            self.main_container = ui.column().classes("flex-1 p-6 gap-4 overflow-y-auto max-w-5xl")
            with self.main_container:
                self._render_content()

        with ui.footer().classes("bg-slate-900 border-t border-slate-700"):
            with ui.row().classes("w-full items-center justify-between px-4"):
                ui.label("LLM Classification Validator").classes("text-xs text-slate-500")
                dims_run = len(self.report.dimensions)
                ui.label(f"{dims_run} dimensions evaluated").classes("text-xs text-slate-500")

    def _build_sidebar(self):
        ui.label("Verdict Policy").classes("text-lg font-bold text-white mb-2")

        ui.select(
            OVERALL_POLICIES,
            value=self.thresholds.policy,
            label="Overall Policy",
            on_change=lambda e: self._set_policy(e.value),
        ).classes("w-full").props("dense outlined dark")

        ui.separator().classes("bg-slate-700 my-3")
        ui.label("Dimension Thresholds").classes("text-lg font-bold text-white mb-2")

        for dim_name in DIMENSION_ORDER:
            t = self.thresholds.dimensions.get(dim_name)
            if t is None:
                continue

            dim_report = next((d for d in self.report.dimensions if d.dimension == dim_name), None)
            score = _dimension_headline_score(dim_report) if dim_report else None
            score_text = f" ({score:.2f})" if score is not None else ""

            with ui.expansion(
                f"{dim_name.title()}{score_text}",
                icon="tune",
            ).classes("w-full").props("dense"):

                with ui.row().classes("w-full items-center gap-2 mb-1"):
                    ui.switch(
                        "Required",
                        value=t.required,
                        on_change=lambda e, d=dim_name: self._set_required(d, e.value),
                    ).props("dense dark color=red")

                ui.number(
                    "Target",
                    value=t.target,
                    min=0.0, max=1.0, step=0.05,
                    on_change=lambda e, d=dim_name: self._set_target(d, e.value),
                ).classes("w-full").props("dense outlined dark")

                ui.number(
                    "Minimum",
                    value=t.minimum,
                    min=0.0, max=1.0, step=0.05,
                    on_change=lambda e, d=dim_name: self._set_minimum(d, e.value),
                ).classes("w-full").props("dense outlined dark")

                if self.thresholds.policy == "weighted":
                    ui.number(
                        "Weight",
                        value=t.weight,
                        min=0.0, max=5.0, step=0.1,
                        on_change=lambda e, d=dim_name: self._set_weight(d, e.value),
                    ).classes("w-full").props("dense outlined dark")

    def _render_content(self):
        dim_verdicts, overall = self._recompute_verdicts()
        self._render_overview(dim_verdicts, overall)
        self._render_dimensions(dim_verdicts)
        if self.report.items:
            self._render_items()

    def _render_overview(self, dim_verdicts: dict[str, Verdict], overall: Verdict):
        with ui.row().classes("w-full gap-4"):
            with ui.card().classes("flex-1 bg-slate-800 border-slate-700"):
                ui.label("Dimension Radar").classes("text-sm font-semibold text-slate-300 mb-2")
                ui.plotly(_radar_figure(self.report, self.thresholds)).classes("w-full")

            with ui.card().classes("flex-1 bg-slate-800 border-slate-700"):
                ui.label("Status").classes("text-sm font-semibold text-slate-300 mb-2")

                for dim_name in DIMENSION_ORDER:
                    dim = next((d for d in self.report.dimensions if d.dimension == dim_name), None)
                    if dim is None:
                        continue
                    score = _dimension_headline_score(dim)
                    verdict = dim_verdicts.get(dim_name, dim.verdict)
                    t = self.thresholds.dimensions.get(dim_name)
                    icon = VERDICT_ICONS.get(verdict, "help")
                    color = VERDICT_COLORS.get(verdict, TEXT_MUTED)
                    required = t.required if t else True

                    with ui.row().classes("w-full items-center justify-between py-2 border-b border-slate-700/50"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon(icon, size="xs").style(f"color: {color}")
                            label_text = dim_name.title()
                            if not required:
                                label_text += " (optional)"
                            ui.label(label_text).classes(
                                "text-sm text-white" if required else "text-sm text-slate-500 italic"
                            )
                        with ui.row().classes("items-center gap-3"):
                            if score is not None:
                                ui.label(f"{score:.4f}").classes("text-sm font-mono text-slate-300")
                            _verdict_badge(verdict)
                            if dim.duration_s > 0:
                                ui.label(f"{dim.duration_s:.3f}s").classes("text-xs text-slate-500")

    def _render_dimensions(self, dim_verdicts: dict[str, Verdict]):
        for dim_name in DIMENSION_ORDER:
            dim = next((d for d in self.report.dimensions if d.dimension == dim_name), None)
            if dim is None:
                continue

            verdict = dim_verdicts.get(dim_name, dim.verdict)
            icon = VERDICT_ICONS.get(verdict, "help")
            default_open = verdict in (Verdict.FAIL, Verdict.MARGINAL)

            with ui.expansion(
                f"{dim_name.title()} — {verdict.value}",
                icon=icon,
            ).classes("w-full bg-slate-800 border-slate-700").props(
                "default-opened" if default_open else ""
            ):
                renderer = _DIMENSION_RENDERERS.get(dim_name)
                if renderer:
                    renderer(dim)
                else:
                    for m in dim.metrics:
                        ui.label(m.summary).classes("text-xs font-mono text-slate-300")

                if dim_name == "coherence" and self.sample_plan is not None:
                    self._render_sample_status()

                if dim.error:
                    ui.separator().classes("bg-slate-700 my-2")
                    ui.label(f"Error: {dim.error}").classes("text-xs text-red-400")

                if dim.metrics:
                    with ui.expansion("All Metrics", icon="list").classes("w-full mt-2"):
                        for m in dim.metrics:
                            with ui.row().classes("w-full justify-between py-1"):
                                ui.label(m.metric_name).classes("text-xs text-slate-500 font-mono")
                                ui.label(f"{m.value:.4f}").classes("text-xs text-white font-mono")
                                if m.interpretation:
                                    ui.label(m.interpretation).classes("text-xs text-slate-500 italic")


    def _render_sample_status(self):
        sp = self.sample_plan
        if sp is None:
            return

        ui.separator().classes("bg-slate-700 my-3")

        sufficient_color = ACCENT_GREEN if sp.sufficient else ACCENT
        sufficient_icon = "check_circle" if sp.sufficient else "warning"
        status_text = "Expert review covers all mapping regions" if sp.sufficient else "Some mapping regions have too few expert-reviewed controls"

        with ui.row().classes("w-full items-center gap-3 mb-2"):
            ui.icon(sufficient_icon, size="sm").style(f"color: {sufficient_color}")
            ui.label("Expert Review Coverage").classes("text-sm font-semibold text-white")

        ui.label(status_text).classes("text-xs text-slate-400 mb-2")

        with ui.row().classes("w-full gap-6 mb-2"):
            with ui.column().classes("items-center"):
                ui.label(str(sp.sample_size)).classes("text-2xl font-bold font-mono text-white")
                ui.label(f"of {sp.total_items} reviewed").classes("text-xs text-slate-400")
            with ui.column().classes("items-center"):
                thin = sum(1 for c in sp.strata.values() if c < 3)
                ok = len(sp.strata) - thin
                color = ACCENT_GREEN if thin == 0 else ACCENT_AMBER
                ui.label(f"{ok}/{len(sp.strata)}").classes("text-2xl font-bold font-mono").style(f"color: {color}")
                ui.label("regions with 3+ reviews").classes("text-xs text-slate-400")

        thin_regions = [(k, v) for k, v in sorted(sp.strata.items()) if v < 3]
        if thin_regions:
            with ui.expansion(
                f"{len(thin_regions)} region(s) need more expert review",
                icon="warning",
            ).classes("w-full").props("dense default-opened" if len(thin_regions) <= 5 else "dense"):
                for key, count in thin_regions:
                    src, tgt = _parse_stratum_key(key)
                    with ui.row().classes("w-full justify-between py-1"):
                        ui.label(f"{src} mapped to {tgt}").classes("text-xs text-slate-300")
                        ui.label(f"{count} reviewed (need 3+)").classes("text-xs font-mono text-amber-400")

    def _render_items(self):
        items_sorted = sorted(self.report.items, key=lambda x: x.issue_count, reverse=True)

        error_count = sum(i.error_count for i in items_sorted)
        warn_count = sum(i.warning_count for i in items_sorted)
        clean_count = sum(1 for i in items_sorted if i.issue_count == 0)

        with ui.card().classes("w-full bg-slate-800 border-slate-700"):
            with ui.row().classes("w-full items-center justify-between mb-4"):
                ui.label("Per-Control View").classes("text-lg font-bold text-white")
                with ui.row().classes("gap-4"):
                    ui.badge(f"{error_count} errors", color=ACCENT).classes("text-xs")
                    ui.badge(f"{warn_count} warnings", color=ACCENT_AMBER).classes("text-xs")
                    ui.badge(f"{clean_count}/{len(items_sorted)} clean", color=ACCENT_GREEN).classes("text-xs")

            for item in items_sorted:
                has_issues = item.issue_count > 0
                domain_match = item.domain_match
                if domain_match is False:
                    border_color = "border-l-red-500"
                elif item.warning_count > 0:
                    border_color = "border-l-amber-500"
                else:
                    border_color = "border-l-green-500"

                with ui.expansion(
                    f"{item.item_id}",
                    icon="error" if item.error_count > 0 else ("warning" if item.warning_count > 0 else "check_circle"),
                ).classes(f"w-full border-l-4 {border_color}").props(
                    "dense" + (" default-opened" if item.error_count > 0 else "")
                ):
                    ui.label(item.label).classes("text-xs text-slate-400 mb-2")

                    with ui.row().classes("w-full gap-8"):
                        with ui.column().classes("flex-1"):
                            ui.label("Predicted").classes("text-xs font-semibold text-slate-500")
                            for k, v in item.predicted.items():
                                with ui.row().classes("gap-2"):
                                    ui.label(k).classes("text-xs text-slate-500 font-mono w-20")
                                    match = item.reference.get(k)
                                    is_match = match is not None and v == match
                                    color = "text-green-400" if is_match else "text-white"
                                    ui.label(v).classes(f"text-xs font-mono {color}")

                        with ui.column().classes("flex-1"):
                            ui.label("Reference").classes("text-xs font-semibold text-slate-500")
                            for k, v in item.reference.items():
                                with ui.row().classes("gap-2"):
                                    ui.label(k).classes("text-xs text-slate-500 font-mono w-20")
                                    ui.label(v).classes("text-xs font-mono text-slate-300")

                    if item.issues:
                        ui.separator().classes("bg-slate-700 my-2")
                        for issue in item.issues:
                            if issue.severity == "error":
                                icon, color = "error", "text-red-400"
                            elif issue.severity == "warning":
                                icon, color = "warning", "text-amber-400"
                            else:
                                icon, color = "info", "text-blue-400"
                            with ui.row().classes("items-center gap-2"):
                                ui.icon(icon, size="xs").classes(color)
                                ui.label(f"[{issue.dimension}] {issue.message}").classes(f"text-xs font-mono {color}")


def launch(report: EvaluationReport, port: int = 8081, reload: bool = False, sample_plan: SamplePlan | None = None):
    @ui.page("/")
    def index():
        ValidatorApp(report, sample_plan=sample_plan).build()

    ui.run(
        title="LLM Classification Validator",
        port=port,
        reload=reload,
        show=True,
        dark=True,
        favicon="🔬",
    )
