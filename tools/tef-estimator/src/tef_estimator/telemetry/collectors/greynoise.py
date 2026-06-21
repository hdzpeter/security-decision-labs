"""GreyNoise Community API telemetry collector."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from tef_estimator.telemetry.collectors.base import CollectionSummary
from tef_estimator.telemetry.db import TelemetryDB

log = logging.getLogger(__name__)

SOURCE_ID = "greynoise"
EVENT_TYPE = "internet_noise"
COMMUNITY_API_URL = "https://api.greynoise.io/v3/community/"
REQUEST_TIMEOUT = 30
RATE_LIMIT_DELAY = 2.0
TTL_DAYS = 30
DEFAULT_BATCH_SIZE = 40

CLASSIFICATION_MAP = {
    "malicious": 1.0,
    "benign": 0.0,
    "unknown": 0.5,
}

DEFAULT_PRIORITY_IPS = [
    "45.33.32.156",
    "8.8.8.8",
    "1.1.1.1",
]


def _query_ip(ip: str, api_key: str | None = None) -> dict | None:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["key"] = api_key

    try:
        response = requests.get(
            f"{COMMUNITY_API_URL}{ip}",
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code == 429:
            log.warning("Rate limited by GreyNoise, pausing...")
            time.sleep(60)
            return None

        if response.status_code == 404:
            return {"ip": ip, "noise": False, "classification": "unknown"}

        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        log.error("GreyNoise query failed for %s: %s", ip, e)
        return None


def _build_ip_queue(
    db: TelemetryDB,
    priority_ips: list[str],
    batch_size: int,
) -> list[str]:
    queue = list(priority_ips)

    conn = db.connect()
    cursor = conn.cursor()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=TTL_DAYS)).strftime("%Y-%m-%d")

    cursor.execute(
        """SELECT DISTINCT metric_name FROM raw_observations
           WHERE source_id = ? AND observation_date >= ?
           ORDER BY observation_date ASC""",
        (SOURCE_ID, cutoff),
    )

    for row in cursor.fetchall():
        metric = row[0]
        if metric.startswith("noise_") and metric[6:] not in queue:
            queue.append(metric[6:])
            if len(queue) >= batch_size:
                break

    conn.close()
    return queue[:batch_size]


class GreyNoiseCollector:
    SOURCE_ID = SOURCE_ID
    CADENCE_DAYS = 1

    def collect(
        self,
        db: TelemetryDB,
        *,
        api_key: str | None = None,
        priority_ips: list[str] | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        **kwargs,
    ) -> CollectionSummary:
        collection_ts = db.collection_timestamp()
        priority_ips = priority_ips or DEFAULT_PRIORITY_IPS

        ip_queue = _build_ip_queue(db, priority_ips, batch_size)
        log.info("GreyNoise: querying %d IPs...", len(ip_queue))

        conn = db.connect()
        cursor = conn.cursor()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        inserted = 0
        skipped = 0
        queried = 0
        failed = 0

        for i, ip in enumerate(ip_queue):
            result = _query_ip(ip, api_key)

            if result is None:
                failed += 1
                continue

            queried += 1
            classification = result.get("classification", "unknown")
            noise = result.get("noise", False)

            noise_value = CLASSIFICATION_MAP.get(classification, 0.5)
            was_inserted = db.insert_observation(
                cursor, SOURCE_ID, EVENT_TYPE,
                today, f"noise_{ip}", noise_value,
                "classification", collection_ts,
                TelemetryDB.compute_hash(str(result)),
            )
            if was_inserted:
                inserted += 1
            else:
                skipped += 1

            if noise:
                db.insert_observation(
                    cursor, SOURCE_ID, EVENT_TYPE,
                    today, f"active_noise_{ip}", 1.0,
                    "binary", collection_ts,
                    TelemetryDB.compute_hash(str(result)),
                )

            if i < len(ip_queue) - 1:
                time.sleep(RATE_LIMIT_DELAY)

        conn.commit()

        health_notes = (
            f"{queried}/{len(ip_queue)} IPs queried, "
            f"{failed} failed, "
            f"{inserted} records inserted"
        )
        db.update_source_health(conn, SOURCE_ID, queried > 0, health_notes)
        conn.close()

        log.info("GreyNoise: %d inserted, %d skipped, %d failed",
                 inserted, skipped, failed)

        return {
            "source": SOURCE_ID,
            "status": "completed" if queried > 0 else "failed",
            "records_inserted": inserted,
            "records_skipped": skipped,
            "collection_timestamp": collection_ts,
        }
