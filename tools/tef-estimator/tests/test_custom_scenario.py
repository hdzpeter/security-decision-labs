"""Tests for custom scenario builder."""

import json
import pytest
from pathlib import Path

from tef_estimator.data.common import (
    Geography,
    PERTRange,
    RemoteAccessType,
    RevenueBand,
    Sector,
)
from tef_estimator.data.scenarios.base import ScenarioDefinition
from tef_estimator.data.scenarios.custom import (
    CustomScenario,
    generate_template,
    load_custom_scenario,
)
from tef_estimator.engine import TEFEngine
from tef_estimator.profile import OrganizationProfile


VALID_SCENARIO = {
    "scenario_name": "Data Exfiltration",
    "scenario_slug": "data_exfil",
    "vector_proportions": {
        "exploitation": [0.10, 0.20, 0.30],
        "credential": [0.30, 0.40, 0.50],
        "phishing": [0.15, 0.25, 0.35],
        "supply_chain": [0.05, 0.15, 0.20],
    },
    "base_rate": {
        "consensus": [0.005, 0.015, 0.04],
    },
    "overall_share": 0.10,
}


def _write_scenario(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(data))
    return path


class TestCustomScenarioValidation:
    def test_valid_scenario(self, tmp_path):
        path = _write_scenario(tmp_path, VALID_SCENARIO)
        s = load_custom_scenario(path)
        assert s.scenario_name == "Data Exfiltration"
        assert s.scenario_slug == "data_exfil"

    def test_missing_required_field(self, tmp_path):
        bad = dict(VALID_SCENARIO)
        del bad["vector_proportions"]
        path = _write_scenario(tmp_path, bad)
        with pytest.raises(ValueError, match="missing required"):
            load_custom_scenario(path)

    def test_unknown_vector(self, tmp_path):
        bad = dict(VALID_SCENARIO)
        bad["vector_proportions"] = dict(VALID_SCENARIO["vector_proportions"])
        bad["vector_proportions"]["insider"] = [0.1, 0.2, 0.3]
        path = _write_scenario(tmp_path, bad)
        with pytest.raises(ValueError, match="Unknown vectors"):
            load_custom_scenario(path)

    def test_proportions_dont_sum(self, tmp_path):
        bad = dict(VALID_SCENARIO)
        bad["vector_proportions"] = {
            "exploitation": [0.5, 0.6, 0.7],
            "credential": [0.5, 0.6, 0.7],
        }
        path = _write_scenario(tmp_path, bad)
        with pytest.raises(ValueError, match="sum to"):
            load_custom_scenario(path)

    def test_missing_consensus(self, tmp_path):
        bad = dict(VALID_SCENARIO)
        bad["base_rate"] = {"anchor_1": [0.01, 0.02, 0.03]}
        path = _write_scenario(tmp_path, bad)
        with pytest.raises(ValueError, match="consensus"):
            load_custom_scenario(path)


class TestCustomScenarioProtocol:
    @pytest.fixture
    def scenario(self, tmp_path):
        path = _write_scenario(tmp_path, VALID_SCENARIO)
        return load_custom_scenario(path)

    def test_implements_protocol(self, scenario):
        assert isinstance(scenario, ScenarioDefinition)

    def test_vector_proportions(self, scenario):
        vp = scenario.vector_proportions
        assert "exploitation" in vp
        assert "credential" in vp
        assert isinstance(vp["exploitation"], PERTRange)
        assert vp["exploitation"].mode == pytest.approx(0.20)

    def test_base_rate_triangulation(self, scenario):
        br = scenario.base_rate_triangulation
        assert "consensus" in br
        assert br["consensus"].mode == pytest.approx(0.015)

    def test_active_vectors(self, scenario):
        assert set(scenario.active_vectors) == {
            "exploitation", "credential", "phishing", "supply_chain"
        }

    def test_defaults_for_optional_fields(self, scenario):
        assert len(scenario.credential_tempo) > 0
        assert len(scenario.exploitation_scanning) > 0
        assert scenario.output_templates["scenario_label"] == "Data Exfiltration"

    def test_sector_shares_default_to_none(self, scenario):
        shares = scenario.sector_shares
        for sector in Sector:
            assert shares[sector] is None

    def test_revenue_shares_default_to_overall(self, scenario):
        shares = scenario.revenue_shares
        for band in RevenueBand:
            assert shares[band] == scenario.overall_share

    def test_adjusted_sector_multiplier(self, scenario):
        m = scenario.adjusted_sector_multiplier(Sector.MANUFACTURING)
        assert m > 0

    def test_adjusted_revenue_multiplier(self, scenario):
        m = scenario.adjusted_revenue_multiplier(RevenueBand.R_100M_1B)
        assert m > 0


