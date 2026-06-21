"""Integration tests for the TEF estimation engine."""

import pytest

from tef_estimator.data.common import (
    Geography,
    PERTRange,
    RemoteAccessType,
    RevenueBand,
    Sector,
    DampeningConfig,
)
from tef_estimator.data.scenarios.ransomware import RansomwareScenario
from tef_estimator.engine import TEFEngine
from tef_estimator.profile import OrganizationProfile


@pytest.fixture
def engine():
    return TEFEngine()


def _make_profile(**overrides):
    defaults = dict(
        sector=Sector.MANUFACTURING,
        revenue_band=RevenueBand.R_100M_1B,
        geography=Geography.US,
        remote_access=[RemoteAccessType.FORTINET],
        employee_count=2000,
    )
    defaults.update(overrides)
    return OrganizationProfile(**defaults)


class TestEstimate:
    def test_high_risk_manufacturing(self, engine):
        profile = _make_profile()
        result = engine.estimate(profile)
        assert result.total_positioned_median > 0
        assert result.total_positioned_low <= result.total_positioned_median
        assert result.total_positioned_median <= result.total_positioned_high
        # Manufacturing with VPN should be in ~1-5% range
        assert 0.005 < result.total_positioned_median < 0.10

    def test_low_risk_financial(self, engine):
        profile = _make_profile(
            sector=Sector.FINANCIAL,
            remote_access=[RemoteAccessType.NONE],
            employee_count=50,
        )
        result = engine.estimate(profile)
        # Financial with no VPN should be lower than manufacturing with VPN
        mfg_result = engine.estimate(_make_profile())
        assert result.total_positioned_median < mfg_result.total_positioned_median

    def test_minimal_input(self, engine):
        """Engine works with just sector, revenue, geography."""
        profile = OrganizationProfile(
            sector=Sector.EDUCATION,
            revenue_band=RevenueBand.R_10M_100M,
            geography=Geography.WESTERN_EUROPE,
        )
        result = engine.estimate(profile)
        assert result.total_positioned_median > 0

    def test_custom_base_rate(self):
        engine = TEFEngine()
        profile = _make_profile(custom_base_rate=0.05)
        result = engine.estimate(profile)
        # Higher base rate -> higher estimate
        default_result = engine.estimate(_make_profile())
        assert result.total_positioned_median > default_result.total_positioned_median

    def test_four_vectors_present(self, engine):
        profile = _make_profile()
        result = engine.estimate(profile)
        assert len(result.vectors) == 4
        names = {v.vector_name for v in result.vectors}
        assert names == {"Exploitation", "Credential", "Phishing", "Supply Chain"}

    def test_floor_enforced(self, engine):
        profile = _make_profile()
        result = engine.estimate(profile)
        assert result.total_positioned_median >= result.total_floor

    def test_validation_checks_present(self, engine):
        profile = _make_profile()
        result = engine.estimate(profile)
        assert len(result.validation_checks) > 0

    def test_lognormal_params(self, engine):
        profile = _make_profile()
        result = engine.estimate(profile)
        assert result.lognormal.mu < 0  # TEF < 1, so ln(TEF) < 0
        assert result.lognormal.sigma > 0
        assert result.lognormal.p5 < result.lognormal.median < result.lognormal.p95

    def test_scenario_name(self, engine):
        profile = _make_profile()
        result = engine.estimate(profile)
        assert result.scenario_name == "Ransomware"


class TestCompare:
    def test_same_profile_no_delta(self, engine):
        profile = _make_profile()
        diff = engine.compare(profile, profile)
        assert abs(diff.total_delta) < 1e-10

    def test_vpn_removal_reduces(self, engine):
        with_vpn = _make_profile(remote_access=[RemoteAccessType.FORTINET])
        no_vpn = _make_profile(remote_access=[RemoteAccessType.NONE])
        diff = engine.compare(with_vpn, no_vpn)
        assert diff.total_delta < 0  # Removing VPN should reduce TEF

    def test_to_dict(self, engine):
        a = _make_profile()
        b = _make_profile(sector=Sector.EDUCATION)
        diff = engine.compare(a, b)
        d = diff.to_dict()
        assert "vector_deltas" in d
        assert "total_delta" in d
        assert "explanation" in d


class TestSensitivity:
    def test_base_rate_dominates(self, engine):
        profile = _make_profile()
        sens = engine.sensitivity(profile)
        assert len(sens.entries) >= 3
        # Base rate should be the first (highest range)
        assert sens.entries[0].parameter == "base_rate"
        assert sens.entries[0].range_multiple > 1.0

    def test_tornado_data(self, engine):
        profile = _make_profile()
        sens = engine.sensitivity(profile)
        data = sens.tornado_data
        assert len(data) >= 3
        for entry in data:
            assert "parameter" in entry
            assert "low" in entry
            assert "high" in entry
            assert entry["low"] <= entry["high"]


class TestThreeTierOutput:
    def test_summary_tier(self, engine):
        result = engine.estimate(_make_profile())
        s = result.summary
        assert s.positioned_median > 0
        assert s.recurrence_years > 0
        assert len(s.vector_bar) == 4
        assert s.one_sentence

    def test_analysis_tier(self, engine):
        result = engine.estimate(_make_profile())
        a = result.analysis
        assert a.lognormal is not None
        assert len(a.vectors) == 4

    def test_audit_tier(self, engine):
        result = engine.estimate(_make_profile())
        au = result.audit
        assert len(au.traces) == 4
        assert len(au.data_sources) > 0
        assert au.scenario_name == "Ransomware"

    def test_to_dict(self, engine):
        result = engine.estimate(_make_profile())
        d = result.to_dict()
        assert "summary" in d
        assert "analysis" in d
        assert "audit" in d
        assert d["scenario"] == "ransomware"

    def test_brief_report(self, engine):
        result = engine.estimate(_make_profile())
        text = result.brief_report()
        assert "TEF ESTIMATE" in text
        assert "VECTOR BREAKDOWN" in text

    def test_full_report(self, engine):
        result = engine.estimate(_make_profile())
        text = result.full_report()
        assert "THREAT EVENT FREQUENCY ESTIMATE" in text
        assert "CALCULATION TRACES" in text
        assert "DATA SOURCES" in text
        assert "BASE RATE DERIVATION" in text

    def test_to_markdown(self, engine):
        result = engine.estimate(_make_profile())
        md = result.to_markdown()
        assert md.startswith("# Ransomware TEF Estimate")
        assert "## Vector Breakdown" in md
        assert "## Distribution Parameters" in md
        assert "## Calculation Traces" in md
        assert "## Data Sources" in md
        assert "## Base Rate Derivation" in md
