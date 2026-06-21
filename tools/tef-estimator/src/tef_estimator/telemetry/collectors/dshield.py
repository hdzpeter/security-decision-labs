"""DShield port scan telemetry collector."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from tef_estimator.telemetry.collectors.base import CollectionSummary
from tef_estimator.telemetry.db import TelemetryDB

log = logging.getLogger(__name__)

DEFAULT_PORTS = [3389, 445, 443, 22, 23, 8080, 8443]
DEFAULT_LOOKBACK_DAYS = 7
REQUEST_DELAY_SECONDS = 2
REQUEST_TIMEOUT = 30
USER_AGENT = "TEF-Telemetry-Agent/0.1 (research; FAIR-TEF-estimation)"

SOURCE_ID = "dshield"
EVENT_TYPE = "scan_activity"


def fetch_port_history(
    port: int, start_date: str, end_date: str,
) -> tuple[list | None, str | None]:
    url = (
        f"https://isc.sans.edu/api/porthistory/"
        f"{port}/{start_date}/{end_date}?json"
    )
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        raw_text = response.text
        payload_hash = TelemetryDB.compute_hash(raw_text)

        data = response.json()

        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                data = data["data"]
            else:
                numbered = {}
                for k, v in data.items():
                    if k.isdigit() and isinstance(v, dict):
                        numbered[int(k)] = v
                if numbered:
                    data = [numbered[k] for k in sorted(numbered.keys())]
                else:
                    log.warning("Port %d: unexpected dict response, keys=%s",
                                port, list(data.keys()))
                    return None, None

        if not isinstance(data, list):
            log.warning("Port %d: expected list, got %s", port, type(data).__name__)
            return None, None

        if len(data) == 0:
            log.info("Port %d: empty response", port)
            return [], payload_hash

        return data, payload_hash

    except requests.exceptions.Timeout:
        log.error("Port %d: timed out after %ds", port, REQUEST_TIMEOUT)
        return None, None
    except requests.exceptions.HTTPError as e:
        log.error("Port %d: HTTP error %d", port, e.response.status_code)
        return None, None
    except requests.exceptions.ConnectionError as e:
        log.error("Port %d: connection error: %s", port, e)
        return None, None
    except json.JSONDecodeError as e:
        log.error("Port %d: invalid JSON: %s", port, e)
        return None, None


def _collect_port(
    db: TelemetryDB,
    cursor,
    port: int,
    start_date: str,
    end_date: str,
    collection_ts: str,
) -> tuple[int, int, bool]:
    log.info("Fetching port %d (%s to %s)...", port, start_date, end_date)

    data, payload_hash = fetch_port_history(port, start_date, end_date)

    if data is None:
        return 0, 0, False
    if len(data) == 0:
        return 0, 0, True

    inserted = 0
    skipped = 0

    for record in data:
        obs_date = record.get("date")
        if not obs_date:
            skipped += 1
            continue

        obs_date = str(obs_date).strip()

        metrics = {
            f"unique_sources_port_{port}": record.get("sources"),
            f"unique_targets_port_{port}": record.get("targets"),
            f"total_records_port_{port}": record.get("records"),
        }

        for metric_name, raw_value in metrics.items():
            if raw_value is None:
                skipped += 1
                continue
            try:
                metric_value = float(raw_value)
            except (ValueError, TypeError):
                skipped += 1
                continue

            was_inserted = db.insert_observation(
                cursor, SOURCE_ID, EVENT_TYPE,
                obs_date, metric_name, metric_value,
                "count", collection_ts, payload_hash,
            )
            if was_inserted:
                inserted += 1
            else:
                skipped += 1

    log.info("Port %d: %d inserted, %d skipped", port, inserted, skipped)
    return inserted, skipped, True


class DShieldCollector:
    SOURCE_ID = SOURCE_ID
    CADENCE_DAYS = 1

    def collect(
        self,
        db: TelemetryDB,
        *,
        ports: list[int] | None = None,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        **kwargs,
    ) -> CollectionSummary:
        ports = ports or DEFAULT_PORTS
        now = datetime.now(timezone.utc)
        end_date = now.strftime("%Y-%m-%d")
        start_date = (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        collection_ts = db.collection_timestamp()

        log.info("Starting DShield collection")

        conn = db.connect()
        cursor = conn.cursor()

        total_inserted = 0
        total_skipped = 0
        ports_succeeded = 0
        ports_failed = 0

        for i, port in enumerate(ports):
            inserted, skipped, success = _collect_port(
                db, cursor, port, start_date, end_date, collection_ts,
            )
            total_inserted += inserted
            total_skipped += skipped

            if success:
                ports_succeeded += 1
            else:
                ports_failed += 1

            conn.commit()

            if i < len(ports) - 1:
                time.sleep(REQUEST_DELAY_SECONDS)

        health_notes = (
            f"{ports_succeeded}/{len(ports)} ports succeeded, "
            f"{total_inserted} records inserted, "
            f"{total_skipped} skipped"
        )
        db.update_source_health(conn, SOURCE_ID, ports_succeeded > 0, health_notes)
        conn.close()

        return {
            "source": SOURCE_ID,
            "status": "completed" if ports_succeeded > 0 else "failed",
            "records_inserted": total_inserted,
            "records_skipped": total_skipped,
            "collection_timestamp": collection_ts,
        }
