"""
tef-estimator: Data-grounded Threat Event Frequency estimation.

Vector-decomposed ransomware TEF estimation using public empirical data
from IRIS, DBIR, Unit42, Mandiant, CrowdStrike, Beazley, IBM, Coalition, DShield, and GreyNoise.

Point-in-time estimates — refresh quarterly.
"""

__version__ = "1.1.3"

from tef_estimator.profile import OrganizationProfile
from tef_estimator.engine import TEFEngine
from tef_estimator.result import TEFResult

__all__ = ["OrganizationProfile", "TEFEngine", "TEFResult"]