class TestCustomScenarioWithOptionalFields:
    def test_with_sector_shares(self, tmp_path):
        data = dict(VALID_SCENARIO)
        data["sector_shares"] = {"manufacturing": 0.15, "financial": 0.20}
        path = _write_scenario(tmp_path, data)
        s = load_custom_scenario(path)

        assert s.sector_shares[Sector.MANUFACTURING] == 0.15
        assert s.sector_shares[Sector.FINANCIAL] == 0.20
        assert s.sector_shares[Sector.EDUCATION] is None

    def test_with_revenue_shares(self, tmp_path):
        data = dict(VALID_SCENARIO)
        data["revenue_shares"] = {"100m_1b": 0.12, "1b_10b": 0.15}
        path = _write_scenario(tmp_path, data)
        s = load_custom_scenario(path)

        assert s.revenue_shares[RevenueBand.R_100M_1B] == 0.12
        assert s.revenue_shares[RevenueBand.UNDER_10M] == 0.10  # falls back to overall_share

    def test_with_additional_anchors(self, tmp_path):
        data = dict(VALID_SCENARIO)
        data["base_rate"] = {
            "anchor_1": [0.01, 0.02, 0.03],
            "anchor_2": [0.005, 0.015, 0.05],
            "consensus": [0.005, 0.015, 0.04],
        }
        path = _write_scenario(tmp_path, data)
        s = load_custom_scenario(path)

        br = s.base_rate_triangulation
        assert len(br) == 3


class TestCustomScenarioEngine:
    def test_engine_runs_with_custom_scenario(self, tmp_path):
        path = _write_scenario(tmp_path, VALID_SCENARIO)
        scenario = load_custom_scenario(path)

        engine = TEFEngine(scenario=scenario)
        profile = OrganizationProfile(
            sector=Sector.MANUFACTURING,
            revenue_band=RevenueBand.R_100M_1B,
            geography=Geography.US,
        )
        result = engine.estimate(profile)

        assert result.total_positioned_median > 0
        assert result.scenario_name == "Data Exfiltration"
        assert len(result.vectors) == 4

    def test_compare_with_custom_scenario(self, tmp_path):
        path = _write_scenario(tmp_path, VALID_SCENARIO)
        scenario = load_custom_scenario(path)

        engine = TEFEngine(scenario=scenario)
        a = OrganizationProfile(
            sector=Sector.MANUFACTURING,
            revenue_band=RevenueBand.R_100M_1B,
            geography=Geography.US,
            remote_access=[RemoteAccessType.FORTINET],
        )
        b = OrganizationProfile(
            sector=Sector.MANUFACTURING,
            revenue_band=RevenueBand.R_100M_1B,
            geography=Geography.US,
        )
        diff = engine.compare(a, b)
        assert diff.total_delta != 0

    def test_sensitivity_with_custom_scenario(self, tmp_path):
        path = _write_scenario(tmp_path, VALID_SCENARIO)
        scenario = load_custom_scenario(path)

        engine = TEFEngine(scenario=scenario)
        profile = OrganizationProfile(
            sector=Sector.FINANCIAL,
            revenue_band=RevenueBand.R_1B_10B,
            geography=Geography.US,
        )
        result = engine.sensitivity(profile)
        assert result.baseline_median > 0
        assert len(result.entries) >= 2


class TestTemplate:
    def test_generate_template(self, tmp_path):
        path = tmp_path / "template.json"
        generate_template(path)
        assert path.exists()

        with open(path) as f:
            data = json.load(f)

        assert "scenario_name" in data
        assert "vector_proportions" in data
        assert "base_rate" in data

    def test_template_is_valid(self, tmp_path):
        path = tmp_path / "template.json"
        generate_template(path)
        s = load_custom_scenario(path)
        assert s.scenario_name == "My Custom Scenario"

    def test_template_runs_in_engine(self, tmp_path):
        path = tmp_path / "template.json"
        generate_template(path)
        scenario = load_custom_scenario(path)

        engine = TEFEngine(scenario=scenario)
        profile = OrganizationProfile(
            sector=Sector.INFORMATION,
            revenue_band=RevenueBand.R_10M_100M,
            geography=Geography.US,
        )
        result = engine.estimate(profile)
        assert result.total_positioned_median > 0
