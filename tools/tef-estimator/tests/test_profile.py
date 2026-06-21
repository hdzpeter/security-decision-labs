"""Tests for OrganizationProfile and its derived properties."""

from tef_estimator.data.common import (
    Geography,
    RemoteAccessType,
    RevenueBand,
    Sector,
)
from tef_estimator.profile import OrganizationProfile


def _make_profile(**overrides):
    defaults = dict(
        sector=Sector.MANUFACTURING,
        revenue_band=RevenueBand.R_100M_1B,
        geography=Geography.US,
    )
    defaults.update(overrides)
    return OrganizationProfile(**defaults)


class TestVPNDetection:
    def test_fortinet_is_vpn(self):
        p = _make_profile(remote_access=[RemoteAccessType.FORTINET])
        assert p.has_vpn is True

    def test_rdp_is_not_vpn(self):
        p = _make_profile(remote_access=[RemoteAccessType.RDP])
        assert p.has_vpn is False
        assert p.has_rdp is True

    def test_none_is_no_remote(self):
        p = _make_profile(remote_access=[RemoteAccessType.NONE])
        assert p.has_no_remote_access is True
        assert p.has_vpn is False
        assert p.has_rdp is False

    def test_vulnerable_vendor(self):
        for vendor in [RemoteAccessType.FORTINET, RemoteAccessType.CISCO,
                       RemoteAccessType.PALO_ALTO, RemoteAccessType.SONICWALL]:
            p = _make_profile(remote_access=[vendor])
            assert p.has_vulnerable_vpn_vendor is True

    def test_other_vpn_not_vulnerable(self):
        p = _make_profile(remote_access=[RemoteAccessType.OTHER_VPN])
        assert p.has_vpn is True
        assert p.has_vulnerable_vpn_vendor is False


class TestEmployeeBands:
    def test_unknown(self):
        p = _make_profile()
        assert p.employee_band_label == "unknown"

    def test_small(self):
        p = _make_profile(employee_count=25)
        assert p.employee_band_label == "<50"

    def test_mid(self):
        p = _make_profile(employee_count=200)
        assert p.employee_band_label == "50–500"

    def test_large(self):
        p = _make_profile(employee_count=2000)
        assert p.employee_band_label == "500–5,000"

    def test_large_email_footprint(self):
        p = _make_profile(employee_count=5000)
        assert p.has_large_email_footprint is True

    def test_small_no_large_email(self):
        p = _make_profile(employee_count=100)
        assert p.has_large_email_footprint is False


class TestCloudPrimary:
    def test_no_remote_no_edge_is_cloud(self):
        p = _make_profile(
            remote_access=[RemoteAccessType.NONE],
            edge_vendors=[],
        )
        assert p.is_cloud_primary is True

    def test_vpn_is_not_cloud(self):
        p = _make_profile(remote_access=[RemoteAccessType.FORTINET])
        assert p.is_cloud_primary is False


class TestValidation:
    def test_negative_employee_count_raises(self):
        import pytest
        with pytest.raises(ValueError, match="non-negative"):
            _make_profile(employee_count=-1)

    def test_absurd_employee_count_raises(self):
        import pytest
        with pytest.raises(ValueError, match="exceeds 10M"):
            _make_profile(employee_count=99_000_000)

    def test_base_rate_zero_raises(self):
        import pytest
        with pytest.raises(ValueError, match="between 0 and 1"):
            _make_profile(custom_base_rate=0.0)

    def test_base_rate_negative_raises(self):
        import pytest
        with pytest.raises(ValueError, match="between 0 and 1"):
            _make_profile(custom_base_rate=-0.5)

    def test_base_rate_over_one_raises(self):
        import pytest
        with pytest.raises(ValueError, match="between 0 and 1"):
            _make_profile(custom_base_rate=1.5)

    def test_valid_base_rate_accepted(self):
        p = _make_profile(custom_base_rate=0.02)
        assert p.custom_base_rate == 0.02

    def test_valid_employee_count_accepted(self):
        p = _make_profile(employee_count=50000)
        assert p.employee_count == 50000
