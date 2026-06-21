"""Tests for scenario definitions and isolation."""

from tef_estimator.data.common import PERTRange, RevenueBand, Sector
from tef_estimator.data.scenarios.bec import BECScenario
from tef_estimator.data.scenarios.ransomware import RansomwareScenario


class TestRansomwareScenario:
    def setup_method(self):
        self.scenario = RansomwareScenario()

    def test_scenario_name(self):
        assert self.scenario.scenario_name == "Ransomware"
        assert self.scenario.scenario_slug == "ransomware"

    def test_vector_proportions_are_pert(self):
        for name, pert in self.scenario.vector_proportions.items():
            assert isinstance(pert, PERTRange)
            assert pert.low < pert.mode < pert.high

    def test_overall_share(self):
        share = self.scenario.overall_share
        assert 0 < share < 1

    def test_sector_shares_bounded(self):
        for sector, share in self.scenario.sector_shares.items():
            if share is not None:
                assert 0 < share <= 1.0, f"{sector} share out of range: {share}"

    def test_revenue_shares_bounded(self):
        for band, share in self.scenario.revenue_shares.items():
            assert 0 < share <= 1.0

    def test_credential_tempo(self):
        tempo = self.scenario.credential_tempo
        assert "global_campaigns_per_month" in tempo
        assert "credential_proportion" in tempo
        assert "addressable_population" in tempo

    def test_adjusted_multiplier_composition(self):
        """Verify: adjusted = common_mult * (sector_share / overall_share)."""
        from tef_estimator.data.common import SECTOR_DATA
        sector = Sector.MANUFACTURING
        common_mult = SECTOR_DATA[sector].all_incident_multiplier
        share = self.scenario.sector_shares.get(sector)
        expected = common_mult * (share / self.scenario.overall_share)
        actual = self.scenario.adjusted_sector_multiplier(sector)
        assert abs(actual - expected) < 1e-6

    def test_adjusted_multiplier_range_returns_pert(self):
        r = self.scenario.adjusted_sector_multiplier_range(Sector.MANUFACTURING)
        assert isinstance(r, PERTRange)
        assert r.low < r.mode < r.high

    def test_adjusted_revenue_range_returns_pert(self):
        r = self.scenario.adjusted_revenue_multiplier_range(RevenueBand.R_100M_1B)
        assert isinstance(r, PERTRange)
        assert r.low < r.mode < r.high

    def test_base_rate_triangulation_complete(self):
        tri = self.scenario.base_rate_triangulation
        expected_keys = {"operational_tempo", "iris_back_calculation",
                         "coalition_market_adjusted", "consensus"}
        assert expected_keys <= set(tri.keys())

    def test_exploitation_scanning(self):
        scanning = self.scenario.exploitation_scanning
        assert "grn_malicious_rate" in scanning
        assert "poa_ransomware" in scanning


class TestBECScenario:
    def setup_method(self):
        self.scenario = BECScenario()

    def test_scenario_name(self):
        assert self.scenario.scenario_name == "Business Email Compromise"
        assert self.scenario.scenario_slug == "bec"

    def test_vector_proportions_are_pert(self):
        for name, pert in self.scenario.vector_proportions.items():
            assert isinstance(pert, PERTRange)
            assert pert.low < pert.mode < pert.high

    def test_phishing_is_dominant_vector(self):
        props = self.scenario.vector_proportions
        assert props["phishing"].mode > props["credential"].mode
        assert props["phishing"].mode > props["exploitation"].mode
        assert props["phishing"].mode > props["supply_chain"].mode

    def test_exploitation_is_minimal(self):
        assert self.scenario.vector_proportions["exploitation"].mode < 0.10

    def test_overall_share(self):
        share = self.scenario.overall_share
        assert 0 < share < 1

    def test_base_rate_higher_than_ransomware(self):
        rw = RansomwareScenario()
        bec_consensus = self.scenario.base_rate_triangulation["consensus"]
        rw_consensus = rw.base_rate_triangulation["consensus"]
        assert bec_consensus.mode > rw_consensus.mode

    def test_credential_tempo(self):
        tempo = self.scenario.credential_tempo
        assert "global_campaigns_per_month" in tempo
        assert "credential_proportion" in tempo

    def test_adjusted_multiplier_composition(self):
        from tef_estimator.data.common import SECTOR_DATA
        sector = Sector.FINANCIAL
        common_mult = SECTOR_DATA[sector].all_incident_multiplier
        share = self.scenario.sector_shares.get(sector)
        expected = common_mult * (share / self.scenario.overall_share)
        actual = self.scenario.adjusted_sector_multiplier(sector)
        assert abs(actual - expected) < 1e-6

    def test_financial_sector_highly_targeted(self):
        fin_mult = self.scenario.adjusted_sector_multiplier(Sector.FINANCIAL)
        mfg_mult = self.scenario.adjusted_sector_multiplier(Sector.MANUFACTURING)
        assert fin_mult > mfg_mult


class TestBECEstimation:
    def test_bec_produces_result(self):
        from tef_estimator.engine import TEFEngine
        from tef_estimator.profile import OrganizationProfile
        from tef_estimator.data.common import Geography, RemoteAccessType

        profile = OrganizationProfile(
            sector=Sector.FINANCIAL,
            revenue_band=RevenueBand.R_100M_1B,
            geography=Geography.US,
            remote_access=[RemoteAccessType.NONE],
        )
        engine = TEFEngine(scenario=BECScenario())
        result = engine.estimate(profile)
        assert result.total_positioned_median > 0
        assert result.scenario_name == "Business Email Compromise"
        assert len(result.vectors) == 4

    def test_bec_phishing_dominant_in_output(self):
        from tef_estimator.engine import TEFEngine
        from tef_estimator.profile import OrganizationProfile
        from tef_estimator.data.common import Geography, RemoteAccessType

        profile = OrganizationProfile(
            sector=Sector.FINANCIAL,
            revenue_band=RevenueBand.R_100M_1B,
            geography=Geography.US,
            remote_access=[RemoteAccessType.NONE],
        )
        engine = TEFEngine(scenario=BECScenario())
        result = engine.estimate(profile)
        phishing_v = [v for v in result.vectors if v.vector_name == "Phishing"][0]
        assert phishing_v.positioned_median == max(v.positioned_median for v in result.vectors)

    def test_bec_tef_higher_than_ransomware(self):
        from tef_estimator.engine import TEFEngine
        from tef_estimator.profile import OrganizationProfile
        from tef_estimator.data.common import Geography, RemoteAccessType

        profile = OrganizationProfile(
            sector=Sector.FINANCIAL,
            revenue_band=RevenueBand.R_100M_1B,
            geography=Geography.US,
            remote_access=[RemoteAccessType.NONE],
        )
        bec_result = TEFEngine(scenario=BECScenario()).estimate(profile)
        rw_result = TEFEngine(scenario=RansomwareScenario()).estimate(profile)
        assert bec_result.total_positioned_median > rw_result.total_positioned_median

    def test_vector_shares_sum_to_one(self):
        from tef_estimator.engine import TEFEngine
        from tef_estimator.profile import OrganizationProfile
        from tef_estimator.data.common import Geography, RemoteAccessType

        profile = OrganizationProfile(
            sector=Sector.FINANCIAL,
            revenue_band=RevenueBand.R_100M_1B,
            geography=Geography.US,
            remote_access=[RemoteAccessType.NONE],
        )
        result = TEFEngine(scenario=BECScenario()).estimate(profile)
        shares = result.summary.vector_bar
        total_share = sum(d["share"] for d in shares)
        assert abs(total_share - 1.0) < 0.01
