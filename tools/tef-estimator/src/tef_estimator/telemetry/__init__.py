"""
Continuous telemetry monitoring for TEF estimation.

Requires the telemetry extra:
    pip install tef-estimator[telemetry]
"""

from __future__ import annotations


def _check_requests() -> None:
    try:
        import requests  # noqa: F401
    except ImportError:
        raise ImportError(
            "Telemetry features require the 'requests' package.\n"
            "Install with: pip install tef-estimator[telemetry]"
        ) from None
