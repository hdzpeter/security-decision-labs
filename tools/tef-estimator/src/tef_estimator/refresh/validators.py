"""
Data staleness validation.

Checks that bundled reference data and scenario files are present
and within acceptable freshness thresholds.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from tef_estimator.data.loader import (
    REFERENCE_DIR,
    SCENARIOS_DIR,
    PEER_GRID_DIR,
)


STALENESS_WARNING_DAYS = 90
STALENESS_STALE_DAYS = 180

REFERENCE_SOURCES = [
    "iris", "coalition", "at_bay", "beazley", "common",
]


def _extract_date(path: Path) -> date | None:
    """Read extracted_date from a JSON file's _metadata."""
    try:
        with open(path) as f:
            data = json.load(f)
        raw = data.get("_metadata", {}).get("extracted_date")
        if raw:
            return date.fromisoformat(raw)
    except (json.JSONDecodeError, ValueError, KeyError):
        pass
    return None


def check_freshness(today: date | None = None) -> list[str]:
    """Return staleness warnings for all data sources.

    Returns a list of human-readable warning strings.
    Empty list means everything is fresh.
    """
    today = today or date.today()
    warnings: list[str] = []

    for source in REFERENCE_SOURCES:
        path = REFERENCE_DIR / source / "extracted.json"
        if not path.exists():
            continue
        extracted = _extract_date(path)
        if extracted is None:
            warnings.append(
                f"Data source '{source}' has no extracted_date — age unknown"
            )
            continue
        age = (today - extracted).days
        if age > STALENESS_STALE_DAYS:
            warnings.append(
                f"Data source '{source}' is {age} days old "
                f"(extracted {extracted.isoformat()}). Consider refreshing."
            )
        elif age > STALENESS_WARNING_DAYS:
            warnings.append(
                f"Data source '{source}' is {age} days old "
                f"(extracted {extracted.isoformat()})"
            )

    for scenario_file in sorted(SCENARIOS_DIR.glob("*.json")):
        extracted = _extract_date(scenario_file)
        if extracted is None:
            continue
        age = (today - extracted).days
        if age > STALENESS_STALE_DAYS:
            warnings.append(
                f"Scenario '{scenario_file.stem}' is {age} days old "
                f"(extracted {extracted.isoformat()}). Consider refreshing."
            )
        elif age > STALENESS_WARNING_DAYS:
            warnings.append(
                f"Scenario '{scenario_file.stem}' is {age} days old "
                f"(extracted {extracted.isoformat()})"
            )

    return warnings


def run_check() -> dict[str, str]:
    """Validate data sources and report status."""
    results = {}
    print("Data validation report:")
    print("=" * 60)

    print(f"  Reference data: {REFERENCE_DIR}")
    print()

    for source in REFERENCE_SOURCES:
        path = REFERENCE_DIR / source / "extracted.json"
        if not path.exists():
            status = "missing"
            age_str = ""
        else:
            status = "present"
            extracted = _extract_date(path)
            if extracted:
                age = (date.today() - extracted).days
                age_str = f" ({age}d old, extracted {extracted.isoformat()})"
            else:
                age_str = " (no date)"
        results[f"ref_{source}"] = status
        icon = "+" if status == "present" else "X"
        print(f"  [{icon}] {source.replace('_', ' ').title()} reference: {status}{age_str}")

    print()

    for scenario in ["ransomware", "bec"]:
        path = SCENARIOS_DIR / f"{scenario}.json"
        if path.exists():
            results[f"scenario_{scenario}"] = "present"
            extracted = _extract_date(path)
            age_str = ""
            if extracted:
                age = (date.today() - extracted).days
                age_str = f" ({age}d old)"
            print(f"  [+] Scenario {scenario}: present{age_str}")
        else:
            results[f"scenario_{scenario}"] = "missing"
            print(f"  [X] Scenario {scenario}: missing")

    print()

    grid_path = PEER_GRID_DIR / "ransomware.json"
    if grid_path.exists():
        results["peer_grid"] = "present"
        print("  [+] Peer grid: present")
    else:
        results["peer_grid"] = "missing"
        print("  [X] Peer grid: missing (run: tef-estimator data peer-grid --rebuild)")

    print()

    freshness_warnings = check_freshness()
    if freshness_warnings:
        print("FRESHNESS WARNINGS:")
        for w in freshness_warnings:
            print(f"  ! {w}")
        print()

    pkg_data = Path(__file__).resolve().parent.parent / "data"
    log_path = pkg_data / "refresh_log.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = {
        "timestamp": datetime.now().isoformat(),
        "results": results,
    }
    log_path.write_text(json.dumps(log, indent=2))
    print(f"Validation log saved to {log_path}")

    return results
