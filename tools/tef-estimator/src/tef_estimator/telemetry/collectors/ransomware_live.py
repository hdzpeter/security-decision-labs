"""Ransomware.live victim telemetry collector."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

import requests

from tef_estimator.telemetry.collectors.base import CollectionSummary
from tef_estimator.telemetry.db import TelemetryDB

log = logging.getLogger(__name__)

SOURCE_ID = "ransomware_live"
EVENT_TYPE = "ransomware_activity"
VICTIMS_URL = "https://data.ransomware.live/victims.json"
REQUEST_TIMEOUT = 120


def _normalize_date(raw_date: str | None) -> str | None:
    if not raw_date:
        return None
    raw_date = raw_date.strip()

    if "T" in raw_date:
        try:
            return datetime.fromisoformat(raw_date).strftime("%Y-%m-%d")
        except ValueError:
            pass

    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw_date, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def _filter_and_aggregate(
    victims: list[dict],
) -> tuple[dict[str, int], dict[str, int]]:
    daily_counts: dict[str, int] = defaultdict(int)
    group_counts: dict[str, int] = defaultdict(int)

    for victim in victims:
        discovered = _normalize_date(victim.get("discovered"))
        if not discovered:
            continue

        daily_counts[discovered] += 1

        group_name = victim.get("group_name")
        if group_name:
            group_counts[group_name] += 1

    return dict(daily_counts), dict(group_counts)


class RansomwareLiveCollector:
    SOURCE_ID = SOURCE_ID
    CADENCE_DAYS = 1

    def collect(self, db: TelemetryDB, **kwargs) -> CollectionSummary:
        collection_ts = db.collection_timestamp()
        log.info("Fetching ransomware.live victims...")

        try:
            response = requests.get(
                VICTIMS_URL,
                timeout=REQUEST_TIMEOUT,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            log.error("Failed to fetch victims: %s", e)
            conn = db.connect()
            db.update_source_health(conn, SOURCE_ID, False, str(e))
            conn.close()
            return {
                "source": SOURCE_ID,
                "status": "failed",
                "records_inserted": 0,
                "records_skipped": 0,
                "error": str(e),
            }

        payload_hash = TelemetryDB.compute_hash(response.text)
        last_hash = db.get_last_hash(SOURCE_ID)

        if payload_hash == last_hash:
            log.info("No change in victims data (hash match)")
            conn = db.connect()
            db.update_source_health(conn, SOURCE_ID, True, "No changes detected")
            conn.close()
            return {
                "source": SOURCE_ID,
                "status": "completed",
                "records_inserted": 0,
                "records_skipped": 0,
                "collection_timestamp": collection_ts,
            }

        victims = response.json()
        if not isinstance(victims, list):
            log.error("Expected list, got %s", type(victims).__name__)
            return {
                "source": SOURCE_ID,
                "status": "failed",
                "records_inserted": 0,
                "records_skipped": 0,
                "error": "Unexpected response format",
            }

        log.info("Processing %d victims...", len(victims))
        daily_counts, group_counts = _filter_and_aggregate(victims)

        conn = db.connect()
        cursor = conn.cursor()

        inserted = 0
        skipped = 0

        for date_str, count in sorted(daily_counts.items()):
            was_inserted = db.insert_observation(
                cursor, SOURCE_ID, EVENT_TYPE,
                date_str, "daily_victim_count", float(count),
                "count", collection_ts, payload_hash,
            )
            if was_inserted:
                inserted += 1
            else:
                skipped += 1

        for group_name, count in sorted(group_counts.items()):
            was_inserted = db.insert_observation(
                cursor, SOURCE_ID, EVENT_TYPE,
                datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                f"group_census_{group_name}", float(count),
                "count", collection_ts, payload_hash,
            )
            if was_inserted:
                inserted += 1
            else:
                skipped += 1

        conn.commit()

        db.save_hash(SOURCE_ID, payload_hash)
        health_notes = (
            f"{len(victims)} victims processed, "
            f"{len(daily_counts)} dates, "
            f"{len(group_counts)} groups, "
            f"{inserted} records inserted"
        )
        db.update_source_health(conn, SOURCE_ID, True, health_notes)
        conn.close()

        log.info("Ransomware.live: %d inserted, %d skipped", inserted, skipped)

        return {
            "source": SOURCE_ID,
            "status": "completed",
            "records_inserted": inserted,
            "records_skipped": skipped,
            "collection_timestamp": collection_ts,
        }
