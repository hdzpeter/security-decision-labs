"""Tests for coherence sampling module."""

import pytest

from llm_classification_validator.coherence.sampling import (
    SamplePlan,
    check_sample_sufficiency,
    compute_sample_plan,
)


def _make_items(
    n: int,
    source_cats: list[str] | None = None,
    target_cats: list[str] | None = None,
) -> list[dict]:
    """Helper: build item dicts with round-robin source/target categories."""
    items = []
    for i in range(n):
        d: dict = {"id": f"item_{i:03d}"}
        if source_cats:
            d["source_category"] = source_cats[i % len(source_cats)]
        if target_cats:
            d["target_category"] = target_cats[i % len(target_cats)]
        items.append(d)
    return items


# ── compute_sample_plan ─────────────────────────────────────────────


class TestBasicStratification:
    """Stratified sample covers every (source, target) stratum."""

    def test_all_strata_represented(self):
        items = _make_items(
            60,
            source_cats=["NIST", "ISO"],
            target_cats=["AC", "AU", "IA"],
        )
        plan = compute_sample_plan(items, min_per_stratum=3, min_total=20)

        # 2 source * 3 target = 6 strata
        assert len(plan.strata) == 6
        for key, count in plan.strata.items():
            assert count >= 3, f"Stratum {key} has only {count} items"

    def test_sample_ids_are_subset_of_population(self):
        items = _make_items(40, source_cats=["A"], target_cats=["X", "Y"])
        plan = compute_sample_plan(items)
        all_ids = {item["id"] for item in items}
        assert set(plan.sample_ids).issubset(all_ids)

    def test_sample_size_matches_ids(self):
        items = _make_items(50, source_cats=["S1", "S2"], target_cats=["T1"])
        plan = compute_sample_plan(items)
        assert plan.sample_size == len(plan.sample_ids)
        assert plan.total_items == 50

    def test_deterministic_with_same_seed(self):
        items = _make_items(80, source_cats=["A", "B"], target_cats=["X", "Y"])
        plan1 = compute_sample_plan(items, seed=99)
        plan2 = compute_sample_plan(items, seed=99)
        assert plan1.sample_ids == plan2.sample_ids

    def test_different_seed_gives_different_sample(self):
        items = _make_items(80, source_cats=["A", "B"], target_cats=["X", "Y"])
        plan1 = compute_sample_plan(items, seed=1)
        plan2 = compute_sample_plan(items, seed=2)
        # Highly unlikely to be identical with different seeds
        assert plan1.sample_ids != plan2.sample_ids


class TestMinimumTotal:
    """Top-up logic ensures the sample reaches min_total."""

    def test_reaches_min_total(self):
        # 6 strata * 3 = 18 from stratification, should top-up to 20
        items = _make_items(
            60,
            source_cats=["A", "B"],
            target_cats=["X", "Y", "Z"],
        )
        plan = compute_sample_plan(items, min_per_stratum=3, min_total=20)
        assert plan.sample_size >= 20

    def test_large_min_total_takes_more(self):
        items = _make_items(
            100,
            source_cats=["A", "B"],
            target_cats=["X"],
        )
        plan = compute_sample_plan(items, min_per_stratum=3, min_total=50)
        assert plan.sample_size >= 50


class TestSmallStrataWarnings:
    """Warns when a stratum has fewer items than min_per_stratum."""

    def test_warns_on_small_stratum(self):
        # Create 2 items in one stratum, plenty in others
        items = [
            {"id": "rare_0", "source_category": "RARE", "target_category": "T"},
            {"id": "rare_1", "source_category": "RARE", "target_category": "T"},
        ]
        items += _make_items(30, source_cats=["COMMON"], target_cats=["T"])
        plan = compute_sample_plan(items, min_per_stratum=3, min_total=10)

        stratum_warnings = [w for w in plan.warnings if "RARE" in w]
        assert len(stratum_warnings) >= 1
        assert "below minimum" in stratum_warnings[0].lower() or "only" in stratum_warnings[0].lower()

    def test_includes_all_items_from_small_stratum(self):
        items = [
            {"id": "tiny_0", "source_category": "X", "target_category": "Y"},
        ]
        items += _make_items(30, source_cats=["A"], target_cats=["B"])
        plan = compute_sample_plan(items, min_per_stratum=5, min_total=10)
        assert "tiny_0" in plan.sample_ids


