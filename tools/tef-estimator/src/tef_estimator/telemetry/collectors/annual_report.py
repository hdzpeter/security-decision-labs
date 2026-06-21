"""Annual report edition monitor (IRIS / Verizon)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from tef_estimator.telemetry.collectors.base import CollectionSummary
from tef_estimator.telemetry.db import TelemetryDB

log = logging.getLogger(__name__)

SOURCE_ID = "annual_report_monitor"
EVENT_TYPE = "report_update"
REQUEST_TIMEOUT = 30

MONITORED_REPORTS = [
    {
        "name": "IRIS",
        "url": "https://www.cyentia.com/iris/",
        "edition_pattern": r"IRIS\s+(\d{4})",
        "known_latest": "2024",
    },
    {
        "name": "Verizon",
        "url": "https://www.verizon.com/business/resources/reports/dbir/",
        "edition_pattern": r"(\d{4})\s+Data Breach Investigations Report",
        "known_latest": "2024",
    },
]

DEFAULT_STATE_DIR = Path.home() / ".tef-estimator" / "report_state"


def _check_report(
    report: dict,
    state_dir: Path,
) -> dict:
    name = report["name"]
    url = report["url"]
    pattern = report["edition_pattern"]
    known_latest = report["known_latest"]

    result = {
        "name": name,
        "url": url,
        "checked": True,
        "new_edition": False,
        "detected_edition": None,
        "error": None,
    }

    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        content = response.text

        editions = re.findall(pattern, content)
        if not editions:
            result["error"] = "No edition year found"
            return result

        latest_detected = max(editions)
        result["detected_edition"] = latest_detected

        state_file = state_dir / f"{name.lower()}_last_known.txt"
        last_known = known_latest
        if state_file.exists():
            last_known = state_file.read_text().strip()

        if int(latest_detected) > int(last_known):
            result["new_edition"] = True
            log.warning(
                "NEW %s EDITION DETECTED: %s (was %s) — update reference data!",
                name, latest_detected, last_known,
            )
            state_dir.mkdir(parents=True, exist_ok=True)
            state_file.write_text(latest_detected)
        else:
            log.info("%s: current edition %s (no update)", name, latest_detected)

    except requests.exceptions.RequestException as e:
        result["error"] = str(e)
        log.error("Failed to check %s: %s", name, e)

    return result


class AnnualReportCollector:
    SOURCE_ID = SOURCE_ID
    CADENCE_DAYS = 7

    def collect(
        self,
        db: TelemetryDB,
        *,
        state_dir: Path | None = None,
        **kwargs,
    ) -> CollectionSummary:
        collection_ts = db.collection_timestamp()
        state_dir = state_dir or DEFAULT_STATE_DIR

        log.info("Checking annual report editions...")

        conn = db.connect()
        cursor = conn.cursor()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        inserted = 0
        alerts = []

        for report in MONITORED_REPORTS:
            result = _check_report(report, state_dir)

            if result["error"]:
                continue

            if result["detected_edition"]:
                was_inserted = db.insert_observation(
                    cursor, SOURCE_ID, EVENT_TYPE,
                    today,
                    f"latest_edition_{result['name'].lower()}",
                    float(result["detected_edition"]),
                    "year", collection_ts, "",
                )
                if was_inserted:
                    inserted += 1

            if result["new_edition"]:
                alerts.append(
                    f"{result['name']} {result['detected_edition']}"
                )

        conn.commit()

        success = True
        health_notes = f"Checked {len(MONITORED_REPORTS)} reports"
        if alerts:
            health_notes += f" — NEW: {', '.join(alerts)}"

        db.update_source_health(conn, SOURCE_ID, success, health_notes)
        conn.close()

        return {
            "source": SOURCE_ID,
            "status": "completed",
            "records_inserted": inserted,
            "records_skipped": 0,
            "collection_timestamp": collection_ts,
        }
