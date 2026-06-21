"""
Scenario definitions for TEF estimation.

Each scenario defines its own vector proportions, base rate triangulation,
sector/revenue adjustments, and output templates. The engine consumes
scenario definitions and runs identically regardless of threat type.
"""

from tef_estimator.data.scenarios.base import ScenarioDefinition
from tef_estimator.data.scenarios.ransomware import RansomwareScenario

__all__ = ["ScenarioDefinition", "RansomwareScenario"]
