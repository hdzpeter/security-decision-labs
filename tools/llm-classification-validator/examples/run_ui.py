"""Run the AICM-to-FAIR-CAM evaluation and display results in the validation UI."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

RESULTS_DIR = Path(__file__).parent.parent / "results"
REPORT_PATH = RESULTS_DIR / "report.json"
SAMPLE_PLAN_PATH = RESULTS_DIR / "sample_plan.json"

from llm_classification_validator.models import EvaluationReport
from llm_classification_validator.coherence.sampling import SamplePlan
from llm_classification_validator.ui import launch


def run_fresh():
    """Run the full evaluation and save results."""
    from examples.aicm_to_faircam import (
        CONTROLS,
        EXPERT_DOMAIN_MAPPINGS,
        map_control,
        run_coherence,
        run_consistency,
        run_convergent,
        run_adversarial,
        run_stability,
        _USE_LLM,
    )
    from llm_classification_validator.coherence.sampling import compute_sample_plan
    from llm_classification_validator.runner import run_evaluation
    from llm_classification_validator.models import ItemReport

    mode = "LLM (Claude)" if _USE_LLM else "keyword fallback"
    print(f"Classifier: {mode}\n")

    report = run_evaluation(
        foundation=[run_coherence, run_consistency, run_convergent],
        advanced=[run_adversarial, run_stability],
        parallel_advanced=True,
    )

    issues_by_id = {item.item_id: item.issues for item in report.items}

    report.items = []
    for i, ctrl in enumerate(CONTROLS):
        mapping = map_control(ctrl["description"])
        expert_domain = EXPERT_DOMAIN_MAPPINGS[i]
        issues = issues_by_id.get(ctrl["id"], [])

        report.items.append(ItemReport(
            item_id=ctrl["id"],
            label=ctrl["description"][:80] + ("..." if len(ctrl["description"]) > 80 else ""),
            predicted={"domain": mapping["domain"], **{k: v for k, v in mapping.items() if k != "domain"}},
            reference={"domain": expert_domain},
            issues=issues,
        ))

    sample_items = []
    for i, ctrl in enumerate(CONTROLS):
        mapping = map_control(ctrl["description"])
        sample_items.append({
            "id": ctrl["id"],
            "source_category": ctrl["id"].split("-")[0],
            "target_category": mapping["domain"],
        })
    sample_plan = compute_sample_plan(sample_items)

    report.save(REPORT_PATH)
    sample_plan.save(SAMPLE_PLAN_PATH)
    print(f"\nResults saved to {RESULTS_DIR}/")

    return report, sample_plan


def load_cached():
    """Load previously saved results."""
    report = EvaluationReport.load(REPORT_PATH)
    sample_plan = SamplePlan.load(SAMPLE_PLAN_PATH)
    print(f"Loaded cached results from {RESULTS_DIR}/")
    return report, sample_plan


if __name__ == "__main__":
    force = "--force" in sys.argv

    if not force and REPORT_PATH.exists() and SAMPLE_PLAN_PATH.exists():
        report, sample_plan = load_cached()
    else:
        report, sample_plan = run_fresh()

    print(f"Overall: {report.overall_verdict.value}")
    for dim in report.dimensions:
        print(f"  {dim.dimension}: {dim.verdict.value} ({len(dim.item_issues)} item issues)")
    print(f"  {len(report.items)} items")
    print(f"  Sample plan: {sample_plan.sample_size}/{sample_plan.total_items} items, "
          f"{'sufficient' if sample_plan.sufficient else 'INSUFFICIENT'}")
    if sample_plan.warnings:
        for w in sample_plan.warnings:
            print(f"    ! {w}")
    print("\nLaunching UI...")

    launch(report, sample_plan=sample_plan)
