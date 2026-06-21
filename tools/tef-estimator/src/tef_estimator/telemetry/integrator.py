"""Transform raw observations into clean, aligned time series.

Responsibilities:
  - Deduplication: most recent collection_timestamp wins per (date, metric).
  - Gap detection: for daily sources, identifies missing dates.
    Single-day gaps are linearly interpolated (flagged). Longer gaps logged.
  - Rolling averages: 7-day and 30-day, written as derived metrics.
  - All output goes to the time_series table.
"""

from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from tef_estimator.telemetry.db import TelemetryDB

log = logging.getLogger(__name__)

DAILY_SOURCES = {
    "dshield": {
        "event_type": "scan_activity",
    },
    "ransomware_live": {
        "event_type": "ransomware_activity",
    },
}

EVENT_SOURCES = {
    "cisa_kev": {
        "event_type": "vulnerability_catalog",
    },
    "greynoise": {
        "event_type": "internet_noise",
    },
}

DEFAULT_LOOKBACK_DAYS = 90


def _date_range(start: str, end: str) -> list[str]:
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    current = start_dt
    dates = []
    while current <= end_dt:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def _rolling_average(
    values_by_date: dict[str, float],
    sorted_dates: list[str],
    window: int,
) -> dict[str, float]:
    result = {}
    for i, date in enumerate(sorted_dates):
        window_start = max(0, i - window + 1)
        window_dates = sorted_dates[window_start : i + 1]
        window_values = [
            values_by_date[d] for d in window_dates if d in values_by_date
        ]
        if window_values:
            result[date] = sum(window_values) / len(window_values)
    return result


def _integrate_daily(
    cursor: sqlite3.Cursor,
    source_id: str,
    event_type: str,
    cutoff_date: str,
) -> dict[str, Any]:
    log.info("Processing daily source: %s", source_id)

    cursor.execute(
        """SELECT observation_date, metric_name, metric_value, collection_timestamp
           FROM raw_observations
           WHERE source_id = ? AND event_type = ? AND observation_date >= ?
           ORDER BY observation_date, metric_name, collection_timestamp DESC""",
        (source_id, event_type, cutoff_date),
    )
    rows = cursor.fetchall()

    if not rows:
        log.info("  No raw data for %s since %s", source_id, cutoff_date)
        return {"source": source_id, "processed": 0, "inserted": 0, "gaps": 0}

    metrics: dict[str, dict[str, float]] = defaultdict(dict)
    seen: set[tuple[str, str]] = set()
    for obs_date, metric_name, value, _ts in rows:
        key = (obs_date, metric_name)
        if key not in seen:
            seen.add(key)
            metrics[metric_name][obs_date] = value

    log.info(
        "  Found %d unique metrics, %d (date, metric) pairs",
        len(metrics), len(seen),
    )

    inserted = 0
    gaps_found = 0
    interpolated = 0

    for metric_name, values_by_date in metrics.items():
        if not values_by_date:
            continue

        sorted_dates = sorted(values_by_date.keys())
        all_dates = _date_range(sorted_dates[0], sorted_dates[-1])
        missing_dates = set(d for d in all_dates if d not in values_by_date)

        if missing_dates:
            gaps_found += len(missing_dates)
            for missing_date in missing_dates:
                idx = all_dates.index(missing_date)
                prev_date = all_dates[idx - 1] if idx > 0 else None
                next_date = all_dates[idx + 1] if idx < len(all_dates) - 1 else None

                prev_val = values_by_date.get(prev_date) if prev_date else None
                next_val = values_by_date.get(next_date) if next_date else None

                if prev_val is not None and next_val is not None:
                    values_by_date[missing_date] = (prev_val + next_val) / 2.0
                    interpolated += 1

        sorted_dates = sorted(values_by_date.keys())

        for date_str in sorted_dates:
            value = values_by_date[date_str]
            is_interp = 1 if date_str in missing_dates else 0
            try:
                cursor.execute(
                    """INSERT OR REPLACE INTO time_series
                       (source_id, series_date, event_type, metric_name,
                        value, interpolation_flag)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (source_id, date_str, event_type, metric_name, value, is_interp),
                )
                inserted += 1
            except sqlite3.Error as e:
                log.error("  Insert error for %s on %s: %s", metric_name, date_str, e)

        for suffix, window in [("7d_avg", 7), ("30d_avg", 30)]:
            avgs = _rolling_average(values_by_date, sorted_dates, window)
            for date_str, avg_val in avgs.items():
                try:
                    cursor.execute(
                        """INSERT OR REPLACE INTO time_series
                           (source_id, series_date, event_type, metric_name,
                            value, interpolation_flag)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (source_id, date_str, event_type,
                         f"{metric_name}_{suffix}", avg_val, 0),
                    )
                    inserted += 1
                except sqlite3.Error as e:
                    log.error("  Insert error for %s_%s on %s: %s",
                              metric_name, suffix, date_str, e)

    if gaps_found:
        log.info("  Gaps: %d missing dates, %d interpolated", gaps_found, interpolated)

    return {
        "source": source_id,
        "metrics": len(metrics),
        "date_metric_pairs": len(seen),
        "inserted": inserted,
        "gaps_found": gaps_found,
        "interpolated": interpolated,
    }