class TestInsufficientSample:
    """sufficient=False when critical thresholds fail."""

    def test_insufficient_when_population_too_small_for_strata(self):
        # Exactly 2 items per stratum, min_per_stratum=3, and total < min_total
        items = _make_items(
            4,
            source_cats=["A", "B"],
            target_cats=["X"],
        )
        plan = compute_sample_plan(items, min_per_stratum=3, min_total=20)
        # Population is 4, which is less than 20, so we can't meet min_total
        # but the warning should flag it
        assert any("smaller than" in w.lower() or "below" in w.lower() for w in plan.warnings)

    def test_empty_input(self):
        plan = compute_sample_plan([])
        assert plan.sufficient is False
        assert plan.sample_size == 0


class TestMissingCategories:
    """Items without source_category or target_category land in _unknown."""

    def test_unknown_stratum(self):
        items = [
            {"id": "no_cats"},
            {"id": "partial", "source_category": "A"},
            {"id": "full", "source_category": "A", "target_category": "X"},
        ]
        plan = compute_sample_plan(items, min_per_stratum=1, min_total=1)
        # Should have strata containing "_unknown"
        unknown_strata = [k for k in plan.strata if "_unknown" in k]
        assert len(unknown_strata) >= 1


# ── check_sample_sufficiency ────────────────────────────────────────


class TestCheckSufficiency:
    """Validate an existing sample against stratification requirements."""

    def test_good_sample_is_sufficient(self):
        items = _make_items(60, source_cats=["A", "B"], target_cats=["X", "Y"])
        plan = compute_sample_plan(items, min_per_stratum=3, min_total=20)

        warnings, sufficient = check_sample_sufficiency(
            plan.sample_ids, items, min_per_stratum=3, min_total=20
        )
        assert sufficient is True
        assert len(warnings) == 0

    def test_uncovered_stratum_detected(self):
        items = _make_items(40, source_cats=["A", "B"], target_cats=["X", "Y"])
        # Take a sample that deliberately misses stratum (B, Y)
        sample = [
            it["id"] for it in items
            if not (it.get("source_category") == "B" and it.get("target_category") == "Y")
        ][:25]

        warnings, sufficient = check_sample_sufficiency(
            sample, items, min_per_stratum=3, min_total=20
        )
        # Should flag at least the missing stratum
        assert sufficient is False
        assert any("not covered" in w for w in warnings)

    def test_underrepresented_stratum_detected(self):
        items = _make_items(60, source_cats=["A", "B"], target_cats=["X", "Y"])
        # Build sample with only 1 item from stratum (B, Y), rest well-covered
        by_items = [it for it in items if it.get("source_category") == "B" and it.get("target_category") == "Y"]
        other_items = [it for it in items if not (it.get("source_category") == "B" and it.get("target_category") == "Y")]
        sample = [by_items[0]["id"]] + [it["id"] for it in other_items[:24]]

        warnings, sufficient = check_sample_sufficiency(
            sample, items, min_per_stratum=3, min_total=20
        )
        assert sufficient is False
        assert any("underrepresented" in w for w in warnings)

    def test_below_min_total_detected(self):
        items = _make_items(60, source_cats=["A"], target_cats=["X"])
        sample = [items[0]["id"], items[1]["id"]]

        warnings, sufficient = check_sample_sufficiency(
            sample, items, min_per_stratum=1, min_total=20
        )
        assert sufficient is False
        assert any("below minimum" in w for w in warnings)

    def test_empty_population(self):
        warnings, sufficient = check_sample_sufficiency(["x"], [])
        assert sufficient is False

    def test_small_population_all_sampled(self):
        """When population < min_total and all items are sampled, no complaint about total."""
        items = _make_items(5, source_cats=["A"], target_cats=["X"])
        sample = [it["id"] for it in items]
        warnings, sufficient = check_sample_sufficiency(
            sample, items, min_per_stratum=3, min_total=20
        )
        # Population is smaller than min_total, so the total check
        # should not fire (can't sample more than exists)
        total_warnings = [w for w in warnings if "below minimum" in w.lower()]
        assert len(total_warnings) == 0


# ── SamplePlan dataclass ───────────────────────────────────────────


class TestSamplePlanDataclass:
    def test_defaults(self):
        sp = SamplePlan(
            sample_ids=["a"], total_items=10, sample_size=1, strata={"x": 1}
        )
        assert sp.warnings == []
        assert sp.sufficient is True
