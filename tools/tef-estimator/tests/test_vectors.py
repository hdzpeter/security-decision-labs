"""Tests for individual vector estimation engines."""

import pytest

from tef_estimator.data.common import (
    Geography,
    PERTRange,
    RemoteAccessType,
    RevenueBand,
    Sector,
)
from tef_estimator.data.scenarios.ransomware import RansomwareScenario
from tef_estimator.profile import OrganizationProfile
from tef_estimator.vectors.credential import CredentialVector
from tef_estimator.vectors.exploitation import ExploitationVector
from tef_estimator.vectors.phishing import PhishingVector
from tef_estimator.vectors.supply_chain import SupplyChainVector


@pytest.fixture
def scenario():
    return RansomwareScenario()


@pytest.fixture
def base_rate(scenario):
    return scenario.base_rate_triangulation["consensus"]


@pytest.fixture
def manufacturing_profile():
    return OrganizationProfile(
        sector=Sector.MANUFACTURING,
        revenue_band=RevenueBand.R_100M_1B,
        geography=Geography.US,
        remote_access=[RemoteAccessType.FORTINET],
        employee_count=2000,
    )


@pytest.fixture
def minimal_profile():
    return OrganizationProfile(
        sector=Sector.FINANCIAL,
        revenue_band=RevenueBand.R_10M_100M,
        geography=Geography.US,
    )


class TestExploitationVector:
    def test_produces_valid_estimate(self, manufacturing_profile, base_rate, scenario):
        vec = ExploitationVector()
        est = vec.estimate(manufacturing_profile, base_rate, scenario)
        assert est.positioned_median > 0
        assert est.positioned_low <= est.positioned_median <= est.positioned_high
        assert est.floor > 0
        assert est.vector_name == "Exploitation"

    def test_floor_respected(self, manufacturing_profile, base_rate, scenario):
        vec = ExploitationVector()
        est = vec.estimate(manufacturing_profile, base_rate, scenario)
        assert est.positioned_low >= est.floor

    def test_has_trace(self, manufacturing_profile, base_rate, scenario):
        vec = ExploitationVector()
        est = vec.estimate(manufacturing_profile, base_rate, scenario)
        assert est.trace is not None
        assert len(est.trace.steps) > 5

    def test_vpn_increases_estimate(self, base_rate, scenario):
        no_vpn = OrganizationProfile(
            sector=Sector.MANUFACTURING,
            revenue_band=RevenueBand.R_100M_1B,
            geography=Geography.US,
        )
        with_vpn = OrganizationProfile(
            sector=Sector.MANUFACTURING,
            revenue_band=RevenueBand.R_100M_1B,
            geography=Geography.US,
            remote_access=[RemoteAccessType.FORTINET],
        )
        vec = ExploitationVector()
        est_no = vec.estimate(no_vpn, base_rate, scenario)
        est_yes = vec.estimate(with_vpn, base_rate, scenario)
        assert est_yes.positioned_median > est_no.positioned_median


class TestCredentialVector:
    def test_produces_valid_estimate(self, manufacturing_profile, base_rate, scenario):
        vec = CredentialVector()
        est = vec.estimate(manufacturing_profile, base_rate, scenario)
        assert est.positioned_median > 0
        assert est.positioned_low <= est.positioned_median <= est.positioned_high
        assert est.vector_name == "Credential"

    def test_largest_proportion(self, manufacturing_profile, base_rate, scenario):
        """Credential should be the largest vector by proportion."""
        cred = CredentialVector().estimate(manufacturing_profile, base_rate, scenario)
        expl = ExploitationVector().estimate(manufacturing_profile, base_rate, scenario)
        phish = PhishingVector().estimate(manufacturing_profile, base_rate, scenario)
        sc = SupplyChainVector().estimate(manufacturing_profile, base_rate, scenario)
        assert cred.positioned_median > expl.positioned_median
        assert cred.positioned_median > phish.positioned_median
        assert cred.positioned_median > sc.positioned_median

    def test_has_trace(self, manufacturing_profile, base_rate, scenario):
        vec = CredentialVector()
        est = vec.estimate(manufacturing_profile, base_rate, scenario)
        assert est.trace is not None

    def test_no_remote_reduces(self, base_rate, scenario):
        with_vpn = OrganizationProfile(
            sector=Sector.MANUFACTURING,
            revenue_band=RevenueBand.R_100M_1B,
            geography=Geography.US,
            remote_access=[RemoteAccessType.FORTINET],
        )
        no_remote = OrganizationProfile(
            sector=Sector.MANUFACTURING,
            revenue_band=RevenueBand.R_100M_1B,
            geography=Geography.US,
            remote_access=[RemoteAccessType.NONE],
        )
        vec = CredentialVector()
        est_vpn = vec.estimate(with_vpn, base_rate, scenario)
        est_none = vec.estimate(no_remote, base_rate, scenario)
        assert est_none.positioned_median < est_vpn.positioned_median


class TestPhishingVector:
    def test_produces_valid_estimate(self, manufacturing_profile, base_rate, scenario):
        vec = PhishingVector()
        est = vec.estimate(manufacturing_profile, base_rate, scenario)
        assert est.positioned_median > 0
        assert est.vector_name == "Phishing"

    def test_large_email_footprint_increases(self, base_rate, scenario):
        small_co = OrganizationProfile(
            sector=Sector.MANUFACTURING,
            revenue_band=RevenueBand.R_100M_1B,
            geography=Geography.US,
            employee_count=30,
        )
        large_co = OrganizationProfile(
            sector=Sector.MANUFACTURING,
            revenue_band=RevenueBand.R_100M_1B,
            geography=Geography.US,
            employee_count=5000,
        )
        vec = PhishingVector()
        est_small = vec.estimate(small_co, base_rate, scenario)
        est_large = vec.estimate(large_co, base_rate, scenario)
        assert est_large.positioned_median > est_small.positioned_median

    def test_has_trace(self, manufacturing_profile, base_rate, scenario):
        vec = PhishingVector()
        est = vec.estimate(manufacturing_profile, base_rate, scenario)
        assert est.trace is not None


class TestSupplyChainVector:
    def test_produces_valid_estimate(self, manufacturing_profile, base_rate, scenario):
        vec = SupplyChainVector()
        est = vec.estimate(manufacturing_profile, base_rate, scenario)
        assert est.positioned_median > 0
        assert est.vector_name == "Supply Chain"

    def test_smallest_vector(self, manufacturing_profile, base_rate, scenario):
        """Supply chain should be the smallest vector."""
        sc = SupplyChainVector().estimate(manufacturing_profile, base_rate, scenario)
        expl = ExploitationVector().estimate(manufacturing_profile, base_rate, scenario)
        assert sc.positioned_median < expl.positioned_median

    def test_supply_chain_provider_increases(self, base_rate, scenario):
        base = OrganizationProfile(
            sector=Sector.MANUFACTURING,
            revenue_band=RevenueBand.R_100M_1B,
            geography=Geography.US,
        )
        provider = OrganizationProfile(
            sector=Sector.MANUFACTURING,
            revenue_band=RevenueBand.R_100M_1B,
            geography=Geography.US,
            supply_chain_provider=True,
        )
        vec = SupplyChainVector()
        est_base = vec.estimate(base, base_rate, scenario)
        est_provider = vec.estimate(provider, base_rate, scenario)
        assert est_provider.positioned_median > est_base.positioned_median

    def test_has_trace(self, manufacturing_profile, base_rate, scenario):
        vec = SupplyChainVector()
        est = vec.estimate(manufacturing_profile, base_rate, scenario)
        assert est.trace is not None