def _integrate_event(
    cursor: sqlite3.Cursor,
    source_id: str,
    event_type: str,
    cutoff_date: str,
) -> dict[str, Any]:
    log.info("Processing event source: %s", source_id)

    cursor.execute(
        """SELECT observation_date, metric_name, metric_value, collection_timestamp
           FROM raw_observations
           WHERE source_id = ? AND event_type = ? AND observation_date >= ?
           ORDER BY observation_date, metric_name, collection_timestamp DESC""",
        (source_id, event_type, cutoff_date),
    )
    rows = cursor.fetchall()

    if not rows:
        log.info("  No raw data for %s since %s", source_id, cutoff_date)
        return {"source": source_id, "processed": 0, "inserted": 0}

    seen: set[tuple[str, str]] = set()
    inserted = 0

    for obs_date, metric_name, value, _ts in rows:
        key = (obs_date, metric_name)
        if key in seen:
            continue
        seen.add(key)

        try:
            cursor.execute(
                """INSERT OR REPLACE INTO time_series
                   (source_id, series_date, event_type, metric_name,
                    value, interpolation_flag)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (source_id, obs_date, event_type, metric_name, value, 0),
            )
            inserted += 1
        except sqlite3.Error as e:
            log.error("  Insert error for %s on %s: %s", metric_name, obs_date, e)

    log.info("  Processed %d unique records, inserted %d", len(seen), inserted)

    return {"source": source_id, "processed": len(seen), "inserted": inserted}


def run_integration(
    db: TelemetryDB,
    *,
    source_filter: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, Any]:
    """Process raw observations into clean time series."""
    cutoff_date = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
    ).strftime("%Y-%m-%d")

    log.info("Starting integration (lookback=%dd, cutoff=%s)", lookback_days, cutoff_date)

    conn = db.connect()
    cursor = conn.cursor()
    results = []

    for source_id, config in DAILY_SOURCES.items():
        if source_filter and source_id != source_filter:
            continue
        result = _integrate_daily(cursor, source_id, config["event_type"], cutoff_date)
        results.append(result)
        conn.commit()

    for source_id, config in EVENT_SOURCES.items():
        if source_filter and source_id != source_filter:
            continue
        result = _integrate_event(cursor, source_id, config["event_type"], cutoff_date)
        results.append(result)
        conn.commit()

    conn.close()

    total_inserted = sum(r.get("inserted", 0) for r in results)
    total_gaps = sum(r.get("gaps_found", 0) for r in results)
    total_interpolated = sum(r.get("interpolated", 0) for r in results)

    log.info(
        "Integration complete: %d sources, %d records, %d gaps (%d interpolated)",
        len(results), total_inserted, total_gaps, total_interpolated,
    )

    return {
        "status": "completed",
        "cutoff_date": cutoff_date,
        "sources_processed": len(results),
        "total_inserted": total_inserted,
        "total_gaps_found": total_gaps,
        "total_interpolated": total_interpolated,
        "per_source": results,
    }
