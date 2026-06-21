"""
Vector-decomposed TEF estimation.

Each initial access vector has its own floor, ceiling, and positioning logic.
The vectors are:

    - Exploitation: public-facing app/device exploitation (DShield/GreyNoise observable)
    - Credential: stolen/purchased VPN/RDP/SSO credentials (IAB market)
    - Phishing: email-based social engineering
    - Supply chain: third-party compromise

Total TEF = sum of vector TEFs with cross-vector dampening.
"""

from tef_estimator.vectors.base import VectorEstimate
from tef_estimator.vectors.exploitation import ExploitationVector
from tef_estimator.vectors.credential import CredentialVector
from tef_estimator.vectors.phishing import PhishingVector
from tef_estimator.vectors.supply_chain import SupplyChainVector

__all__ = [
    "VectorEstimate",
    "ExploitationVector",
    "CredentialVector",
    "PhishingVector",
    "SupplyChainVector",
]
