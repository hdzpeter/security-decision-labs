"""Tests for data layer: sector/revenue population, multiplier sanity."""

import pytest

from tef_estimator.data.common import (
    FLOOR_ANCHORS,
    GEO_MULTIPLIERS,
    PROFILE_MULTIPLIERS,
    REVENUE_BAND_DATA,
    SECTOR_DATA,
    TECH_MULTIPLIERS,
    DampeningConfig,
    Geography,
    PERTRange,
    RemoteAccessType,
    RevenueBand,
    Sector,
)
from tef_estimator.data.scenarios.ransomware import RansomwareScenario


class TestSectorData:
    def test_all_sectors_populated(self):
        for sector in Sector:
            assert sector in SECTOR_DATA, f"Missing sector: {sector}"

    def test_multipliers_positive(self):
        for sector, data in SECTOR_DATA.items():
            assert data.all_incident_multiplier > 0, f"{sector} has non-positive multiplier"

    def test_event_counts_nonnegative(self):
        for sector, data in SECTOR_DATA.items():
            if data.event_count_2019_2023 is not None:
                assert data.event_count_2019_2023 >= 0, f"{sector} has negative event count"


class TestRevenueBandData:
    def test_all_bands_populated(self):
        for band in RevenueBand:
            assert band in REVENUE_BAND_DATA, f"Missing band: {band}"

    def test_multipliers_positive(self):
        for band, data in REVENUE_BAND_DATA.items():
            assert data.all_incident_multiplier > 0


class TestFloorAnchors:
    def test_floor_keys_exist(self):
        assert "overall_lower_bound" in FLOOR_ANCHORS
        assert "overall_upper_bound" in FLOOR_ANCHORS

    def test_floor_ordering(self):
        assert FLOOR_ANCHORS["overall_lower_bound"] < FLOOR_ANCHORS["overall_upper_bound"]

    def test_floor_positive(self):
        assert FLOOR_ANCHORS["overall_lower_bound"] > 0


class TestGeoMultipliers:
    def test_all_geos_populated(self):
        for geo in Geography:
            assert geo in GEO_MULTIPLIERS, f"Missing geo: {geo}"

    def test_us_is_elevated(self):
        """US has higher disclosure rates -> higher observed rate."""
        us_mult = GEO_MULTIPLIERS[Geography.US]
        assert us_mult.mode >= 1.0


class TestTechMultipliers:
    def test_key_techs_exist(self):
        for key in ["vpn_vulnerable_vendor", "rdp_exposed", "no_remote_access"]:
            assert key in TECH_MULTIPLIERS, f"Missing tech: {key}"

    def test_vpn_above_one(self):
        vpn = TECH_MULTIPLIERS["vpn_vulnerable_vendor"]
        assert vpn.mode > 1.0

    def test_no_remote_below_one(self):
        no_remote = TECH_MULTIPLIERS["no_remote_access"]
        assert no_remote.mode < 1.0


class TestDampeningConfig:
    def test_defaults(self):
        d = DampeningConfig()
        assert 0 < d.factor_k < 1
        assert 0 < d.vector_k < 1
        assert d.max_composite > 1

    def test_values_loaded_from_json(self):
        d = DampeningConfig()
        assert d.factor_k == 0.70
        assert d.vector_k == 0.85
        assert d.max_composite == 5.0

    def test_source_citations_not_empty(self):
        d = DampeningConfig()
        assert d.factor_k_source, "factor_k_source should have a citation"
        assert d.vector_k_source, "vector_k_source should have a citation"
        assert d.max_composite_source, "max_composite_source should have a citation"

    def test_vector_k_has_veris_citation(self):
        d = DampeningConfig()
        assert "VERIS" in d.vector_k_source

    def test_veris_pairwise_lifts_in_json(self):
        """VERIS pairwise lift data should be present in extracted.json."""
        from tef_estimator.data.loader import load_reference
        common = load_reference("common")
        lifts = common["dampening_config"]["veris_pairwise_lifts"]
        assert "credential_x_phishing" in lifts
        assert lifts["credential_x_phishing"]["lift"] > 1.0
        assert lifts["exploitation_x_credential"]["lift"] < 1.0


class TestRansomwareScenario:
    def setup_method(self):
        self.scenario = RansomwareScenario()

    def test_vector_proportions_sum_near_one(self):
        """Mode proportions should sum close to 1 (within ~5% for rounding)."""
        total = sum(v.mode for v in self.scenario.vector_proportions.values())
        assert 0.90 <= total <= 1.10, f"Vector proportions sum to {total}"

    def test_active_vectors(self):
        assert set(self.scenario.active_vectors) == {
            "exploitation", "credential", "phishing", "supply_chain"
        }

    def test_base_rate_consensus_exists(self):
        assert "consensus" in self.scenario.base_rate_triangulation

    def test_base_rate_ordering(self):
        consensus = self.scenario.base_rate_triangulation["consensus"]
        assert consensus.low < consensus.mode < consensus.high

    def test_adjusted_sector_multiplier_positive(self):
        for sector in Sector:
            mult = self.scenario.adjusted_sector_multiplier(sector)
            assert mult > 0, f"Non-positive multiplier for {sector}"

    def test_manufacturing_elevated(self):
        """Manufacturing should have above-average ransomware multiplier."""
        mult = self.scenario.adjusted_sector_multiplier(Sector.MANUFACTURING)
        assert mult > 1.0

    def test_financial_below_average(self):
        """Financial should be below average for ransomware."""
        mult = self.scenario.adjusted_sector_multiplier(Sector.FINANCIAL)
        assert mult < 1.0

    def test_adjusted_revenue_multiplier_positive(self):
        for band in RevenueBand:
            mult = self.scenario.adjusted_revenue_multiplier(band)
            assert mult > 0

